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

## Open-model handoff (vLLM or Ollama)

Moving to open models (e.g. the TAMUK lab) is a **`.env`-only change** — the
solver/optimizer/judge each point at any OpenAI-compatible server. The client
picks Azure vs. plain OpenAI purely from whether an `api_version` is set, so
there are **zero code changes**.

> **Critical for every open-model setup:** remove/comment **all**
> `AZURE_OPENAI_*` vars **and** any `*_API_VERSION` var in `.env`. A non-empty
> `api_version` forces the `AzureOpenAI` client path, which vLLM/Ollama reject —
> the symptom is *every completion comes back empty*. Also: `*_API_KEY` must be
> non-empty (`dummy` is fine), and `SOLVER_MODEL` must match the server's model
> id exactly (case-sensitive) or you get a 404.

### Path A — vLLM (fastest; batches requests)

```bash
pip install vllm
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct --port 8000 --max-num-seqs 32
```

```env
SOLVER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy
# judge/optimizer can stay on an API, or point at a second vLLM server
```

Set `--max-workers` to vLLM's `--max-num-seqs` for a large throughput win.

### Path B — Ollama (what the TAMUK lab uses)

```bash
# 1. Install (Linux; already a daemon on most setups)
curl -fsSL https://ollama.com/install.sh | sh

# 2. Pull the model. Use the SAME model id for solver + optimizer so Ollama
#    never has to swap weights mid-run (see concurrency note below).
ollama pull llama3:8b-instruct

# 3. Enable parallel requests BEFORE starting the server, so --max-workers
#    actually buys concurrency (Ollama otherwise serialises to 1 slot).
export OLLAMA_NUM_PARALLEL=4        # concurrent requests per model
export OLLAMA_MAX_LOADED_MODELS=1   # keep one model resident (no eviction)
ollama serve                        # listens on http://localhost:11434
```

`.env` (all three roles on the one Ollama server):

```env
SOLVER_MODEL=llama3:8b-instruct
SOLVER_BASE_URL=http://localhost:11434/v1
SOLVER_API_KEY=dummy

OPTIMIZER_MODEL=llama3:8b-instruct
OPTIMIZER_BASE_URL=http://localhost:11434/v1
OPTIMIZER_API_KEY=dummy

JUDGE_MODEL=llama3:8b-instruct       # unused by simple_fdpo; leave as-is
JUDGE_BASE_URL=http://localhost:11434/v1
JUDGE_API_KEY=dummy
```

Sanity-check the server, then run the exact same commands as above with
`--budget-usd 0` (no price table for local models) and `--max-workers` matched
to `OLLAMA_NUM_PARALLEL`:

```bash
curl http://localhost:11434/v1/models
uv run python -m scripts.run_experiment --method simple_fdpo \
    --dataset legalbench_hearsay --n-train 10 --n-test 6 \
    --tau 3 --seed 0 --budget-usd 0 --max-workers 4 --phase test_scratch
```

> If FDPO runs on a Windows laptop but Ollama is on a Linux node, tunnel the
> port: `ssh -L 11434:localhost:11434 you@node`, then use `localhost:11434`.

### Recommended handoff run (MMLU-6, regression-safe)

For the final open-model handoff, run the six MMLU subjects with the
**regression-safe** settings below — the worst any subject can do is match its
own baseline, so the sweep is safe to run unsupervised:

```bash
bash scripts/run_mmlu_handoff.sh
# override defaults if needed:
SEEDS="0 1 2" MAXWORKERS=32 bash scripts/run_mmlu_handoff.sh
```

**Model roles (`.env`) — the one decision that matters:**

| Role | Use | Why |
|---|---|---|
| `SOLVER_MODEL` | the ~7B under test (e.g. `Qwen2.5-7B-Instruct`, `Llama-3.1-8B-Instruct`) | weak solver = more headroom = larger, cleaner deltas |
| `OPTIMIZER_MODEL` | the **strongest** model you can serve (32B–72B ideal) | a stronger optimizer writes better prompts; a same-7B optimizer works but gains are muted. A *too-strong* optimizer (e.g. gpt-5) overfits — mid-strong is the sweet spot. |

**Why these flags (baked into the script):**

- `--accept-margin 0.0` — **regression-safe gate**: ships a rewrite only if it
  beats/ties the seed on held-out validation, else reverts to the seed. Worst
  case per subject = its baseline. This is the key safety property when no one
  is watching the run.
- `--simple-val-frac 0.5` — a 25/25 mining/validation split so the gate's
  decision is reliable (a tiny validation slice is what shipped regressors on
  Azure).
- `--solver-temperature 0.0` — open weights are deterministic, which removes the
  ~5 pp non-determinism and makes both the gate and the deltas trustworthy.
- **neutral seed** (`prompts/mmlu_oneliner.md`) — honest baseline; the optimizer
  discovers reasoning itself. Its system prompt already knows the solver has
  **no hidden scratchpad** (so it must write *visible* step-by-step working) and
  **when to reason vs answer directly** (reasoning for math/econ, direct for
  recall subjects like law/security).

Expect **larger, cleaner per-subject deltas than the gpt-4o-mini runs** (more
headroom + determinism): the compute/reasoning subjects gaining, the
near-ceiling recall subjects flat, and — with the regression-safe gate — no
subject dropping below its baseline.

### Performance & concurrency on Ollama

`evaluate()` fans solver calls across a `ThreadPoolExecutor` of size
`--max-workers`; the token ledger is lock-guarded and the `openai` client
retries with backoff, so parallel evaluation is safe. The caveats are all on
the **server** side:

- **`--max-workers` must match `OLLAMA_NUM_PARALLEL`.** Requests beyond the
  server's parallel slots just **queue** (no error, no speedup). Ollama does not
  batch like vLLM, so expect it to be **5–10× slower** on these sweeps.
- **One experiment process at a time.** Running several `run_experiment`
  invocations at once against the same Ollama server is the main footgun —
  they contend for the same slots, and if their model ids differ Ollama
  **thrashes** loading/unloading weights. The loops in the run guide are
  sequential by design; keep them that way (or raise `OLLAMA_NUM_PARALLEL`).
- **Keep solver == optimizer model** (or set `OLLAMA_MAX_LOADED_MODELS ≥ 2`
  with enough VRAM) so the per-round optimizer call doesn't evict the solver.
- **Single-GPU VRAM ceiling.** With `OLLAMA_NUM_PARALLEL=4` the KV cache is
  split across slots; on <24 GB VRAM drop to 2 to avoid OOM / reloads.

Rough wall-clock, single modern GPU, Llama-3-8B (Q4), `--max-workers 4`:

| Sweep | Solver calls (≈) | Ollama estimate |
|---|---:|---|
| Tiny sanity (`--n-train 10 --n-test 6`) | ~30 | 1–3 min (+ first cold load) |
| Hearsay, 3 seeds | ~850 | 15–45 min |
| MMLU **one** subject, 3 seeds | ~1,000 | 30–75 min (math is slowest — long CoT) |
| MMLU **all 6** subjects, 3 seeds | ~6,000 | ~3–8 h (run overnight) |
| Baseline ablation (3 methods × 3 seeds) | ~800 | 30–60 min |

These scale with output length (recall tasks emit ~10 tokens → ~1 s each; math
emits ~400 tokens → ~6–12 s each), model size (a 70B is far slower on one GPU),
and GPU throughput. vLLM cuts all of these several-fold.

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
