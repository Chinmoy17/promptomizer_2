# Running Reflective FDPO on Llama / Qwen (vLLM or Ollama)

**Relationship to `running_on_local_gpu.md`**: that document covers server setup
(vLLM/Ollama install, `.env` wiring, sanity checks) for the older `simple_fdpo`
mechanism. This document assumes that setup is done and adds what changed once
the project evolved into **Promptomizer**'s **Reflective FDPO** (`--method
reflect_fdpo`): different default knobs per dataset, a mandatory but unused
`judge` role, and PUPA's extra `external` role. If you have not stood up a
vLLM or Ollama server yet, do that first via `running_on_local_gpu.md` §§1-3,
then come back here.

---

## 1. Model pairing: which model plays which role

Every real run in this project used a **small, cheap solver** and a **much
stronger optimizer/judge** (e.g. GPT-4o-mini / Claude Haiku 4.5 as solver,
GPT-5 as optimizer+judge). Reflective FDPO's optimizer has to read a dense
per-round effect report and reason about cause → effect before rewriting a
five-section prompt — a 7-8B model can do this, but noticeably less reliably
than a frontier model. That asymmetry is itself part of what RQ5 in the paper
(generality across solver families) is asking, so don't expect open-model
numbers to look like the GPT-5-optimizer numbers already in the paper — this
is the first real data point toward answering that question, not a
replication of it.

Two tiers depending on your hardware:

| Tier | Solver | Optimizer + Judge | External (PUPA only) | VRAM |
|---|---|---|---|---|
| **Single-GPU / same model for all roles** | Llama-3-8B-Instruct or Qwen2.5-7B-Instruct | *same model* | Mistral-7B-Instruct-v0.3 (must differ from solver) | ~20-24 GB |
| **Multi-GPU / asymmetric (recommended, closer to the paper's setup)** | Llama-3-8B-Instruct or Qwen2.5-7B-Instruct | Llama-3-70B-Instruct or Qwen2.5-72B-Instruct | the *other* family's 7-8B model | 24 GB (solver) + 80-140 GB (optimizer, quantized or multi-GPU) |

If you only have one GPU, use the single-model row — Reflective FDPO still
runs and is still meaningful, just with a weaker optimizer than tier 2.

---

## 2. `.env` templates

**Llama, vLLM, asymmetric tier** (solver on port 8000, optimizer+judge on 8001):

```env
SOLVER_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy

# Judge is never called by reflect_fdpo, but load_role() still requires it to
# resolve -- point it at the same server/model as the optimizer so you don't
# need a 4th deployment.
JUDGE_MODEL=meta-llama/Meta-Llama-3-70B-Instruct
JUDGE_BASE_URL=http://localhost:8001/v1
JUDGE_API_KEY=dummy

OPTIMIZER_MODEL=meta-llama/Meta-Llama-3-70B-Instruct
OPTIMIZER_BASE_URL=http://localhost:8001/v1
OPTIMIZER_API_KEY=dummy

# PUPA only -- must be a genuinely different model from solver/optimizer.
EXTERNAL_MODEL=Qwen/Qwen2.5-7B-Instruct
EXTERNAL_BASE_URL=http://localhost:8002/v1
EXTERNAL_API_KEY=dummy
```

**Qwen, vLLM, asymmetric tier**:

```env
SOLVER_MODEL=Qwen/Qwen2.5-7B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy

JUDGE_MODEL=Qwen/Qwen2.5-72B-Instruct
JUDGE_BASE_URL=http://localhost:8001/v1
JUDGE_API_KEY=dummy

OPTIMIZER_MODEL=Qwen/Qwen2.5-72B-Instruct
OPTIMIZER_BASE_URL=http://localhost:8001/v1
OPTIMIZER_API_KEY=dummy

EXTERNAL_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
EXTERNAL_BASE_URL=http://localhost:8002/v1
EXTERNAL_API_KEY=dummy
```

Single-GPU tier: set every `*_BASE_URL` to the same `http://localhost:8000/v1`
(or `:11434/v1` for Ollama) and every `*_MODEL` to the same model string,
except `EXTERNAL_MODEL` for PUPA, which still needs its own port/model.
**Do not set any `AZURE_OPENAI_*` variable** — its presence forces the Azure
client path regardless of the other settings.

For Ollama, replace `http://localhost:8000/v1` with `http://localhost:11434/v1`
everywhere and use Ollama tags (`llama3:8b-instruct`, `llama3:70b-instruct`,
`qwen2.5:7b-instruct`, `qwen2.5:72b-instruct`) instead of HF repo ids. One
Ollama daemon can serve multiple models by name on the same port — you don't
strictly need separate ports — but if roles alternate rapidly it will reload
models in and out of VRAM, which is slow. Separate `ollama serve` processes on
different ports (`OLLAMA_HOST=127.0.0.1:11435 ollama serve`) avoid that if you
have the VRAM to keep more than one model resident.

---

## 3. Sanity check before spending real GPU time

```bash
uv run python -m pytest -q                       # expect 95 passed, offline

uv run python -m scripts.run_experiment \
    --dry-run --method reflect_fdpo \
    --dataset legalbench_hearsay --n-train 10 --n-test 6

uv run python -m scripts.run_experiment \
    --method reflect_fdpo --dataset legalbench_hearsay \
    --n-train 10 --n-test 6 --tau 1 --simple-max-rounds 2 \
    --budget-usd 0 --phase test_scratch
```

`--budget-usd 0` disables the cost guard (no price-table entry for local
models). If this last command completes without an HTTP error, move on.

---

## 4. The five benchmark commands

These reproduce the exact per-dataset knobs from this project's own
`reflect_fdpo` runs (pulled directly from each run's `config.json`), with
`--budget-usd 0` swapped in for local inference. Run each once per model
family — just swap which `.env` is active; the commands themselves don't change.

**LegalBench-Hearsay** (legal classification, 50 train / 49 test, stratified):
```bash
uv run python -m scripts.run_experiment \
  --method reflect_fdpo --dataset legalbench_hearsay \
  --n-train 50 --n-test 49 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 \
  --phase local_reflect_hearsay
```

**MMLU** (per-subject sweep, matching the paper's 6-subject protocol; 50/66
per subject, balanced):
```bash
for subject in college_mathematics computer_security econometrics \
               high_school_biology philosophy professional_law; do
  uv run python -m scripts.run_experiment \
    --method reflect_fdpo --dataset mmlu \
    --prompt-file prompts/mmlu_oneliner.md \
    --n-train 50 --n-test 66 --tau 1 --simple-max-rounds 3 \
    --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
    --split-mode balanced --subjects "$subject" --seed 0 --budget-usd 0 \
    --phase "local_reflect_mmlu_${subject}"
done
```

**IFBench** (verifiable instruction-following, 40 train / 42 test, stratified):
```bash
uv run python -m scripts.run_experiment \
  --method reflect_fdpo --dataset ifbench \
  --n-train 40 --n-test 42 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 \
  --phase local_reflect_ifbench
```

**AIME** (competition mathematics, 90 train / 30 test, seeded split):
```bash
uv run python -m scripts.run_experiment \
  --method reflect_fdpo --dataset aime \
  --n-train 90 --n-test 30 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.35 \
  --split-mode seeded --seed 0 --budget-usd 0 \
  --solver-max-tokens 4096 \
  --phase local_reflect_aime
```
Open models tend to "think out loud" more verbosely than GPT-4o-mini on AIME;
`--solver-max-tokens 4096` (vs. the 2048 used in the original run) guards
against truncating before the final answer line. If you see extraction
failures in `run.log`, raise it further.

**PUPA** (privacy-conscious delegation, 60 train / 40 test, stratified —
needs the `external` role configured, see §2):
```bash
uv run python -m scripts.run_experiment \
  --method reflect_fdpo --dataset pupa \
  --n-train 60 --n-test 40 --tau 1 --simple-max-rounds 3 \
  --accept-margin 1.0 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 --max-workers 4 \
  --phase local_reflect_pupa
```

Notes on the knob values above (they intentionally differ from
`running_on_local_gpu.md`'s older `simple_fdpo` defaults, e.g. `--tau 5`):
`--tau 1` means Reflective FDPO always attempts optimization rather than
skipping low-failure batches; `--accept-margin` is set but **ignored** by
`reflect_fdpo` (no revert-to-baseline gate — see `reflect_loop.py`'s module
docstring), except PUPA which was run with the field left at its default
(harmless either way); `--skip-above-acc 0.95` protects near-ceiling subjects
from being optimized at all, mirroring §5.4's diagnosis.

For multi-seed robustness, wrap any of the above in `for seed in 0 1 2; do
... --seed $seed --phase local_reflect_<name>_s$seed; done` — every run in
this project's own `results/` used seed 0 only for `reflect_fdpo`, so seeds
1-2 would be new evidence, not a replication of an existing number.

---

## 5. Reading the results

Each run writes to `results/<phase>/<dataset>_reflect_fdpo_<model>_s<seed>_<timestamp>/`:
- `metrics.json` — `optimization.baseline_val_acc` / `best_structured_val_acc`,
  `seed_test.accuracy` / `final_test.accuracy`, and `train_confusion` /
  `test_confusion` giving `R_t`/`G_t` directly (§3.4 of the paper).
- `registry.json` — every committed round's exact prompt text; use
  `scripts/show_rounds.py <run_dir>` to print the per-round trajectory, or
  `scripts/eval_round_on_test.py` to retroactively score a *different* round
  on the sealed test set (useful if you want to check whether the shipped
  round was actually the best one — see §5.2 of the paper for why that
  matters).
- `run.log` — per-round confusion matrices and any solver extraction warnings.
