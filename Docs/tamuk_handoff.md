# TAMUK Handoff: Running Reflective FDPO's 5 Benchmarks on Qwen

Quick-start for reproducing this project's 5-benchmark protocol
(LegalBench-Hearsay, MMLU, IFBench, AIME, PUPA) on Qwen, on a Linux GPU
cluster. This distills the full background doc
(`Docs/running_reflect_fdpo_local.md`) into copy-paste commands — read that
file for the "why" behind any knob below.

---

## 0. Two ways to run this: bare `uv`, or Docker

Every command in this doc is written as `python -m scripts.run_experiment
...`. You have two equally valid ways to actually execute that:

**Bare `uv`** (§1 below): `uv sync` once, then run commands directly with
`uv run` in front, e.g. `uv run python -m scripts.run_experiment ...`.

**Docker** (no local Python/`uv` setup needed at all):
```bash
docker compose build          # once, or whenever src/scripts/Dataset/prompts change
docker compose run --rm fdpo python -m pytest -q   # sanity check, expect 95 passed
```
Then prefix every `python -m scripts.run_experiment ...` command below with
`docker compose run --rm fdpo`, e.g.:
```bash
docker compose run --rm fdpo python -m scripts.run_experiment \
  --method reflect_fdpo --dataset legalbench_hearsay --n-train 50 --n-test 49 ...
```
**Important**: `.env` is read at container *run* time (via `env_file:` in
`docker-compose.yml`), never baked into the image. You do not need `.env` to
exist to `docker compose build`, only to `docker compose run`. Changing a
model/URL in `.env` never requires a rebuild, only a fresh `run`.
The `fdpo` container talks to your vLLM/Ollama server(s) over
`network_mode: host` (Linux only), so `SOLVER_BASE_URL=http://localhost:8000/v1`
in `.env` means exactly what it means in the bare-`uv` case below — no URL
rewriting needed. `results/` is bind-mounted, so output lands on your host
disk exactly like a bare-`uv` run, and survives `--rm`.

---

## 1. Environment setup (`uv`, Linux)

Skip this section entirely if you're using Docker (see §0) -- `docker compose
build` already does the equivalent of `uv sync`, offline and pinned to the
same `uv.lock`.

```bash
# Requires uv (https://docs.astral.sh/uv/). Python 3.12 is pinned and
# auto-installed by uv -- no manual venv/python-version management needed.
uv sync                                   # creates .venv, installs pinned deps
cp .env.example .env                      # then fill in real values, see §2
uv run python -m pytest -q                # expect 95 passed, fully offline
```

`Dataset/<name>/{train,test}.jsonl` is already committed to this repo, so a
clone works fully offline — you do **not** need to run
`scripts/download_datasets.py` unless a `Dataset/` folder is unexpectedly
missing or you want to refresh a dataset.

All commands below use `python -m <module>` form, run from the repo root.

---

## 2. `.env` setup for Qwen

Serve Qwen via vLLM or Ollama first (not covered here — see
`Docs/running_on_local_gpu.md` for server standup). Once a server is
running, pick one tier based on available GPUs:

**Single-GPU tier** (same model for every role — simplest, but a weaker
optimizer than tier 2):
```env
SOLVER_MODEL=Qwen/Qwen2.5-7B-Instruct
SOLVER_BASE_URL=http://localhost:8000/v1
SOLVER_API_KEY=dummy

JUDGE_MODEL=Qwen/Qwen2.5-7B-Instruct
JUDGE_BASE_URL=http://localhost:8000/v1
JUDGE_API_KEY=dummy

OPTIMIZER_MODEL=Qwen/Qwen2.5-7B-Instruct
OPTIMIZER_BASE_URL=http://localhost:8000/v1
OPTIMIZER_API_KEY=dummy

# PUPA only -- must be a genuinely different model from solver/optimizer.
EXTERNAL_MODEL=meta-llama/Meta-Llama-3-8B-Instruct
EXTERNAL_BASE_URL=http://localhost:8001/v1
EXTERNAL_API_KEY=dummy
```

**Multi-GPU / asymmetric tier** (recommended — closer to this project's own
setup of a small solver + a much stronger optimizer/judge):
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

**Important**: do not set any `AZURE_OPENAI_*` variable in `.env` — its mere
presence forces the Azure client code path regardless of the `SOLVER_*` /
`JUDGE_*` / `OPTIMIZER_*` values above.

Sanity check before any real run:
```bash
python -m scripts.run_experiment --dry-run --method reflect_fdpo \
  --dataset legalbench_hearsay --n-train 10 --n-test 6

python -m scripts.run_experiment --method reflect_fdpo \
  --dataset legalbench_hearsay --n-train 10 --n-test 6 --tau 1 \
  --simple-max-rounds 2 --budget-usd 0 --phase test_scratch
```
`--budget-usd 0` disables the cost guard (no price-table entry for local
models). If the second command completes without an HTTP error, proceed.

---

## 3. The 5 benchmark commands

Run each once per model configuration (`.env` swap only — commands don't
change). `--budget-usd 0` throughout for the same reason as above. If using
Docker, prefix every command below with `docker compose run --rm fdpo`
(see §0).

**1. LegalBench-Hearsay** (legal classification, 50 train / 49 test, stratified):
```bash
python -m scripts.run_experiment \
  --method reflect_fdpo --dataset legalbench_hearsay \
  --n-train 50 --n-test 49 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 \
  --phase tamuk_reflect_hearsay_qwen
```

**2. MMLU** (6-subject sweep, 50 train / 66 test per subject, balanced):
```bash
for subject in college_mathematics computer_security econometrics \
               high_school_biology philosophy professional_law; do
  python -m scripts.run_experiment \
    --method reflect_fdpo --dataset mmlu \
    --prompt-file prompts/mmlu_oneliner.md \
    --n-train 50 --n-test 66 --tau 1 --simple-max-rounds 3 \
    --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
    --split-mode balanced --subjects "$subject" --seed 0 --budget-usd 0 \
    --phase "tamuk_reflect_mmlu_qwen_${subject}"
done
```

**3. IFBench** (verifiable instruction-following, 40 train / 42 test, stratified):
```bash
python -m scripts.run_experiment \
  --method reflect_fdpo --dataset ifbench \
  --n-train 40 --n-test 42 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 \
  --phase tamuk_reflect_ifbench_qwen
```

**4. AIME** (competition mathematics, 90 train / 30 test, seeded split):
```bash
python -m scripts.run_experiment \
  --method reflect_fdpo --dataset aime \
  --n-train 90 --n-test 30 --tau 1 --simple-max-rounds 3 \
  --accept-margin 0.0 --skip-above-acc 0.95 --simple-val-frac 0.35 \
  --split-mode seeded --seed 0 --budget-usd 0 \
  --solver-max-tokens 16000 \
  --phase tamuk_reflect_aime_qwen
```
**Important lesson from this project's own debugging**: AIME needs a much
higher token cap than you'd expect. Even GPT-4.1 Mini (a frontier commercial
model) needed `--solver-max-tokens` raised from 8096 to 16000 before
truncation-driven wrong answers stopped confounding the results — and open
7-8B models tend to "think out loud" even more verbosely. Start at 16000, not
lower. **After the run, check for remaining truncation**:
```bash
python -c "
import csv
rows = list(csv.DictReader(open('results/tamuk_reflect_aime_qwen/<run_dir>/ledger.csv')))
solver = [r for r in rows if r['role'] == 'solver']
capped = [r for r in solver if float(r['completion_tokens']) >= 15990]
print(f'{len(capped)}/{len(solver)} solver calls hit the token cap')
"
```
If a meaningful fraction hit the cap, raise `--solver-max-tokens` further and
rerun before trusting the accuracy number.

**5. PUPA** (privacy-conscious delegation, 60 train / 40 test, stratified —
needs the `EXTERNAL_*` role configured in `.env`, see §2):
```bash
python -m scripts.run_experiment \
  --method reflect_fdpo --dataset pupa \
  --n-train 60 --n-test 40 --tau 1 --simple-max-rounds 3 \
  --accept-margin 1.0 --simple-val-frac 0.5 \
  --split-mode stratified --seed 0 --budget-usd 0 --max-workers 4 \
  --phase tamuk_reflect_pupa_qwen
```

---

## 4. Reading the results

Each run writes to `results/<phase>/<dataset>_reflect_fdpo_<model>_s<seed>_<timestamp>/`:
- `metrics.json` — `seed_test.accuracy` (baseline) / `final_test.accuracy`
  (shipped), and `optimization.test_confusion.recoveries` /
  `.regressions` (which specific test items flipped, and in which direction).
- `ledger.csv` — per-call `completion_tokens`; check this for token-cap
  truncation as shown above, especially for AIME.
- `run.log` — per-round mining/validation accuracy and the final shipped-round
  decision.

For multi-seed robustness (recommended, since every existing result in this
project is single-seed), wrap any command in
`for seed in 0 1 2; do ... --seed $seed --phase tamuk_reflect_<name>_qwen_s$seed; done`.
