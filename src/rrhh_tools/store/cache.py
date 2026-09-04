"""Persistencia de ejecuciones en disco."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

DATA_DIR = Path("data")


def run_dir(run_id: str) -> Path:
    return DATA_DIR / "runs" / run_id


def new_run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def save_raw(run_id: str, records: list[dict[str, Any]]) -> Path:
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "raw.json"
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2, default=str),
                    encoding="utf-8")
    return path


def load_raw(run_id: str) -> list[dict[str, Any]]:
    path = run_dir(run_id) / "raw.json"
    if not path.is_file():
        raise FileNotFoundError(f"No hay datos crudos para la ejecución {run_id}: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def latest_run_id() -> str:
    base = DATA_DIR / "runs"
    runs = sorted((d.name for d in base.iterdir() if d.is_dir()), reverse=True) if base.is_dir() else []
    if not runs:
        raise FileNotFoundError(
            "No hay ninguna ejecución guardada todavía. Lanza primero:  rrhh-tools search"
        )
    return runs[0]


def resolve_run(run: str) -> str:
    return latest_run_id() if run in ("latest", "ultima", "última") else run


def save_checkpoint(run_id: str, state: dict[str, Any]) -> None:
    directory = run_dir(run_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "checkpoint.json").write_text(
        json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def load_checkpoint(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "checkpoint.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
