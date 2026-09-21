"""Diarios JSONL encadenados para decisiones y liquidaciones de paper trading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


GENESIS_HASH = "0" * 64


def _canonical(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")


def _record_hash(record: Mapping[str, Any]) -> str:
    material = {key: value for key, value in record.items() if key != "record_hash"}
    return hashlib.sha256(_canonical(material)).hexdigest()


def read_hash_chain(path: str | Path) -> list[dict[str, Any]]:
    """Lee y valida que ninguna línea previa haya sido alterada o reordenada."""
    journal = Path(path)
    if not journal.exists():
        return []
    records: list[dict[str, Any]] = []
    previous = GENESIS_HASH
    for line_number, line in enumerate(journal.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON inválido en {journal}, línea {line_number}.") from exc
        if not isinstance(record, dict):
            raise ValueError(f"Registro inválido en {journal}, línea {line_number}.")
        if record.get("previous_hash") != previous:
            raise ValueError(f"Cadena rota en {journal}, línea {line_number}.")
        expected = _record_hash(record)
        if record.get("record_hash") != expected:
            raise ValueError(f"Huella inválida en {journal}, línea {line_number}.")
        records.append(record)
        previous = expected
    return records


def append_hash_record(path: str | Path, payload: Mapping[str, Any]) -> dict[str, Any]:
    """Añade un registro sin reescribir el historial y devuelve su huella."""
    if "record_hash" in payload or "previous_hash" in payload:
        raise ValueError("El payload no puede definir campos internos de la cadena.")
    journal = Path(path)
    records = read_hash_chain(journal)
    previous = records[-1]["record_hash"] if records else GENESIS_HASH
    record = {**dict(payload), "previous_hash": previous}
    record["record_hash"] = _record_hash(record)
    journal.parent.mkdir(parents=True, exist_ok=True)
    with journal.open("a", encoding="utf-8", newline="") as stream:
        stream.write(json.dumps(record, ensure_ascii=False, sort_keys=True, default=str) + "\n")
    return record
