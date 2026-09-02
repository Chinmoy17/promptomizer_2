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
from fdpo.data.ifeval_verifiers import describe_requirements
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


def _jsonable(obj):
    """Recursively convert numpy/pandas containers (ndarray, np.generic) to
    plain Python types so json.dumps() accepts them -- IFEval/IFBench's
    `kwargs` column comes back from parquet with numpy arrays nested inside
    dicts (e.g. a forbidden-words list), which plain dict()/list() casts
    don't reach."""
    if isinstance(obj, dict):
        return {k: _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if hasattr(obj, "tolist"):  # numpy ndarray or scalar (np.generic)
        return _jsonable(obj.tolist())
    return obj


def fetch_ifeval() -> tuple[list[Example], list[Example]]:
    """google/IFEval: 541 verifiable-instruction prompts, single upstream
    split (no official train/test division -- like HumanEval's 0/164
    convention, everything goes to test; --split-mode stratified re-pools
    and re-carves train/test at experiment time, same as legalbench_hearsay).

    There is no single "gold answer" for this task -- correctness means
    every listed instruction_id passed its own verifier function against the
    raw output, not an extracted-answer-vs-gold match. `gold` is a
    placeholder; the real verification spec lives in `meta`. See
    `fdpo.data.ifeval_verifiers` for the (partial -- 18 of 83 distinct
    instruction types) checker implementation; `is_fully_covered()` filters
    the loaded pool at load time (see loaders.py) so only examples where
    every listed instruction has an implemented checker are ever scored."""
    df = _read_parquet_split("google/IFEval", "train")
    test = [
        Example(
            id=f"ifeval_{row['key']}",
            question=row["prompt"],
            gold="PASS",
            reference=describe_requirements(
                list(row["instruction_id_list"]), _jsonable(list(row["kwargs"]))),
            meta=_jsonable({
                "instruction_id_list": row["instruction_id_list"],
                "kwargs": row["kwargs"],
            }),
        )
        for _, row in df.iterrows()
    ]
    return [], test


def fetch_ifbench() -> tuple[list[Example], list[Example]]:
    """allenai/IFBench_test: 300 out-of-domain verifiable-instruction prompts
    (58 new constraint types beyond IFEval), same single-split/no-gold
    situation as fetch_ifeval() above -- see its docstring."""
    df = _read_parquet_split("allenai/IFBench_test", "train")
    test = [
        Example(
            id=f"ifbench_{row['key']}",
            question=row["prompt"],
            gold="PASS",
            reference=describe_requirements(
                list(row["instruction_id_list"]), _jsonable(list(row["kwargs"]))),
            meta=_jsonable({
                "instruction_id_list": row["instruction_id_list"],
                "kwargs": row["kwargs"],
            }),
        )
        for _, row in df.iterrows()
    ]
    return [], test


def fetch_aime() -> tuple[list[Example], list[Example]]:
    """AIME competition math, split exactly as GEPA's own protocol: train =
    AIME 2022-2024 (AI-MO/aimo-validation-aime, 90 problems), test = AIME
    2025 (opencompass/AIME2025, 30 problems across its I/II configs). Kept
    as the OFFICIAL train/test boundary (no re-pooling) so numbers are
    directly comparable to GEPA's table -- use --split-mode seeded (the
    default), never stratified/balanced, which would pool train+test
    together and erase that boundary.

    Answers are integers 0-999; reuses gsm8k's "#### <number>" extractor
    (see fdpo.data.extraction) rather than a new format."""
    train_df = _read_parquet_split("AI-MO/aimo-validation-aime", "train")
    train = [
        Example(
            id=f"aime_train_{row['id']}",
            question=row["problem"],
            gold=str(row["answer"]).strip(),
            reference=row["solution"],
            meta={},
        )
        for _, row in train_df.iterrows()
    ]

    test: list[Example] = []
    for config in ("AIME2025-I", "AIME2025-II"):
        test_df = _read_parquet_split("opencompass/AIME2025", "test", config=config)
        for i, row in test_df.iterrows():
            test.append(Example(
                id=f"aime_test_{config}_{i}",
                question=row["question"],
                gold=str(row["answer"]).strip(),
                reference=str(row["answer"]),
                meta={},
            ))
    return train, test


def fetch_pupa() -> tuple[list[Example], list[Example]]:
    """Columbia-NLP/PUPA (PAPILLON paper): privacy-conscious delegation data.
    Two upstream configs, each a single unsplit "train" rows-bag (no official
    train/test division, like IFEval/IFBench above) -- PUPA-TNB (237 rows,
    from the Trust No Bot annotations) and PUPA-New (664 rows, from WildChat).
    All 901 rows go to `test`; --split-mode stratified/balanced re-pools and
    re-carves train/test at experiment time.

    This is data-only in the sense that no HF network access happens outside
    this fetch step; the evaluator/optimizer pipeline for PUPA lives in
    fdpo.data.pupa_pipeline (see reflect_loop.py's judge/external threading).
    PUPA's task is a two-hop pipeline (redact query -> query an untrusted
    external model -> synthesize final response), scored by a CONTINUOUS
    composite (quality judge + mechanical PII-leakage fraction) -- not a
    boolean pass/fail like IFEval/IFBench, and not a single
    extracted-answer-vs-gold match. `gold` is deliberately "N/A": it is
    unused by design, not a stand-in for a pass/fail verdict."""
    def _str_or_empty(v) -> str:
        # Some rows have no PII units / no redacted_query recorded upstream;
        # pandas reads that as NaN (a float), not "" -- .split()/.lower() on
        # a NaN crashes downstream in pupa_pipeline.compute_leakage().
        return "" if pd.isna(v) else str(v)

    test: list[Example] = []
    for config in ("pupa_new", "pupa_tnb"):
        df = _read_parquet_split("Columbia-NLP/PUPA", "train", config=config)
        for i, row in df.iterrows():
            test.append(Example(
                id=f"pupa_{config}_{i}",
                question=_str_or_empty(row["user_query"]),
                gold="N/A",
                reference=_str_or_empty(row["target_response"]),
                meta={
                    "subset": config,
                    "conversation_hash": _str_or_empty(row["conversation_hash"]),
                    "predicted_category": _str_or_empty(row["predicted_category"]),
                    "pii_units": _str_or_empty(row["pii_units"]),
                    "redacted_query": _str_or_empty(row["redacted_query"]),
                },
            ))
    return [], test


FETCHERS = {
    "gsm8k": fetch_gsm8k,
    "arc": fetch_arc,
    "mmlu": fetch_mmlu,
    "legalbench_hearsay": fetch_legalbench_hearsay,
    "legalbench_contract_nli": fetch_legalbench_contract_nli,
    "ifeval": fetch_ifeval,
    "ifbench": fetch_ifbench,
    "aime": fetch_aime,
    "pupa": fetch_pupa,
}
