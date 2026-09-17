"""CLI de las fases 1 y 2: definición, adquisición, calidad y características."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.config import load_experiment_config
from src.data_pipeline import (
    calcular_caracteristicas,
    cargar_datos_locales,
    descargar_datos,
    exportar_diccionario_datos,
    guardar_dataset_versionado,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara datasets auditables para Nostradamus V2 (fases 1 y 2)."
    )
    parser.add_argument(
        "--config",
        default="config/experiment.yaml",
        help="Definición experimental YAML.",
    )
    parser.add_argument(
        "--ticker",
        action="append",
        help="Limita la ejecución a uno o más tickers; se puede repetir.",
    )
    parser.add_argument(
        "--input-csv",
        help="Usa un CSV OHLCV local en lugar de descargar. Requiere un solo ticker.",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Valida y transforma sin escribir artefactos de datos.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    config = load_experiment_config(args.config)
    tickers = tuple(args.ticker or config.data.tickers)
    unknown = sorted(set(tickers) - set(config.data.tickers))
    if unknown:
        raise ValueError(
            "Los tickers solicitados no pertenecen al universo declarado: "
            + ", ".join(unknown)
        )
    if args.input_csv and len(tickers) != 1:
        raise ValueError("--input-csv requiere seleccionar exactamente un ticker.")

    summaries: list[dict[str, object]] = []
    for ticker in tickers:
        if args.input_csv:
            raw, quality = cargar_datos_locales(
                args.input_csv,
                ticker=ticker,
                min_filas=config.validation.min_rows,
                max_missing_ratio=config.validation.max_missing_ratio,
            )
            if not args.no_save:
                raw_artifact = guardar_dataset_versionado(
                    raw,
                    output_dir="data/raw",
                    dataset_kind="raw",
                    ticker=ticker,
                    source="local_csv",
                    interval=config.data.interval,
                    quality_report=quality,
                    metadata={"input_path": str(Path(args.input_csv).resolve())},
                )
                raw.attrs["artifact_path"] = str(raw_artifact.data_path)
                raw.attrs["manifest_path"] = str(raw_artifact.manifest_path)
        else:
            raw = descargar_datos(
                ticker=ticker,
                fecha_inicio=config.data.start_date.isoformat(),
                fecha_fin=(config.data.end_date.isoformat() if config.data.end_date else None),
                guardar_csv=not args.no_save,
                intervalo=config.data.interval,
                auto_adjust=config.data.auto_adjust,
                min_filas=config.validation.min_rows,
                max_missing_ratio=config.validation.max_missing_ratio,
            )

        processed = calcular_caracteristicas(
            raw,
            guardar_csv=not args.no_save,
            feature_config=config.features,
            target_config=config.target,
            ticker=ticker,
            source=config.data.source,
            intervalo=config.data.interval,
        )
        summaries.append(
            {
                "ticker": ticker,
                "raw_rows": len(raw),
                "processed_rows": len(processed),
                "raw_artifact": raw.attrs.get("artifact_path"),
                "processed_artifact": processed.attrs.get("artifact_path"),
                "processed_manifest": processed.attrs.get("manifest_path"),
            }
        )

    exportar_diccionario_datos(
        "docs/DICCIONARIO_DATOS.md",
        extra_columns=processed.columns if summaries else (),
    )
    print(json.dumps({"experiment": config.to_dict(), "datasets": summaries}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
