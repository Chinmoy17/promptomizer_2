"""One-time fetch: HuggingFace -> committed Dataset/<name>/{train,test}.jsonl.

Run this once (or whenever a dataset needs refreshing) and commit the result.
Experiment runs never call HuggingFace directly (see src/fdpo/data/loaders.py)
so this is the only place the `datasets` library's network path is exercised.

Usage:
    uv run python -m scripts.download_datasets --dataset all
    uv run python -m scripts.download_datasets --dataset gsm8k arc
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from fdpo.data.hf_fetch import FETCHERS
from fdpo.data.loaders import DATASET_DIRS, DEFAULT_DATASET_ROOT
from fdpo.utils.io import write_jsonl
from fdpo.utils.log import setup_logging

ALL = tuple(FETCHERS)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dataset", nargs="+", choices=(*ALL, "all"), default=["all"])
    p.add_argument("--dataset-root", default=DEFAULT_DATASET_ROOT)
    args = p.parse_args(argv)

    logger = setup_logging()
    targets = ALL if "all" in args.dataset else tuple(args.dataset)
    root = Path(args.dataset_root)

    for name in targets:
        logger.info("fetching %s from HuggingFace ...", name)
        train, test = FETCHERS[name]()
        out_dir = root / DATASET_DIRS[name]
        write_jsonl(out_dir / "train.jsonl", [asdict(e) for e in train])
        write_jsonl(out_dir / "test.jsonl", [asdict(e) for e in test])
        logger.info("%s: wrote %d train / %d test examples -> %s",
                    name, len(train), len(test), out_dir)

    logger.info("done. Commit the Dataset/ folder so TAMU gets identical data.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
