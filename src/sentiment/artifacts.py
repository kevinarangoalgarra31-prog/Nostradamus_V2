"""Persistencia trazable de una ejecución de sentimiento."""

from __future__ import annotations

import csv
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from .domain import NewsItem, SentimentAssessment, SentimentSignal
from .pipeline import NewsAuditBatch


@dataclass(frozen=True)
class SentimentRunArtifacts:
    headlines: Path
    rejected: Path
    assessments: Path
    signals: Path
    evaluation: Path
    manifest: Path


def _safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    return normalized.strip("_") or "sentiment"


def _write_json(path: Path, payload: Any) -> str:
    data = (json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> str:
    fieldnames = sorted({key for row in rows for key in row}) if rows else ["news_id"]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                    if isinstance(value, (dict, list, tuple))
                    else value
                    for key, value in row.items()
                }
            )
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save_sentiment_run(
    output_dir: str | Path,
    *,
    batch: NewsAuditBatch,
    assessments: Iterable[SentimentAssessment],
    signals: Iterable[SentimentSignal],
    evaluation: Mapping[str, Any],
    config: Mapping[str, Any],
    provider: str,
) -> SentimentRunArtifacts:
    """Guarda todos los insumos y modelos necesarios para reconstruir una señal."""
    directory = Path(output_dir) / _safe_name(batch.asset)
    directory.mkdir(parents=True, exist_ok=True)
    paths = SentimentRunArtifacts(
        headlines=directory / "headlines.csv",
        rejected=directory / "rejected.json",
        assessments=directory / "assessments.csv",
        signals=directory / "signals.json",
        evaluation=directory / "evaluation.json",
        manifest=directory / "run_manifest.json",
    )
    assessment_rows = [item.to_dict() for item in assessments]
    signal_rows = [item.to_dict() for item in signals]
    hashes = {
        "headlines.csv": _write_csv(paths.headlines, [item.to_dict() for item in batch.accepted]),
        "rejected.json": _write_json(paths.rejected, list(batch.rejected)),
        "assessments.csv": _write_csv(paths.assessments, assessment_rows),
        "signals.json": _write_json(paths.signals, signal_rows),
        "evaluation.json": _write_json(paths.evaluation, dict(evaluation)),
    }
    model_versions = sorted(
        {
            f"{row['analyzer']}:{row['model_name']}:{row['model_version']}"
            for row in assessment_rows
        }
    )
    _write_json(
        paths.manifest,
        {
            "schema_version": "4.0.0",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "asset": batch.asset,
            "decision_at": batch.decision_at.isoformat(),
            "provider": provider,
            "models": model_versions,
            "audit_metrics": dict(batch.metrics),
            "config": dict(config),
            "artifact_sha256": hashes,
        },
    )
    return paths
