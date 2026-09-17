"""Normalización y controles de calidad para series OHLCV."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd


REQUIRED_OHLCV_COLUMNS = ("Open", "High", "Low", "Close", "Volume")


class DataValidationError(ValueError):
    """Indica que un dataset no cumple el contrato de calidad."""


@dataclass(frozen=True)
class DataQualityReport:
    """Resultado auditable de los controles de calidad."""

    valid: bool
    row_count: int
    start_date: str | None
    end_date: str | None
    duplicate_timestamps: int
    missing_values: dict[str, int]
    non_positive_price_rows: int
    negative_volume_rows: int
    invalid_ohlc_rows: int
    errors: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _flatten_columns(frame: pd.DataFrame, ticker: str | None) -> pd.DataFrame:
    if not isinstance(frame.columns, pd.MultiIndex):
        return frame

    level_zero = set(str(item) for item in frame.columns.get_level_values(0))
    if set(REQUIRED_OHLCV_COLUMNS).issubset(level_zero):
        frame.columns = frame.columns.get_level_values(0)
        return frame

    if ticker and ticker in frame.columns.get_level_values(-1):
        return frame.xs(ticker, axis=1, level=-1, drop_level=True)

    raise DataValidationError(
        "No fue posible identificar un único activo en las columnas MultiIndex."
    )


def normalizar_ohlcv(frame: pd.DataFrame, ticker: str | None = None) -> pd.DataFrame:
    """Estandariza columnas, índice temporal y tipos numéricos de un dataset OHLCV."""
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise DataValidationError("El proveedor devolvió un dataset vacío.")

    data = _flatten_columns(frame.copy(), ticker)
    aliases = {str(column).strip().lower(): column for column in data.columns}
    rename: dict[Any, str] = {}
    for required in REQUIRED_OHLCV_COLUMNS:
        original = aliases.get(required.lower())
        if original is not None:
            rename[original] = required
    data = data.rename(columns=rename)

    missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in data.columns]
    if missing_columns:
        raise DataValidationError(
            f"Faltan columnas OHLCV obligatorias: {', '.join(missing_columns)}."
        )

    data = data.loc[:, list(REQUIRED_OHLCV_COLUMNS)]
    try:
        temporal_index = pd.to_datetime(data.index, utc=True, errors="raise")
    except (TypeError, ValueError) as exc:
        raise DataValidationError("El índice del dataset no contiene fechas válidas.") from exc

    data.index = temporal_index.tz_convert(None)
    data.index.name = "Date"
    for column in REQUIRED_OHLCV_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    return data.sort_index()


def validar_ohlcv(
    frame: pd.DataFrame,
    *,
    min_rows: int = 2,
    max_missing_ratio: float = 0.0,
    raise_on_error: bool = True,
) -> DataQualityReport:
    """Valida integridad temporal, completitud y coherencia de precios OHLCV."""
    errors: list[str] = []
    warnings: list[str] = []
    row_count = len(frame)

    missing_columns = [column for column in REQUIRED_OHLCV_COLUMNS if column not in frame.columns]
    if missing_columns:
        errors.append(f"Faltan columnas: {', '.join(missing_columns)}")
        report = DataQualityReport(
            valid=False, row_count=row_count, start_date=None, end_date=None,
            duplicate_timestamps=0,
            missing_values={column: row_count for column in missing_columns},
            non_positive_price_rows=0, negative_volume_rows=0,
            invalid_ohlc_rows=0, errors=tuple(errors), warnings=tuple(warnings),
        )
        if raise_on_error:
            raise DataValidationError("; ".join(errors))
        return report

    if row_count < min_rows:
        errors.append(f"Se requieren al menos {min_rows} filas y se recibieron {row_count}.")

    duplicate_timestamps = int(frame.index.duplicated(keep=False).sum())
    if duplicate_timestamps:
        errors.append(f"Hay {duplicate_timestamps} filas con fechas duplicadas.")
    if not frame.index.is_monotonic_increasing:
        errors.append("El índice temporal no está ordenado de forma ascendente.")

    missing_values = {
        column: int(frame[column].isna().sum()) for column in REQUIRED_OHLCV_COLUMNS
    }
    for column, count in missing_values.items():
        ratio = count / row_count if row_count else 1.0
        if ratio > max_missing_ratio:
            errors.append(
                f"{column} supera el máximo de faltantes ({ratio:.2%} > {max_missing_ratio:.2%})."
            )
        elif count:
            warnings.append(f"{column} contiene {count} valores faltantes.")

    prices = frame[["Open", "High", "Low", "Close"]]
    non_positive_price_rows = int((prices <= 0).any(axis=1).sum())
    if non_positive_price_rows:
        errors.append(f"Hay {non_positive_price_rows} filas con precios no positivos.")

    negative_volume_rows = int((frame["Volume"] < 0).sum())
    if negative_volume_rows:
        errors.append(f"Hay {negative_volume_rows} filas con volumen negativo.")

    invalid_ohlc = (
        (frame["High"] < frame[["Open", "Close", "Low"]].max(axis=1))
        | (frame["Low"] > frame[["Open", "Close", "High"]].min(axis=1))
    )
    invalid_ohlc_rows = int(invalid_ohlc.sum())
    if invalid_ohlc_rows:
        errors.append(f"Hay {invalid_ohlc_rows} filas con relaciones OHLC inválidas.")

    start_date = frame.index.min().isoformat() if row_count else None
    end_date = frame.index.max().isoformat() if row_count else None
    report = DataQualityReport(
        valid=not errors, row_count=row_count, start_date=start_date,
        end_date=end_date, duplicate_timestamps=duplicate_timestamps,
        missing_values=missing_values,
        non_positive_price_rows=non_positive_price_rows,
        negative_volume_rows=negative_volume_rows,
        invalid_ohlc_rows=invalid_ohlc_rows, errors=tuple(errors),
        warnings=tuple(warnings),
    )
    if errors and raise_on_error:
        raise DataValidationError("; ".join(errors))
    return report
