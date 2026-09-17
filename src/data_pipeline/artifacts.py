"""Persistencia versionada y trazable de datasets de Nostradamus V2."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from .validation import DataQualityReport


@dataclass(frozen=True)
class DatasetArtifact:
    """Rutas y huella de un dataset persistido."""

    data_path: Path
    manifest_path: Path
    sha256: str
    rows: int


def safe_name(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9_.]+", "_", value.strip())
    return normalized.strip("_") or "dataset"


def guardar_dataset_versionado(
    frame: pd.DataFrame,
    *,
    output_dir: str | Path,
    dataset_kind: str,
    ticker: str,
    source: str,
    interval: str,
    quality_report: DataQualityReport | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DatasetArtifact:
    """Guarda CSV y manifiesto JSON con nombre determinado por el contenido."""
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)

    csv_bytes = frame.to_csv(index=True, lineterminator="\n").encode("utf-8")
    digest = hashlib.sha256(csv_bytes).hexdigest()
    start = frame.index.min().strftime("%Y-%m-%d")
    end = frame.index.max().strftime("%Y-%m-%d")
    stem = safe_name(f"{ticker}_{interval}_{dataset_kind}_{start}_{end}_{digest[:12]}")
    data_path = directory / f"{stem}.csv"
    manifest_path = directory / f"{stem}.manifest.json"

    data_path.write_bytes(csv_bytes)
    manifest = {
        "schema_version": "1.0",
        "dataset_kind": dataset_kind,
        "source": source,
        "ticker": ticker,
        "interval": interval,
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(frame),
        "columns": list(frame.columns),
        "observed_start": frame.index.min().isoformat(),
        "observed_end": frame.index.max().isoformat(),
        "sha256": digest,
        "quality": quality_report.to_dict() if quality_report else None,
        "metadata": dict(metadata or {}),
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    return DatasetArtifact(data_path, manifest_path, digest, len(frame))
