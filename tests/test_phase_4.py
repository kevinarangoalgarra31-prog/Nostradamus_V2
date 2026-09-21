from __future__ import annotations

import hashlib
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from src.config import load_sentiment_config
from src.sentiment import (
    CsvNewsProvider,
    GoogleNewsRssProvider,
    GroqCompletionClient,
    LexiconSentimentAnalyzer,
    NewsItem,
    SentimentAssessment,
    StructuredLLMSentimentAnalyzer,
    aggregate_signal,
    audit_news,
    evaluate_assessments,
    parse_datetime_utc,
    save_sentiment_run,
    build_labeling_queue,
    evaluate_labeling_queue,
)


UTC = timezone.utc
DECISION = datetime(2026, 1, 8, tzinfo=UTC)


def news_item(
    suffix: str,
    *,
    title: str = "Bitcoin market publishes a routine update",
    source: str = "Test source",
    language: str = "en",
    published_at: str = "2026-01-07T10:00:00Z",
    captured_at: str = "2026-01-07T10:30:00Z",
    metadata: dict[str, str] | None = None,
) -> NewsItem:
    return NewsItem(
        asset="BTC-USD",
        title=title,
        source=source,
        url=f"https://example.test/{suffix}",
        language=language,
        published_at=published_at,
        captured_at=captured_at,
        provider="test",
        metadata=metadata or {},
    )


class SentimentConfigTests(unittest.TestCase):
    def test_repository_sentiment_config_is_explicit(self) -> None:
        config = load_sentiment_config("config/sentiment_v4.yaml")
        self.assertEqual(config.version, "4.0.0")
        self.assertGreaterEqual(config.min_headlines, 1)
        self.assertEqual(config.provider, "csv")
        self.assertIn("BTC-USD", config.query_terms)
        self.assertEqual(config.max_completion_tokens, 256)


class NewsDomainAndProviderTests(unittest.TestCase):
    def test_dates_are_timezone_aware_and_ids_are_deterministic(self) -> None:
        first = news_item("same")
        second = news_item(
            "same",
            published_at="2026-01-07T05:00:00-05:00",
            captured_at="2026-01-07T05:30:00-05:00",
        )
        self.assertEqual(first.news_id, second.news_id)
        self.assertEqual(first.published_at.tzinfo, UTC)
        with self.assertRaises(ValueError):
            parse_datetime_utc("2026-01-07T10:00:00")

    def test_csv_provider_preserves_metadata_and_reports_invalid_rows(self) -> None:
        content = (
            "asset,title,source,url,language,published_at,captured_at,manual_label\n"
            "BTC-USD,Bitcoin gains,Source,https://example.test/ok,en,"
            "2026-01-07T10:00:00Z,2026-01-07T10:01:00Z,1\n"
            "BTC-USD,Broken,Source,,en,2026-01-07T10:00:00Z,"
            "2026-01-07T10:01:00Z,-1\n"
            "ETH-USD,Ethereum gains,Source,https://example.test/eth,en,"
            "2026-01-07T10:00:00Z,2026-01-07T10:01:00Z,1\n"
        )
        directory = Path("tmp/test_phase4_provider")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "news.csv"
        path.write_text(content, encoding="utf-8")
        result = CsvNewsProvider(path).collect("BTC-USD", DECISION)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].metadata["manual_label"], "1")
        self.assertEqual(len(result.issues), 1)
        self.assertEqual(result.issues[0]["reason"], "invalid_provider_record")

    def test_rss_provider_uses_same_normalized_contract(self) -> None:
        entry = SimpleNamespace(
            title="Bitcoin ETF approval",
            source={"title": "Example wire"},
            link="https://example.test/rss-item",
            published="Wed, 07 Jan 2026 10:00:00 GMT",
        )
        feed = SimpleNamespace(entries=[entry], bozo=False)
        provider = GoogleNewsRssProvider(
            query_terms={"BTC-USD": "Bitcoin"}, parser=lambda _url: feed
        )
        result = provider.collect("BTC-USD", DECISION)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source, "Example wire")
        self.assertEqual(result.items[0].query, "Bitcoin")
        self.assertEqual(result.items[0].captured_at, DECISION)


class NewsAuditTests(unittest.TestCase):
    def test_audit_rejects_lookahead_age_language_and_duplicates(self) -> None:
        valid = news_item("valid")
        duplicate = news_item("duplicate")
        future_publish = news_item(
            "future-publish",
            published_at="2026-01-08T01:00:00Z",
            captured_at="2026-01-08T01:05:00Z",
        )
        future_capture = news_item(
            "future-capture", captured_at="2026-01-08T01:00:00Z"
        )
        old = news_item(
            "old",
            title="Old Bitcoin market report",
            published_at="2025-12-20T10:00:00Z",
            captured_at="2025-12-20T10:30:00Z",
        )
        wrong_language = news_item(
            "fr", title="Bitcoin rapport", language="fr"
        )
        batch = audit_news(
            [valid, duplicate, future_publish, future_capture, old, wrong_language],
            asset="BTC-USD",
            decision_at=DECISION,
            lookback_hours=168,
            allowed_languages=("en", "es"),
        )
        self.assertEqual(len(batch.accepted), 1)
        reasons = batch.metrics["rejection_reasons"]
        self.assertEqual(reasons["duplicate"], 1)
        self.assertEqual(reasons["published_after_decision"], 1)
        self.assertEqual(reasons["captured_after_decision"], 1)
        self.assertEqual(reasons["outside_lookback"], 1)
        self.assertEqual(reasons["language_not_allowed"], 1)

    def test_no_coverage_is_explicit(self) -> None:
        batch = audit_news(
            [], asset="BTC-USD", decision_at=DECISION, lookback_hours=24
        )
        self.assertEqual(batch.metrics["coverage_status"], "no_coverage")


class AnalyzerTests(unittest.TestCase):
    @patch("groq.Groq")
    def test_groq_client_caps_the_expected_output(self, groq_factory) -> None:
        completion = SimpleNamespace(message=SimpleNamespace(content='{"ok": true}'))
        groq_factory.return_value.chat.completions.create.return_value = SimpleNamespace(
            choices=[completion]
        )
        client = GroqCompletionClient(
            model="fixture-model",
            api_key="fixture-key",
            max_completion_tokens=256,
        )

        self.assertEqual(client("prompt"), '{"ok": true}')
        call = groq_factory.return_value.chat.completions.create.call_args
        self.assertEqual(call.kwargs["max_completion_tokens"], 256)

    def test_lexicon_is_structured_and_auditable(self) -> None:
        analyzer = LexiconSentimentAnalyzer()
        result = analyzer.analyze(
            news_item("positive", title="Bitcoin ETF approval drives a bullish rally"),
            created_at=DECISION,
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.sentiment, 1)
        self.assertGreater(result.confidence, 0.0)
        self.assertTrue(any(value.startswith("positive:") for value in result.evidence))

    def test_irrelevant_headline_is_not_forced_to_neutral(self) -> None:
        analyzer = LexiconSentimentAnalyzer()
        result = analyzer.analyze(
            news_item("weather", title="Rain is expected tomorrow"),
            created_at=DECISION,
        )
        self.assertEqual(result.status, "irrelevant")
        self.assertIsNone(result.sentiment)

    def test_invalid_llm_response_is_not_forced_to_neutral(self) -> None:
        analyzer = StructuredLLMSentimentAnalyzer(
            lambda _prompt: "probably positive",
            model_name="fixture-model",
            model_version="1",
        )
        result = analyzer.analyze(news_item("llm-invalid"), created_at=DECISION)
        self.assertEqual(result.status, "invalid_response")
        self.assertIsNone(result.sentiment)
        self.assertTrue(result.raw_response_sha256)

    def test_valid_llm_response_requires_literal_evidence(self) -> None:
        raw = json.dumps(
            {
                "sentiment": -1,
                "score": -0.8,
                "confidence": 0.9,
                "relevance": 1.0,
                "evidence": ["security breach"],
            }
        )
        analyzer = StructuredLLMSentimentAnalyzer(
            lambda _prompt: raw, model_name="fixture-model", model_version="1"
        )
        item = news_item(
            "llm-valid", title="Bitcoin exchange reports a security breach"
        )
        result = analyzer.analyze(item, created_at=DECISION)
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.sentiment, -1)
        self.assertEqual(result.evidence, ("security breach",))


class SignalAndArtifactTests(unittest.TestCase):
    def _assessment(
        self, item: NewsItem, sentiment: int, *, analyzer: str = "test"
    ) -> SentimentAssessment:
        return SentimentAssessment(
            news_id=item.news_id,
            asset=item.asset,
            analyzer=analyzer,
            model_name="fixture",
            model_version="1",
            created_at=DECISION,
            status="ok",
            sentiment=sentiment,
            score=float(sentiment),
            confidence=0.8,
            relevance=1.0,
            evidence=(item.title,),
        )

    def test_aggregate_has_explicit_insufficient_state(self) -> None:
        item = news_item("one", source="Source A")
        assessment = self._assessment(item, 1)
        signal = aggregate_signal(
            [item],
            [assessment],
            asset="BTC-USD",
            decision_at=DECISION,
            analyzer="test",
            model_version="1",
            min_headlines=2,
            min_relevance=0.25,
            positive_threshold=0.15,
            negative_threshold=-0.15,
        )
        self.assertEqual(signal.status, "insufficient_data")
        self.assertIsNone(signal.sentiment)

    def test_valid_aggregate_reports_cross_source_agreement(self) -> None:
        first = news_item("source-a", source="Source A")
        second = news_item(
            "source-b", title="Bitcoin adoption gains", source="Source B"
        )
        assessments = [self._assessment(first, 1), self._assessment(second, 1)]
        signal = aggregate_signal(
            [first, second],
            assessments,
            asset="BTC-USD",
            decision_at=DECISION,
            analyzer="test",
            model_version="1",
            min_headlines=2,
            min_relevance=0.25,
            positive_threshold=0.15,
            negative_threshold=-0.15,
        )
        self.assertEqual(signal.status, "ok")
        self.assertEqual(signal.sentiment, 1)
        self.assertEqual(signal.unique_sources, 2)
        self.assertEqual(signal.source_agreement, 1.0)

    def test_evaluation_reports_coverage_accuracy_and_analyzer_agreement(self) -> None:
        first = news_item("first", metadata={"manual_label": "1"})
        second = news_item(
            "second",
            title="Bitcoin breach",
            metadata={"manual_label": "-1"},
        )
        assessments = [
            self._assessment(first, 1, analyzer="lexicon"),
            self._assessment(second, -1, analyzer="lexicon"),
            self._assessment(first, 1, analyzer="llm"),
            self._assessment(second, 0, analyzer="llm"),
        ]
        result = evaluate_assessments([first, second], assessments)
        self.assertEqual(result["analyzers"]["lexicon"]["accuracy"], 1.0)
        self.assertEqual(result["analyzers"]["llm"]["coverage"], 1.0)
        comparison = result["analyzer_agreement"]["lexicon__vs__llm"]
        self.assertEqual(comparison["overlap"], 2)
        self.assertEqual(comparison["agreement"], 0.5)

    def test_artifact_manifest_links_content_hashes_and_model_version(self) -> None:
        item = news_item("artifact", metadata={"manual_label": "0"})
        assessment = self._assessment(item, 0)
        batch = audit_news(
            [item], asset="BTC-USD", decision_at=DECISION, lookback_hours=24
        )
        signal = aggregate_signal(
            [item],
            [assessment],
            asset="BTC-USD",
            decision_at=DECISION,
            analyzer="test",
            model_version="1",
            min_headlines=1,
            min_relevance=0.25,
            positive_threshold=0.15,
            negative_threshold=-0.15,
        )
        evaluation = evaluate_assessments([item], [assessment])
        directory = Path("tmp/test_phase4_artifacts")
        directory.mkdir(parents=True, exist_ok=True)
        paths = save_sentiment_run(
            directory,
            batch=batch,
            assessments=[assessment],
            signals=[signal],
            evaluation=evaluation,
            config={"version": "4.0.0"},
            provider="fixture",
        )
        manifest = json.loads(paths.manifest.read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["artifact_sha256"]["headlines.csv"],
            hashlib.sha256(paths.headlines.read_bytes()).hexdigest(),
        )
        self.assertIn("test:fixture:1", manifest["models"])

    def test_labeling_queue_preserves_human_labels(self) -> None:
        root = Path("tmp/test_phase4_labeling/run/BTC_USD")
        root.mkdir(parents=True, exist_ok=True)
        item = news_item("label-queue")
        assessment = self._assessment(item, 1, analyzer="structured_llm")
        with (root / "headlines.csv").open("w", encoding="utf-8", newline="") as stream:
            import csv

            writer = csv.DictWriter(stream, fieldnames=item.to_dict().keys())
            writer.writeheader()
            writer.writerow(item.to_dict())
        with (root / "assessments.csv").open("w", encoding="utf-8", newline="") as stream:
            import csv

            writer = csv.DictWriter(stream, fieldnames=assessment.to_dict().keys())
            writer.writeheader()
            writer.writerow(assessment.to_dict())
        queue = Path("tmp/test_phase4_labeling/queue.csv")
        build_labeling_queue(root.parent.parent, queue, sample_size=10)
        import csv

        with queue.open("r", encoding="utf-8", newline="") as stream:
            payload = list(csv.DictReader(stream))
        payload[0]["manual_label"] = "1"
        with queue.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=payload[0].keys())
            writer.writeheader()
            writer.writerows(payload)
        build_labeling_queue(root.parent.parent, queue, sample_size=10)
        evaluation = evaluate_labeling_queue(queue)
        self.assertEqual(evaluation["manually_labeled"], 1)
        self.assertEqual(evaluation["analyzers"]["llm_sentiment"]["accuracy"], 1.0)


if __name__ == "__main__":
    unittest.main()
