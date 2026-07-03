"""Run directories, atomic JSON writes, and append-only CSV/JSONL logs."""

from __future__ import annotations

import csv
import json
import os
import re
import time
from pathlib import Path


def make_run_id(dataset: str, method: str, solver_model: str, seed: int) -> str:
    model_slug = re.sub(r"[^a-zA-Z0-9.-]+", "-", solver_model)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return f"{dataset}_{method}_{model_slug}_s{seed}_{stamp}"


def ensure_run_dir(results_root: str | Path, phase: str, run_id: str) -> Path:
    run_dir = Path(results_root) / phase / run_id
    (run_dir / "calls").mkdir(parents=True, exist_ok=True)
    return run_dir


def atomic_write_json(path: str | Path, obj: dict) -> None:
    """Write JSON crash-safely: temp file in the same dir, then os.replace."""
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class CsvAppender:
    """Append rows to a CSV, writing the header on first use."""

    def __init__(self, path: str | Path, fieldnames: list[str]):
        self.path = Path(path)
        self.fieldnames = fieldnames
        if not self.path.exists():
            with open(self.path, "w", newline="", encoding="utf-8") as f:
                csv.DictWriter(f, fieldnames=fieldnames).writeheader()

    def append(self, row: dict) -> None:
        with open(self.path, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=self.fieldnames, extrasaction="ignore").writerow(row)


class JsonlAppender:
    """Append events to a JSONL file (gitignored; debugging aid)."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def append(self, obj: dict) -> None:
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")
