"""Logging: console always; per-run file handler when a run dir exists."""

from __future__ import annotations

import logging
from pathlib import Path


def setup_logging(run_dir: Path | None = None, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("fdpo")
    logger.setLevel(level)
    logger.handlers.clear()

    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%H:%M:%S")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    if run_dir is not None:
        fh = logging.FileHandler(Path(run_dir) / "run.log", encoding="utf-8")
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
        logger.addHandler(fh)

    return logger
