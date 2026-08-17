# Running FDPO on your own GPU / server

**Audience**: Prof. Tarek Mahmud's group at Texas A&M, or anyone running
this codebase on their own hardware with Llama, Mistral, or another
open-weight model.

**What you get**: identical experimental protocol to what we ran on Azure
OpenAI, but with:
- Full determinism at temperature 0 (open models are bit-deterministic;
  Azure is not — we measure ~5 pp same-prompt variance).
- Zero API cost per run (only your GPU time).
- Access to token log-probabilities if you want to replicate
  "Knowing How to Edit" -style methods (not covered here).

**Time to a first real run**: about 90 minutes end to end for a first-time
setup, then ~15 minutes per experiment.

---

## 1. What you are pointing at

The codebase does NOT have Llama or Mistral weights inside it. It expects
you to run **an inference server on your GPU that speaks the OpenAI
protocol**, and it talks to that server via HTTP. That is the entire
integration point — the `openai` Python package handles the rest.

Three concrete choices, in decreasing order of throughput:

| Server | Best for | Setup difficulty |
|---|---|---|
| **vLLM** | Serious throughput, batched inference, largest model sizes | Medium (Linux + CUDA + Python) |
| **Ollama** | Fastest to get running on a laptop or single GPU | Trivial (one-line install) |
| **Text Generation Inference (TGI)** | If you already use HuggingFace's stack | Medium |

Pick one. This document walks through **vLLM** as the primary path
(recommended for TAMU) and **Ollama** as a fallback for quick experimentation.

---

## 2. Path A — vLLM (recommended for TAMU)

### 2.1 Prerequisites on your GPU node

- Linux with NVIDIA driver + CUDA 12.1 or later.
- Python 3.10 or later (Python 3.12 recommended, matches our development
  environment).
- At least 20 GB of free VRAM for Llama-3-8B-Instruct at fp16; 40 GB for
  Llama-3-70B-Instruct with quantization.
- Network access from the machine running FDPO to the machine running
  vLLM. If they are the same machine, that's `localhost`.

### 2.2 Install vLLM

```bash
pip install vllm
```

or in a fresh conda env:

```bash
conda create -n vllm python=3.12 -y
conda activate vllm
pip install vllm
```

### 2.3 Start the server

For Llama-3-8B-Instruct:

```bash
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct \
    --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 32
```

For Mistral-7B-Instruct:

```bash
python -m vllm.entrypoints.openai.api_server \
    --model mistralai/Mistral-7B-Instruct-v0.3 \
    --port 8000 \
    --max-model-len 8192 \
    --gpu-memory-utilization 0.90 \
    --max-num-seqs 32
```

For a bigger solver plus a bigger optimizer, run **two servers on two
different ports** (each pinned to a different GPU with
`CUDA_VISIBLE_DEVICES=0` and `CUDA_VISIBLE_DEVICES=1`):

```bash
# Terminal 1 (or systemd unit / tmux pane):
CUDA_VISIBLE_DEVICES=0 python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-8B-Instruct --port 8000 --max-num-seqs 32

# Terminal 2:
CUDA_VISIBLE_DEVICES=1 python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3-70B-Instruct --port 8001 --max-num-seqs 8
```

You will see log lines ending in `Uvicorn running on http://0.0.0.0:8000`.
That means the server is up.

### 2.4 Sanity check the server

Before touching FDPO code, verify the server responds:

```bash
curl http://localhost:8000/v1/models
```

You should get a JSON response listing the model. Then:

```bash
curl http://localhost:8000/v1/chat/completions \
    -H "Content-Type: application/json" \
    -d '{
        "model": "meta-llama/Meta-Llama-3-8B-Instruct",
        "messages": [{"role": "user", "content": "Say hi."}],
        "temperature": 0
    }'
```

You should get a JSON completion. If this works, FDPO will work.

### 2.5 Configure FDPO to point at your vLLM server

On the machine that will run FDPO (can be the same node as vLLM, or a
different machine on the same network), clone the repo and set up:

```bash
git clone <this repo> PromtoMizer
cd PromtoMizer
uv sync                            # installs Python 3.12 + dependencies
cp .env.example .env
```

Now edit `.env`. The **only** lines you need to change are the three
role slots:

```env
# Solver: the model being prompted (single-model regime, same model for all roles)
SOLVER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy

# Optimizer: rewrites the prompt. If you have a second, larger server on
# port 8001, point this at it. Otherwise use the same server as solver.
OPTIMIZER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
OPTIMIZER_BASE_URL=http://localhost:8000/v1
OPTIMIZER_API_KEY=dummy

# Judge: only used by --method fdpo (v2), NOT by --method simple_fdpo.
# You can leave this pointing at the same server; it will not be called.
JUDGE_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
JUDGE_BASE_URL=http://localhost:8000/v1
JUDGE_API_KEY=dummy
```

Notes on this file:

- `SOLVER_API_KEY=dummy` — vLLM does not verify the key by default. Any
  non-empty string works. The `openai` Python client refuses to
  instantiate with an empty key, which is why we pass "dummy".
- **Do NOT set `AZURE_OPENAI_*` variables.** If any of the
  `AZURE_OPENAI_*` variables are set, the client tries to construct an
  Azure client with the `api_version` parameter, which vLLM does not
  understand.
- If you eventually run a 70B optimizer on port 8001, only change
  `OPTIMIZER_MODEL` and `OPTIMIZER_BASE_URL`.

### 2.6 Verify FDPO can talk to your server

Run the offline test suite first (no API calls, uses a mock client):

```bash
uv run python -m pytest -q
```

Expect **95 passed**. If a test fails, something is wrong with your
Python environment; do not proceed until this is clean.

Then a mock-client dry run of a real experiment (no API calls, ~2 seconds):

```bash
uv run python -m scripts.run_experiment \
    --dry-run --method simple_fdpo \
    --dataset legalbench_hearsay --n-train 10 --n-test 6
```

Then a tiny real run against your vLLM server (~30 seconds on Llama-8B):

```bash
uv run python -m scripts.run_experiment \
    --method simple_fdpo --dataset legalbench_hearsay \
    --n-train 10 --n-test 6 --tau 3 --seed 0 \
    --budget-usd 0 --phase test_scratch
```

`--budget-usd 0` disables the cost guard, because the guard's price table
doesn't know about your local model. The run should complete without
API errors and write a metrics.json to
`results/test_scratch/legalbench_hearsay_simple_fdpo_.../metrics.json`.

If you see any HTTP error at this stage, the problem is between your FDPO
node and your vLLM server. Check that `curl http://<vllm_host>:8000/v1/models`
works from the FDPO node.

---

## 3. Path B — Ollama (fallback for quick experimentation)

For a laptop or a machine without CUDA-Python friction:

```bash
# One-line install for macOS / Linux:
curl -fsSL https://ollama.com/install.sh | sh

# In another terminal, pull a model:
ollama pull llama3:8b-instruct

# Start the server (usually already running as a daemon after install):
ollama serve
```

The server listens on `http://localhost:11434` by default. In your
`.env`:

```env
SOLVER_MODEL=llama3:8b-instruct
SOLVER_BASE_URL=http://localhost:11434/v1
SOLVER_API_KEY=dummy

OPTIMIZER_MODEL=llama3:8b-instruct
OPTIMIZER_BASE_URL=http://localhost:11434/v1
OPTIMIZER_API_KEY=dummy
```

Same sanity checks as vLLM.

Ollama's `/v1` OpenAI-compatible endpoint has been stable since late 2024.
It is much slower than vLLM (no batched inference) — expect 5-10× longer
runs. Only recommended for a first exploratory session.

---

## 4. The recommended first three experiments

Once you've verified a tiny run works, these are the three experiments to
run in order. Each is bounded to about 15 minutes of wall time on
Llama-3-8B via vLLM.

### 4.1 Replicate our LegalBench-hearsay result

```bash
for seed in 0 1 2; do
    uv run python -m scripts.run_experiment \
        --method simple_fdpo --dataset legalbench_hearsay \
        --n-train 40 --n-test 59 --tau 5 --simple-max-rounds 3 \
        --seed $seed --split-mode stratified \
        --budget-usd 0
done
```

Then aggregate:

```bash
uv run python -m scripts.build_results_summary
```

**Expected outcome**: gain of +5 to +15 pp mean on test across the three
seeds, likely larger than our +7.4 pp on gpt-4o-mini because Llama-3-8B's
baseline should be lower and there is more headroom.

**What to report back to us**: the three metrics.json files, plus the
final `prompt_current.md` from each run.

### 4.2 MMLU per subject

The MMLU dataset is already committed to the repo. This runs six
subjects mixed together (single prompt for all):

```bash
for seed in 0 1 2; do
    uv run python -m scripts.run_experiment \
        --method simple_fdpo --dataset mmlu \
        --n-train 120 --n-test 150 --tau 5 --simple-max-rounds 3 \
        --seed $seed --split-mode stratified \
        --budget-usd 0
done
```

**Expected outcome**: 1-3 pp mean overall gain, with a per-subject
breakdown (analyzed post-hoc via `_dl/mmlu_subject_breakdown.py`) that
should show larger gains on high-baseline subjects (biology, philosophy)
and near-zero on at-chance subjects (professional_law, college_math).
This confirms the "amplifier not injector" finding on open models.

### 4.3 A simple ablation to establish credibility

Run the baselines head-to-head on the same test items:

```bash
for method in zeroshot_cot fewshot_cot monolithic; do
    for seed in 0 1 2; do
        uv run python -m scripts.run_experiment \
            --method $method --dataset legalbench_hearsay \
            --n-train 40 --n-test 59 --seed $seed \
            --split-mode stratified --budget-usd 0
    done
done
```

**Expected outcome**: `simple_fdpo` should beat `zeroshot_cot` and
`fewshot_cot` by at least a few pp mean; `monolithic` (a prompt rewrite
with no failure evidence) should score close to `simple_fdpo` when
optimizer is strong or lower when it is weak.

---

## 5. Tuning knobs specifically for open models

Most defaults are fine, but a few knobs matter more on local models than
they did on Azure:

| Knob | Recommended for open models | Why |
|---|---|---|
| `--solver-temperature 0.0` | Keep at 0 | Open models ARE deterministic at 0 — one of the main reasons to move off Azure. |
| `--optimizer-temperature 0.3` | Keep at 0.3 | Same rationale as with closed models; low enough for structure, high enough for diversity. |
| `--max-workers 8` | Raise to match your vLLM `--max-num-seqs` | e.g. if vLLM was started with `--max-num-seqs 32`, set `--max-workers 32`. Big throughput win. |
| `--budget-usd 0` | Always | The price table has no entry for your local model; the guard would either be a no-op or block on missing pricing. |
| `--solver-max-tokens 1024` | Raise to 2048 for math/reasoning tasks | Open models sometimes need more thinking room than closed frontier models. |
| `--simple-max-rounds 3` | Keep at 3 | The multi-round mechanism with best-snapshot rescue is a strict improvement over single-pass on open models where you have deterministic inference. |

---

## 6. What NOT to worry about

- **Content filters.** Open models have no equivalent to Azure's
  content filter, so the "content_filter blocked ~2% of MMLU
  professional_law calls" issue we hit on Azure disappears. The
  BadRequestError handler in `openai_client.py` will simply never fire.
- **Rate limits.** vLLM has none. Ollama's rate is bounded only by GPU
  throughput. You can run experiments back-to-back.
- **API keys / cost tracking.** With `--budget-usd 0` the budget guard
  is disabled. The ledger will show $0 for every call, which is correct.
- **Log-probabilities.** vLLM exposes them if you pass `logprobs=True`,
  but our current mechanism does not use them. If you want to replicate
  "Knowing How to Edit" (which needs logprobs) that would be a separate
  extension.

---

## 7. Common failure modes and how to spot them

| Symptom | Likely cause | Fix |
|---|---|---|
| `openai.NotFoundError: 404 - model not found` | Your `SOLVER_MODEL` string does not match what vLLM reports at `/v1/models` | Match them exactly (case-sensitive) |
| `openai.APIConnectionError` | vLLM server is down or firewalled | Check `curl http://host:8000/v1/models` from the FDPO machine |
| All completions are empty strings | `AZURE_OPENAI_*` env vars are set and forcing the Azure client path | Unset them (`unset AZURE_OPENAI_ENDPOINT` etc.) |
| Every solver call fails to extract "Answer: X" | Open model isn't following the output format | The extractor is permissive but not infinitely so. Check `run.log` for a few solver outputs, and if the model is emitting "The answer is A" instead of "Answer: A" we may need to loosen the extractor in `src/fdpo/eval/extractor.py` |
| Extremely long wall times | `--max-workers` is too low, or vLLM's `--max-num-seqs` is too low | Raise both. On an 8B model with 40GB VRAM, `--max-num-seqs 64` is realistic |

If you hit an extraction issue that is not obviously the model's fault,
send us three example solver outputs from `run.log` and we will fix the
extractor in a single PR.

---

## 8. What to send back

For each experiment you run, the most useful artifacts to share are:

1. `results/<phase>/<run_id>/metrics.json` — the single source of truth.
2. `results/<phase>/<run_id>/prompt_current.md` — the actual rewritten
   prompt, so we can inspect what the optimizer chose to change.
3. `results/<phase>/<run_id>/run.log` — includes the per-round confusion
   matrices and any warnings.

A `zip -r results.zip results/main/` is enough. We can diff against our
own runs to spot any protocol drift.

---

## 9. If something is genuinely broken

Two channels:

1. Open a GitHub issue on this repo with the failing command line, the
   full stderr, and the `run.log` from the failed run.
2. For urgent blockers, ping [contact info] with the same three items
   plus a one-line summary.

We will fix any real blocker within one working day. Please do not spend
time hacking around a bug in this codebase — flag it and we will patch
it, so that the numbers you eventually publish are on the same code
snapshot as ours.
