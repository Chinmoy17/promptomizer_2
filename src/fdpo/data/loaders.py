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

import logging
import random
from dataclasses import dataclass, field
from pathlib import Path

from fdpo.utils.io import read_jsonl

logger = logging.getLogger("fdpo")

DATASET_DIRS = {
    "gsm8k": "gsm8k",
    "arc": "arc_challenge",
    "mmlu": "mmlu",
    "legalbench_hearsay": "legalbench_hearsay",
    "legalbench_contract_nli": "legalbench_contract_nli",
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
                dataset_root: str,
                subjects: tuple[str, ...] = ()) -> list[Example]:
    path = Path(dataset_root) / DATASET_DIRS[dataset] / f"{split}.jsonl"
    if not path.exists():
        raise FileNotFoundError(
            f"{path} not found. Fetch datasets first:\n"
            f"    uv run python -m scripts.download_datasets --dataset {dataset}"
        )
    rows = [Example(**row) for row in read_jsonl(path)]
    if subjects:
        rows = [e for e in rows if (e.meta or {}).get("subject") in subjects]
    return rows


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
            elif dataset in ("legalbench_hearsay", "legalbench_contract_nli"):
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


def _stratum_key(ex: Example) -> str:
    """Preferred stratification key. Falls back through common category-label
    field names in meta (`slice`, `subject`, `category`) before defaulting to
    the gold answer -- so LegalBench uses its `slice`, MMLU uses `subject`,
    and datasets without any category metadata (GSM8K, ARC) fall back to the
    gold label."""
    if ex.meta:
        for key in ("slice", "subject", "category"):
            if key in ex.meta:
                return ex.meta[key]
    return ex.gold


def _stratified_take(pool: list[Example], n: int, rng: random.Random,
                     ) -> tuple[list[Example], list[Example]]:
    """Take n examples from pool, stratified by `_stratum_key`, using
    proportional allocation with rounding-drift correction.
    Returns (selected, remainder). Deterministic under a fixed `rng`.
    """
    if n >= len(pool):
        shuffled = pool.copy()
        rng.shuffle(shuffled)
        return shuffled, []

    strata: dict[str, list[Example]] = {}
    for e in pool:
        strata.setdefault(_stratum_key(e), []).append(e)
    stratum_names = sorted(strata)  # deterministic iteration order

    total = len(pool)
    # Proportional allocation (rounded)
    allocated = {k: round(n * len(strata[k]) / total) for k in stratum_names}

    # Correct for rounding drift by adjusting the largest strata first.
    order_by_size = sorted(stratum_names, key=lambda k: -len(strata[k]))
    diff = n - sum(allocated.values())
    i = 0
    guard = 100 * max(len(order_by_size), 1)
    while diff != 0 and i < guard:
        k = order_by_size[i % len(order_by_size)]
        if diff > 0 and allocated[k] < len(strata[k]):
            allocated[k] += 1
            diff -= 1
        elif diff < 0 and allocated[k] > 0:
            allocated[k] -= 1
            diff += 1
        i += 1

    selected: list[Example] = []
    remainder: list[Example] = []
    for k in stratum_names:
        exs = strata[k].copy()
        rng.shuffle(exs)
        selected.extend(exs[: allocated[k]])
        remainder.extend(exs[allocated[k]:])
    return selected, remainder


def load_splits(dataset: str, n_train: int, n_test: int, seed: int,
                dataset_root: str = DEFAULT_DATASET_ROOT,
                split_mode: str = "seeded",
                subjects: tuple[str, ...] = (),
                ) -> tuple[list[Example], list[Example]]:
    """Deterministic (train, test) subsamples read from the committed
    Dataset/ folder.

    `split_mode`:
      - "seeded" (default, backward-compatible): random shuffle by seed;
        train/test composition varies per seed.
      - "stratified": pool train + test, stratify by `meta['slice']` (or gold
        as fallback), carve TEST with a FIXED rng (seed=0) so test is
        identical across user seeds, then carve TRAIN from the remainder
        using the user seed. Strongly recommended for legalbench_hearsay
        (5 semantic slices) — removes cross-seed test-composition variance.
      - "balanced": like stratified, but `n_train`/`n_test` are PER-STRATUM
        (per-subject) counts — equal per subject, no dominant stratum. Yields
        the standard MMLU macro-average. Test is fixed across seeds.
    """
    if split_mode == "stratified":
        return _load_splits_stratified(dataset, n_train, n_test, seed, dataset_root, subjects)
    if split_mode == "balanced":
        return _load_splits_balanced(dataset, n_train, n_test, seed, dataset_root, subjects)
    if split_mode != "seeded":
        raise ValueError(f"unknown split_mode: {split_mode!r} "
                         "(expected 'seeded', 'stratified', or 'balanced')")
    return _load_splits_seeded(dataset, n_train, n_test, seed, dataset_root, subjects)


def _load_splits_seeded(dataset: str, n_train: int, n_test: int, seed: int,
                        dataset_root: str, subjects: tuple[str, ...] = (),
                        ) -> tuple[list[Example], list[Example]]:
    """Original seeded split (unchanged behavior).

    If the official train pool is too small (LegalBench hearsay has ~5 train
    examples), the shortfall is carved from the shuffled test pool BEFORE the
    test subsample is taken, so train and test never overlap.
    """
    train_pool = _load_local(dataset, "train", dataset_root, subjects)
    test_pool = _load_local(dataset, "test", dataset_root, subjects)
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


def _load_splits_stratified(dataset: str, n_train: int, n_test: int, seed: int,
                            dataset_root: str, subjects: tuple[str, ...] = (),
                            ) -> tuple[list[Example], list[Example]]:
    """Pool official train + test, then take a FIXED stratified test set
    (rng seeded to 0 -- identical across user seeds) and a seed-dependent
    stratified train set from the remainder."""
    pool = (_load_local(dataset, "train", dataset_root, subjects)
            + _load_local(dataset, "test", dataset_root, subjects))
    if n_test + n_train > len(pool):
        # Trim train silently; test is the deterministic anchor and gets priority.
        n_train = max(0, len(pool) - n_test)

    fixed_rng = random.Random(0)  # test is fixed across user seeds
    test, remainder = _stratified_take(pool, n_test, fixed_rng)

    user_rng = random.Random(seed)
    train, _ = _stratified_take(remainder, n_train, user_rng)
    return train, test


def _load_splits_balanced(dataset: str, n_train: int, n_test: int, seed: int,
                          dataset_root: str, subjects: tuple[str, ...] = (),
                          ) -> tuple[list[Example], list[Example]]:
    """Balanced per-subject split. `n_train` and `n_test` are PER-STRATUM
    (per-subject for MMLU) counts, NOT totals. Pools official train + test,
    groups by `_stratum_key`, and for each stratum carves a FIXED test set
    (rng=0, identical across user seeds) then a seed-dependent train set from
    the remainder. This removes the dominant-stratum problem (MMLU
    professional_law is ~60% of a proportional sample but 1/6 here) and gives
    the standard MMLU macro-average. Strata with too few pooled examples are
    capped with a warning so the run degrades gracefully instead of crashing.
    """
    pool = (_load_local(dataset, "train", dataset_root, subjects)
            + _load_local(dataset, "test", dataset_root, subjects))
    strata: dict[str, list[Example]] = {}
    for e in pool:
        strata.setdefault(_stratum_key(e), []).append(e)

    train: list[Example] = []
    test: list[Example] = []
    for key in sorted(strata):
        exs = strata[key].copy()
        random.Random(0).shuffle(exs)             # test carve fixed across seeds
        take_test = min(n_test, len(exs))
        s_test = exs[:take_test]
        remainder = exs[take_test:]
        random.Random(seed).shuffle(remainder)    # train carve varies per seed
        take_train = min(n_train, len(remainder))
        if take_test < n_test or take_train < n_train:
            logger.warning(
                "balanced split: stratum %r short -- train %d/%d, test %d/%d "
                "(pool=%d)", key, take_train, n_train, take_test, n_test, len(exs))
        train.extend(remainder[:take_train])
        test.extend(s_test)
    logger.info("balanced split: %d strata, %d train + %d test total "
                "(target %d/%d per stratum)", len(strata), len(train), len(test),
                n_train, n_test)
    return train, test
