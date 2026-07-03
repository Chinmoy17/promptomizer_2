"""HuggingFace dataset loaders with deterministic seeded subsampling.

Each loader returns (train_pool, test_pool) of Example objects; subsampling
to n_train / n_test happens in load_splits() with a seeded shuffle so any
machine with the same seed sees the same example ids.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from fdpo.data.extraction import gsm8k_gold

MMLU_SUBJECTS = (
    "college_mathematics",
    "philosophy",
    "high_school_biology",
    "econometrics",
    "computer_security",
    "professional_law",
)

_LETTERS = "ABCDE"


@dataclass
class Example:
    id: str
    question: str          # fully formatted question (choices included for MC)
    gold: str              # normalized gold answer (number / letter / Yes|No)
    reference: str = ""    # full reference solution if available (for the judge)
    meta: dict = field(default_factory=dict)


def _hf_load(*args, **kwargs):
    from datasets import load_dataset  # lazy: offline tests never import HF
    return load_dataset(*args, **kwargs)


def _format_mc(question: str, choices: list[str]) -> str:
    lines = [question.strip(), ""]
    for letter, text in zip(_LETTERS, choices):
        lines.append(f"{letter}. {text}")
    return "\n".join(lines)


def _load_gsm8k() -> tuple[list[Example], list[Example]]:
    ds = _hf_load("openai/gsm8k", "main")

    def convert(split: str) -> list[Example]:
        return [
            Example(
                id=f"gsm8k_{split}_{i}",
                question=row["question"],
                gold=gsm8k_gold(row["answer"]),
                reference=row["answer"],
            )
            for i, row in enumerate(ds[split])
        ]

    return convert("train"), convert("test")


def _load_arc() -> tuple[list[Example], list[Example]]:
    ds = _hf_load("allenai/ai2_arc", "ARC-Challenge")

    def convert(split: str) -> list[Example]:
        out = []
        for i, row in enumerate(ds[split]):
            labels = list(row["choices"]["label"])
            texts = list(row["choices"]["text"])
            if row["answerKey"] not in labels:
                continue
            gold = _LETTERS[labels.index(row["answerKey"])]
            out.append(Example(
                id=f"arc_{split}_{i}",
                question=_format_mc(row["question"], texts),
                gold=gold,
                reference=gold,
            ))
        return out

    return convert("train"), convert("test")


def _load_mmlu() -> tuple[list[Example], list[Example]]:
    train, test = [], []
    for subject in MMLU_SUBJECTS:
        ds = _hf_load("cais/mmlu", subject)
        for split, bucket in (("validation", train), ("dev", train), ("test", test)):
            for i, row in enumerate(ds[split]):
                gold = _LETTERS[int(row["answer"])]
                bucket.append(Example(
                    id=f"mmlu_{subject}_{split}_{i}",
                    question=_format_mc(row["question"], list(row["choices"])),
                    gold=gold,
                    reference=gold,
                    meta={"subject": subject},
                ))
    return train, test


def _load_legalbench_hearsay() -> tuple[list[Example], list[Example]]:
    ds = _hf_load("nguha/legalbench", "hearsay")

    def convert(split: str) -> list[Example]:
        return [
            Example(
                id=f"hearsay_{split}_{i}",
                question=(
                    "Is the following statement hearsay?\n\n"
                    f"Statement: {row['text']}"
                ),
                gold=row["answer"].strip().capitalize(),
                reference=row["answer"],
            )
            for i, row in enumerate(ds[split])
        ]

    return convert("train"), convert("test")


_LOADERS = {
    "gsm8k": _load_gsm8k,
    "arc": _load_arc,
    "mmlu": _load_mmlu,
    "legalbench_hearsay": _load_legalbench_hearsay,
}


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


def load_splits(dataset: str, n_train: int, n_test: int,
                seed: int) -> tuple[list[Example], list[Example]]:
    """Deterministic (train, test) subsamples.

    If the official train pool is too small (LegalBench hearsay has ~5 train
    examples), the shortfall is carved from the shuffled test pool BEFORE the
    test subsample is taken, so train and test never overlap.
    """
    train_pool, test_pool = _LOADERS[dataset]()
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
