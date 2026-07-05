# FDPO — Feedback-Driven Modular Prompt Optimization (Pilot)

Pilot experiments for **FDPO**: a prompt is treated as K semantic sections
(System Role / Context / Task Details / Constraints / Output Format), an LLM
judge attributes each failure to the responsible section, only that section is
rewritten, and every rewrite must pass a **per-section regression gate** before
commit (rollback otherwise).

- Current experiment plan: [plan.md](plan.md)
- Research proposal + literature survey: [Docs/](Docs/)
- Mode: **offline batch rounds** (no online/τ trigger yet — deferred ablation A10)

## Setup (Windows PowerShell)

Requires [uv](https://docs.astral.sh/uv/). Python 3.12.10 is pinned and
auto-installed by uv.

```powershell
uv sync                          # creates .venv, installs pinned deps
Copy-Item .env.example .env      # then fill in real API keys
uv run python -m pytest          # 60+ offline tests, no API calls
uv run python -m scripts.download_datasets --dataset all   # populates Dataset/ (once)
```

Datasets are fetched from HuggingFace **once** and committed to
`Dataset/<name>/{train,test}.jsonl` — experiment runs never hit HuggingFace, so
a clone of this repo (e.g. on the TAMU cluster) works offline and sees
byte-identical data. Re-run `download_datasets.py` and commit the diff only if
a dataset needs refreshing.

On Linux (TAMU cluster) the commands are identical, except `cp .env.example .env`.

> Note: all Python execution uses the `python -m` module form, e.g.
> `uv run python -m scripts.run_experiment`, run from the repo root.

## Configuration

**Model roles** live in `.env` — three roles, each with `MODEL` / `BASE_URL` /
`API_KEY`:

| Role | What it does | Local default |
|---|---|---|
| `SOLVER_*` | The model being prompted (under test) | gpt-4o-mini |
| `JUDGE_*` | Verdict critique + section attribution | gpt-4o |
| `OPTIMIZER_*` | Rewrites the implicated section | gpt-4o |

Any OpenAI-compatible endpoint works (OpenAI API, vLLM, Ollama, TGI, Together,
DeepSeek API). **Experiment parameters** (dataset, sample sizes, ρ, rounds,
budget caps, seed) are argparse flags — see `--help`.

## Running experiments

```powershell
# one run: method x dataset x seed
uv run python -m scripts.run_experiment --method fdpo --dataset gsm8k --seed 0

# cheap live sanity check first (~$1)
uv run python -m scripts.run_experiment --method fdpo --dataset gsm8k `
    --n-train 10 --n-test 10 --max-rounds 2 --budget-usd 1

# full pipeline check without any API calls or cost
uv run python -m scripts.run_experiment --method fdpo --dataset arc --dry-run

# Phase-0 smoke matrix: {gsm8k, arc} x {zeroshot_cot, fewshot_cot, monolithic, fdpo}
uv run python -m scripts.run_smoke --budget-usd 25

# roll all runs into results/summary.json
uv run python -m scripts.build_results_summary
```

Methods: `zeroshot_cot` (B1), `fewshot_cot` (B2), `monolithic` (whole-prompt
rewrite, = ablation A1), `fdpo`.

Datasets: `gsm8k` (EM), `arc` (ARC-Challenge, accuracy), `mmlu` (6 subjects,
accuracy), `legalbench_hearsay` (accuracy + macro-F1) — read from the committed
`Dataset/` folder (see Setup above).

Every API call is metered against a **hard budget cap** (`--budget-usd`); on
breach the run saves all partial results and exits cleanly with
`status="budget_aborted"`.

## Results layout

```
results/<phase>/<run_id>/
  config.json     # full resolved config (reproducibility; no secrets)
  metrics.json    # accuracy/EM/F1 + FDPO metrics (regression rate,
                  # section-attribution accuracy, time-to-stabilization,
                  # cost per accuracy point) + token/cost totals per role
  registry.json   # full per-section version history incl. rejected candidates
  train_log.csv   # per-example verdicts + section attribution per round
  rounds_log.csv  # per-rewrite gate outcomes (acc_old/acc_new/broke/recovered)
  eval_log.csv    # per-example test results (seed + final prompt)
  ledger.csv      # every API call: role, model, tokens, $ (compare vs dashboard)
results/summary.json   # roll-up across all runs
```

Committed to git: `metrics.json`, `config.json`, `registry.json`, CSV logs,
`summary.json`. Gitignored: raw call dumps and `events.jsonl`.

## TAMU cluster handoff (open models)

The recommended path is **vLLM** — zero code changes:

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct --port 8000
```

`.env` on the cluster:

```
SOLVER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy
# judge/optimizer can stay on an API, or point at a second vLLM server
```

Then run the exact same commands as above. Open-model runs cost $0 — pass
`--budget-usd 0` to disable the guard, and use the same `--seed` values so
subsamples match the local runs exactly.

If in-process transformers loading is required instead of a server, implement
`src/fdpo/clients/hf_client.py` — the stub's docstring describes exactly what
to fill in (~40 lines + torch/transformers deps).

## Repository map

```
Dataset/<name>/{train,test}.jsonl  # committed data (see scripts/download_datasets.py)
src/fdpo/
  config.py            # ExperimentConfig + argparse + .env role resolution
  clients/             # ModelClient ABC, OpenAI-compat, mock (tests/dry-run), HF stub
  data/
    hf_fetch.py         # HuggingFace fetch logic (download_datasets.py only)
    loaders.py          # reads committed Dataset/ files, seeded subsampling
    extraction.py       # answer extraction
  core/
    prompt.py          # 5-section and monolithic schemas, rendering
    registry.py        # section versions / archive / best-snapshot / stagnation
    judge.py           # attribution JSON parsing with retry + fallback
    optimizer.py       # section rewrite call
    gate.py            # correct-pool + old-vs-new regression comparison
    loop.py            # the offline batch optimization loop
  baselines/cot.py     # zero-shot / few-shot CoT builders
  eval/                # shared evaluator + standard & novel metrics
  prompts/             # seed prompts, judge & optimizer templates
  utils/               # budget guard/ledger, io, logging
scripts/               # download_datasets, run_experiment, run_smoke, build_results_summary
tests/                 # offline suite (mock client, zero API calls)
```
