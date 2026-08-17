"""One-time HuggingFace downloads, used only by scripts/download_datasets.py.

Experiment runs never import this module — they read the committed files
under Dataset/ (see loaders.py). This keeps HF network access off the runtime
path entirely, so a fresh clone (e.g. on the TAMU cluster) works with zero
network access as long as Dataset/ was cloned too.

Deliberately does NOT use the `datasets` library's load_dataset(): on networks
with a TLS-inspecting proxy (as here), its "xet" transfer backend hangs
indefinitely instead of failing. Plain `requests` against the resolved
parquet URLs (via the datasets-server API) works fine once the OS trust
store is bridged in via `truststore` — the proxy's interception certificate
is trusted by Windows but absent from Python's bundled certifi, which is
what caused the hang.
"""

from __future__ import annotations

import io

import pandas as pd
import requests
import truststore

from fdpo.data.extraction import gsm8k_gold
from fdpo.data.loaders import Example

truststore.inject_into_ssl()

MMLU_SUBJECTS = (
    "college_mathematics",
    "philosophy",
    "high_school_biology",
    "econometrics",
    "computer_security",
    "professional_law",
)

_LETTERS = "ABCDE"
_PARQUET_API = "https://datasets-server.huggingface.co/parquet"


def _parquet_urls(dataset: str, config: str | None = None) -> dict[tuple[str, str], str]:
    """(config, split) -> resolved parquet URL, via the datasets-server API."""
    params = {"dataset": dataset}
    if config:
        params["config"] = config
    resp = requests.get(_PARQUET_API, params=params, timeout=30)
    resp.raise_for_status()
    return {(f["config"], f["split"]): f["url"] for f in resp.json()["parquet_files"]}


def _read_parquet_split(dataset: str, split: str, config: str | None = None) -> pd.DataFrame:
    urls = _parquet_urls(dataset, config)
    key = (config or next(iter(urls))[0], split)
    resp = requests.get(urls[key], timeout=60)
    resp.raise_for_status()
    return pd.read_parquet(io.BytesIO(resp.content))


def _format_mc(question: str, choices: list[str]) -> str:
    lines = [question.strip(), ""]
    for letter, text in zip(_LETTERS, choices):
        lines.append(f"{letter}. {text}")
    return "\n".join(lines)


def fetch_gsm8k() -> tuple[list[Example], list[Example]]:
    def convert(split: str) -> list[Example]:
        df = _read_parquet_split("openai/gsm8k", split, config="main")
        return [
            Example(
                id=f"gsm8k_{split}_{i}",
                question=row["question"],
                gold=gsm8k_gold(row["answer"]),
                reference=row["answer"],
            )
            for i, row in df.iterrows()
        ]

    return convert("train"), convert("test")


def fetch_arc() -> tuple[list[Example], list[Example]]:
    def convert(split: str) -> list[Example]:
        df = _read_parquet_split("allenai/ai2_arc", split, config="ARC-Challenge")
        out = []
        for i, row in df.iterrows():
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


def fetch_mmlu() -> tuple[list[Example], list[Example]]:
    train, test = [], []
    for subject in MMLU_SUBJECTS:
        for split, bucket in (("validation", train), ("dev", train), ("test", test)):
            df = _read_parquet_split("cais/mmlu", split, config=subject)
            for i, row in df.iterrows():
                gold = _LETTERS[int(row["answer"])]
                bucket.append(Example(
                    id=f"mmlu_{subject}_{split}_{i}",
                    question=_format_mc(row["question"], list(row["choices"])),
                    gold=gold,
                    reference=gold,
                    meta={"subject": subject},
                ))
    return train, test


def fetch_legalbench_hearsay() -> tuple[list[Example], list[Example]]:
    def convert(split: str) -> list[Example]:
        df = _read_parquet_split("nguha/legalbench", split, config="hearsay")
        return [
            Example(
                id=f"hearsay_{split}_{i}",
                question=(
                    "Is the following statement hearsay?\n\n"
                    f"Statement: {row['text']}"
                ),
                gold=row["answer"].strip().capitalize(),
                reference=row["answer"],
                # 'slice' is the upstream category (Standard hearsay /
                # Non-assertive conduct / Statement made in court /
                # Non-verbal hearsay / Not introduced to prove truth) --
                # the natural stratification key for splits & per-slice metrics.
                meta={"slice": row["slice"]} if "slice" in row.index else {},
            )
            for i, row in df.iterrows()
        ]

    return convert("train"), convert("test")


def fetch_legalbench_contract_nli() -> tuple[list[Example], list[Example]]:
    """LegalBench `contract_nli_explicit_identification`: does a contract clause
    require Confidential Information to be explicitly marked/identified as
    confidential? Binary Yes/No. One of the LegalBench contract_nli sub-tasks;
    overlaps the Trace2Policy contract_nli cross-domain probe."""
    def convert(split: str) -> list[Example]:
        df = _read_parquet_split("nguha/legalbench", split,
                                 config="contract_nli_explicit_identification")
        return [
            Example(
                id=f"contract_nli_{split}_{i}",
                question=(
                    "Does the following contract clause require that Confidential "
                    "Information be explicitly marked or identified as "
                    "confidential?\n\n"
                    f"Clause: {row['text']}"
                ),
                gold=row["answer"].strip().capitalize(),
                reference=row["answer"],
                meta={},
            )
            for i, row in df.iterrows()
        ]

    return convert("train"), convert("test")


FETCHERS = {
    "gsm8k": fetch_gsm8k,
    "arc": fetch_arc,
    "mmlu": fetch_mmlu,
    "legalbench_hearsay": fetch_legalbench_hearsay,
    "legalbench_contract_nli": fetch_legalbench_contract_nli,
}
