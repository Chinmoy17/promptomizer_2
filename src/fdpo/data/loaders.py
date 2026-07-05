"""Dataset loading from the committed Dataset/ folder, with deterministic
seeded subsampling.

Datasets are fetched ONCE via `python -m scripts.download_datasets` and
committed to Dataset/<name>/{train,test}.jsonl (mirroring this project's
convention of shipping raw data in-repo). Experiment runs never touch
HuggingFace — this keeps runs fast, offline-capable, and byte-identical
between this machine and the TAMU cluster (both read the same committed
files instead of two independent HF downloads).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from fdpo.utils.io import read_jsonl

DATASET_DIRS = {
    "gsm8k": "gsm8k",
    "arc": "arc_challenge",
    "mmlu": "mmlu",
    "legalbench_hearsay": "legalbench_hearsay",
}

DEFAULT_DATASET_ROOT = "Dataset"


@dataclass
class Example:
    id: str
    question: str          # fully formatted question (choices included for MC)
    gold: str              # normalized gold answer (number / letter / Yes|No)
    reference: str = ""    # full reference solution if available (for the judge)
    meta: dict = field(default_factory=dict)


def _load_local(dataset: str, split: str,
                dataset_root: str) -> list[Example]:
    path = Path(dataset_root) / DATASET_DIRS[dataset] / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Fetch datasets first:\n"
            f"    uv run python -m scripts.download_datasets --dataset {dataset}"
        )
    return [Example(**row) for row in read_jsonl(path)]


def synthetic_splits(dataset: str, n_train: int,
                     n_test: int) -> tuple[list[Example], list[Example]]:
    """Tiny offline dataset for --dry-run: golds alternate so the mock solver
    (which always answers A / 42 / Yes) fails ~half the time, exercising the
    judge -> optimizer -> gate path without any network or API cost."""

    def make(split: str, n: int) -> list[Example]:
        out = []
        for i in range(n):
            if dataset == "gsm8k":
                gold = "42" if i % 2 == 0 else "41"
                out.append(Example(
                    id=f"syn_{split}_{i}",
                    question=f"Problem {i}: what is the total?",
                    gold=gold, reference=f"Reasoning...\n#### {gold}"))
            elif dataset == "legalbench_hearsay":
                gold = "Yes" if i % 2 == 0 else "No"
                out.append(Example(
                    id=f"syn_{split}_{i}",
                    question=f"Is statement {i} hearsay? Answer Yes or No.",
                    gold=gold, reference=gold))
            else:
                gold = "A" if i % 2 == 0 else "B"
                out.append(Example(
                    id=f"syn_{split}_{i}",
                    question=f"Question {i}?\n\nA. first\nB. second\nC. third",
                    gold=gold, reference=gold))
        return out

    return make("train", n_train), make("test", n_test)


def subsample(pool: list[Example], n: int, seed: int) -> list[Example]:
    rng = random.Random(seed)
    idx = list(range(len(pool)))
    rng.shuffle(idx)
    return [pool[i] for i in idx[: min(n, len(pool))]]


def load_splits(dataset: str, n_train: int, n_test: int, seed: int,
                dataset_root: str = DEFAULT_DATASET_ROOT
                ) -> tuple[list[Example], list[Example]]:
    """Deterministic (train, test) subsamples read from the committed
    Dataset/ folder.

    If the official train pool is too small (LegalBench hearsay has ~5 train
    examples), the shortfall is carved from the shuffled test pool BEFORE the
    test subsample is taken, so train and test never overlap.
    """
    train_pool = _load_local(dataset, "train", dataset_root)
    test_pool = _load_local(dataset, "test", dataset_root)
    train = subsample(train_pool, n_train, seed)

    rng = random.Random(seed + 1)
    idx = list(range(len(test_pool)))
    rng.shuffle(idx)
    shuffled_test = [test_pool[i] for i in idx]

    shortfall = n_train - len(train)
    if shortfall > 0:
        train = train + shuffled_test[:shortfall]
        shuffled_test = shuffled_test[shortfall:]

    test = shuffled_test[: min(n_test, len(shuffled_test))]
    return train, test
