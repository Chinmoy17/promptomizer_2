# FDPO Pilot — Progress Log

> Status as of 2026-07-04. This file tracks WHAT HAS BEEN BUILT and WHAT'S LEFT.
> For the experiment design and rationale, see [plan.md](plan.md).
> For the research proposal and algorithm, see [Docs/proposal.md](Docs/proposal.md)
> and [Docs/fdpo_experiment_plan.md](Docs/fdpo_experiment_plan.md).

## The plan, in one paragraph

FDPO optimizes a prompt by splitting it into 5 semantic sections, using an LLM
judge to blame failures on a specific section, rewriting only that section, and
gating every rewrite with a regression check before committing (rollback
otherwise). The full research program (8 datasets, 9 models, 11 baselines) is
too expensive to run alone, so it's split across two sites: **this machine**
runs a **$25 smoke test** with OpenAI models (gpt-4o-mini solver, gpt-4o
judge/optimizer) on GSM8K + ARC-Challenge; **Prof. Tarek Mahmud's group at
Texas A&M** will clone this repo and run open models (Llama-3-8B, Qwen3-8B,
DeepSeek) on their cluster, using the exact same code with only `.env` changed.
Optimization is **offline batch rounds only** for now — no online/τ-triggered
streaming (that's deferred as a future ablation).

## Course correction (2026-07-04)

Datasets were initially fetched straight from HuggingFace into the local HF
cache at run time (not stored in the repo). You flagged this as wrong — your
FL-for-Aircraft repo commits its raw data (`Dataset/CMAPSS_NASA/`), and you'd
already asked for a dataset folder once before. Fixed: datasets are now
fetched **once** via `scripts/download_datasets.py` and committed to
`Dataset/<name>/{train,test}.jsonl`; experiment runs read only from that
folder and never call HuggingFace. This also sidesteps the slow/rate-limited
unauthenticated HF downloads we were hitting.

## Status: scaffold complete, pre-first-live-run

| Milestone | Status | Notes |
|---|---|---|
| M1 — Scaffold (uv, pyproject, config, utils) | ✅ Done | Python 3.12.10 pinned; `uv run python -m pytest` green |
| M2 — Model clients + budget guard | ✅ Done | OpenAI-compatible client, mock client, HF stub, price table + hard budget cap |
| M3 — Dataset loaders + extraction | ✅ Done | GSM8K (7473/1319), ARC-Challenge (1119/1172), LegalBench-hearsay (5/94) fetched into `Dataset/`; MMLU loader ready but not yet fetched (not needed for the $25 smoke matrix) |
| M4 — Prompt schema + registry | ✅ Done | 5-section + monolithic schemas; full version/archive/best-snapshot state machine |
| M5 — Judge / optimizer / gate | ✅ Done | JSON-mode parsing with retry+fallback; regression gate with rolling correct-pool |
| M6 — Offline batch loop + baselines + entry point | ✅ Done | `run_experiment.py` runs all 4 methods end-to-end |
| M7 — Smoke orchestrator + README | 🔶 In progress | `run_smoke.py` + `build_results_summary.py` written and dry-run tested; README written; **live API run not yet done** |
| M8 — Live micro-run (~$1) | ⬜ Not started | Needs `.env` filled in with a real OpenAI key |
| M9 — $25 smoke run | ⬜ Not started | Blocked on M8 |

**64 automated tests pass**, all offline (mock client — zero API calls, zero cost).
A full dry-run of the 8-run smoke matrix (2 datasets × 4 methods) completed
successfully end-to-end with $0 spent, proving the whole pipeline wires together
(judge attribution → section rewrite → regression gate → commit/rollback →
`metrics.json`).

### Known issues / blockers

1. **`.env` does not exist yet.** Nothing can call a real OpenAI model until
   you run `Copy-Item .env.example .env` and paste in an API key.
2. **`Dataset/` is populated but not yet committed to git.** GSM8K,
   ARC-Challenge, and LegalBench-hearsay are all on disk under `Dataset/`
   (see table above) — needs a `git add Dataset/` + commit so TAMU gets
   identical data via `git clone`, no HF access needed on their end.
3. No `results/` yet — nothing has been committed there because no real run
   has happened.

## What "done" means for each piece (so you can sanity-check it yourself)

- **Config** (`src/fdpo/config.py`): every experiment parameter (dataset,
  train/test size, number of optimization rounds, regression threshold ρ,
  budget cap, seed, ...) is a `--flag`; run `uv run python -m
  scripts.run_experiment --help` to see all of them. Model choice/endpoint/key
  live in `.env`, never in code or committed configs.
- **Clients** (`src/fdpo/clients/`): one abstract interface (`ModelClient`)
  with three implementations — a real OpenAI-compatible client (works for
  OpenAI, vLLM, Ollama, Together, DeepSeek's API — anything speaking the
  OpenAI protocol), a mock client for tests/dry-runs, and a documented stub for
  direct HuggingFace-transformers loading if TAMU ever needs it instead of a
  vLLM server.
- **Budget guard** (`src/fdpo/utils/budget.py`): every single API call is
  priced from a lookup table and logged; if cumulative spend hits the cap
  mid-run, the run stops immediately, writes out everything it has so far with
  `status="budget_aborted"`, and exits cleanly — it will never overspend.
- **Data + extraction** (`src/fdpo/data/`): `hf_fetch.py` pulls
  GSM8K/ARC/MMLU/LegalBench from HuggingFace **once**, via
  `scripts/download_datasets.py`, into committed `Dataset/<name>/*.jsonl`
  files; `loaders.py` reads only those committed files at run time (no HF
  calls during an experiment) with a seeded shuffle, so the same `--seed`
  always produces the same train/test examples on any machine — and since the
  data itself is committed, you and TAMU see byte-identical examples via
  `git clone`, not two independent downloads. Regex-based answer extraction
  per dataset type (numeric `#### 42`, multiple-choice `Answer: B`, yes/no).
- **Prompt registry** (`src/fdpo/core/registry.py`): tracks every version of
  every section ever proposed (including rejected ones), which version is
  currently active, and the best-scoring version seen so far, all persisted to
  a JSON file after every change (crash-safe).
- **Judge** (`src/fdpo/core/judge.py`): asks an LLM to name which section
  caused a failure; if the LLM's JSON response is malformed, it's given one
  corrective retry, then falls back to "no attribution" rather than crashing
  the run.
- **Optimizer + Gate** (`src/fdpo/core/optimizer.py`, `gate.py`): the optimizer
  rewrites one section using sampled failures + correct examples; the gate
  then re-runs the OLD and NEW prompts on a batch of previously-correct
  examples and only accepts the rewrite if accuracy doesn't drop more than ρ
  (default 2%).
- **The loop** (`src/fdpo/core/loop.py`): ties it all together for a fixed
  number of rounds, with early stopping once accuracy stabilizes.
- **Baselines** (`src/fdpo/baselines/cot.py`) and the **entry point**
  (`scripts/run_experiment.py`): zero-shot CoT, few-shot CoT, and
  "monolithic-FDPO" (same loop, but one undivided prompt instead of 5
  sections) all share the exact same data/eval/results code as FDPO, so
  comparisons are apples-to-apples.

## Project structure (annotated)

```
PromtoMizer_2/
├── plan.md                    # the experiment design doc (scope, budget, milestones)
├── progress.md                # this file — what's built vs. what's left
├── README.md                  # setup + run instructions (for you AND TAMU)
├── pyproject.toml             # uv-managed deps: openai, python-dotenv, datasets, pytest
├── .python-version            # pins Python 3.12.10
├── .env.example                # template for API keys/endpoints — copy to .env, never commit .env
├── .gitignore                  # excludes .env, .venv, raw call logs
│
├── Dataset/                     # committed benchmark data (fetched once, see scripts/download_datasets.py)
│   ├── gsm8k/{train,test}.jsonl
│   ├── arc_challenge/{train,test}.jsonl
│   ├── mmlu/{train,test}.jsonl
│   └── legalbench_hearsay/{train,test}.jsonl
│
├── Docs/                       # the research proposal + literature survey (pre-existing)
│   ├── proposal.md             #   full FDPO method + experimental design write-up
│   ├── fdpo_experiment_plan.md #   the concrete algorithm/dataset/model plan this code implements
│   ├── literature_survey.md    #   30+ method academic survey
│   ├── related_works.md        #   focused competitor comparison (MPO, aPSF, Trace2Policy)
│   └── prompt_optimization_literature_study.md
│
├── src/fdpo/                   # the installable package — all the actual logic
│   ├── config.py                #  ExperimentConfig: every --flag, plus .env role loading
│   ├── clients/                 #  "talk to a model" — one interface, three backends
│   │   ├── base.py               #    ModelClient ABC — every call is metered here
│   │   ├── openai_client.py      #    real client: OpenAI API / vLLM / Ollama / DeepSeek / Together
│   │   ├── mock_client.py        #    fake client for tests and --dry-run (no cost, no network)
│   │   └── hf_client.py          #    STUB for TAMU if they need direct GPU loading instead of vLLM
│   ├── data/                    #  "get the benchmark examples"
│   │   ├── hf_fetch.py            #    HuggingFace fetch logic — used ONLY by download_datasets.py
│   │   ├── loaders.py             #    reads committed Dataset/*.jsonl, seeded subsampling
│   │   └── extraction.py          #    turn raw model text into a gradeable answer (regex-based)
│   ├── core/                    #  the FDPO algorithm itself
│   │   ├── prompt.py               #    5-section / monolithic schemas, message rendering
│   │   ├── registry.py             #    version history per section: active/archived/rejected, best-snapshot
│   │   ├── judge.py                #    "which section caused this failure?" + JSON parsing/retry
│   │   ├── optimizer.py            #    rewrite one section from failures + gold examples
│   │   ├── gate.py                 #    regression check: does the rewrite break previously-correct cases?
│   │   └── loop.py                 #    the offline batch round loop (judge → optimize → gate → commit)
│   ├── baselines/cot.py         #  zero-shot / few-shot CoT prompt builders (no optimization)
│   ├── eval/                    #  scoring
│   │   ├── evaluator.py           #    run the solver over examples, verdict programmatically
│   │   └── metrics.py             #    accuracy/EM/F1 + the 4 novel FDPO metrics (regression rate, etc.)
│   ├── prompts/                 #  the actual text templates
│   │   ├── seeds.py                #    starting (version-0) prompt for each dataset
│   │   ├── judge_prompt.py         #    instructs the judge model
│   │   └── optimizer_prompt.py     #    instructs the optimizer model
│   └── utils/
│       ├── budget.py               #    price table, token ledger, hard spend cap
│       ├── io.py                   #    run folders, crash-safe JSON writes, CSV logs
│       └── log.py                  #    console + per-run log file
│
├── scripts/                    # thin CLI entry points (argparse, no business logic)
│   ├── download_datasets.py     #  one-time HF fetch -> Dataset/<name>/{train,test}.jsonl (commit result)
│   ├── run_experiment.py        #  run ONE (method × dataset × seed) — the main entry point
│   ├── run_smoke.py             #  run the whole $25 Phase-0 matrix (2 datasets × 4 methods) under one cap
│   └── build_results_summary.py #  roll every run's metrics.json into results/summary.json
│
├── tests/                      # 64 tests, ALL offline (mock client, no API calls, no cost)
│   ├── test_scaffold.py         #  package imports, config defaults
│   ├── test_budget.py           #  price table, ledger math, budget cap enforcement
│   ├── test_extraction.py       #  answer-extraction regexes, edge cases, verdict logic
│   ├── test_registry.py         #  version commit/reject/rollback, JSON round-trip
│   ├── test_judge_parsing.py    #  valid/malformed/retry/fallback JSON handling
│   ├── test_gate.py             #  regression pass/fail arithmetic, cold-start, pool FIFO
│   ├── test_loop_mock.py        #  full end-to-end run on every method, budget-abort path
│   └── test_summary.py          #  results roll-up across multiple runs
│
└── results/                    # created at runtime — NOT present yet (no real run has happened)
    └── <phase>/<run_id>/         per-run metrics.json, config.json, registry.json, CSV logs
```

## Next steps (in order)

1. **You**: `Copy-Item .env.example .env`, paste your OpenAI API key into the
   `SOLVER_API_KEY` / `JUDGE_API_KEY` / `OPTIMIZER_API_KEY` lines (same key
   works for all three roles).
2. **Me**: run a ~$1 live micro-run (`--n-train 10 --n-test 10 --max-rounds 2
   --budget-usd 1`) and check the token ledger against your OpenAI usage
   dashboard.
3. **Me**: run the real $25 smoke matrix (`uv run python -m scripts.run_smoke
   --budget-usd 25`) and hand you `results/summary.json`.
4. **You + Prof. Mahmud**: push to GitHub; TAMU clones, points `.env` at their
   vLLM server, and reruns the identical commands for the open models.
