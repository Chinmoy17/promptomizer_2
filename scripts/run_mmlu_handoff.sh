#!/usr/bin/env bash
# MMLU 6-subject simple_fdpo sweep for the open-model (TAMUK) handoff.
#
# Model roles come from .env (NOT this script). Set them there:
#   SOLVER_MODEL    = the ~7B model under test         (e.g. Qwen2.5-7B-Instruct)
#   OPTIMIZER_MODEL = the STRONGEST model you can serve (32B-72B ideal; the
#                     gpt-4.1 analog. A same-7B optimizer works but gains are
#                     muted, and a *too-strong* optimizer can overfit.)
# See README "Open-model handoff" and Docs/running_on_local_gpu.md.
#
# Regression-safe settings for an UNSUPERVISED run (see the project analysis):
#   --accept-margin 0.0    ship a rewrite only if it beats/ties baseline on
#                          validation, else revert to the seed -> worst case
#                          per subject is its own baseline (never a silent loss).
#   --simple-val-frac 0.5  bigger (25/25), less-noisy validation for the gate.
#   --solver-temperature 0 deterministic on open weights -> trustworthy gate.
#   --simple-max-rounds 2  rounds 1-2 are usually best; smaller overfit surface.
#   neutral seed prompt    honest delta; the optimizer discovers reasoning, and
#                          its system prompt already knows the solver has NO
#                          hidden scratchpad (must write VISIBLE steps) and when
#                          to reason (math/econ) vs answer directly (recall).
#
# Usage:
#   bash scripts/run_mmlu_handoff.sh
#   SEEDS="0 1 2" MAXWORKERS=32 bash scripts/run_mmlu_handoff.sh
set -u

SEEDS="${SEEDS:-0 1 2}"
ROUNDS="${ROUNDS:-2}"
VALFRAC="${VALFRAC:-0.5}"
ACCEPTMARGIN="${ACCEPTMARGIN:-0.0}"
SKIPABOVE="${SKIPABOVE:-0.90}"
NTRAIN="${NTRAIN:-50}"
NTEST="${NTEST:-66}"
TAU="${TAU:-3}"
MAXWORKERS="${MAXWORKERS:-16}"

SUBJECTS="college_mathematics philosophy econometrics high_school_biology professional_law computer_security"

ok=0
fail=0
failed=""
for subj in $SUBJECTS; do
  for seed in $SEEDS; do
    echo "=== ${subj} seed=${seed} rounds=${ROUNDS} margin=${ACCEPTMARGIN} ==="
    uv run python -m scripts.run_experiment --method simple_fdpo --dataset mmlu \
      --prompt-file prompts/mmlu_oneliner.md --subjects "$subj" \
      --n-train "$NTRAIN" --n-test "$NTEST" \
      --simple-max-rounds "$ROUNDS" --simple-val-frac "$VALFRAC" \
      --accept-margin "$ACCEPTMARGIN" --skip-above-acc "$SKIPABOVE" --tau "$TAU" \
      --seed "$seed" --split-mode balanced --solver-temperature 0.0 \
      --budget-usd 0 --max-workers "$MAXWORKERS" --phase "mmlu_open_${subj}"
    rc=$?
    if [ "$rc" -eq 0 ]; then
      ok=$((ok + 1))
    else
      fail=$((fail + 1))
      failed="${failed} ${subj}/s${seed}(rc=${rc})"
      echo "WARN: ${subj} seed ${seed} failed (exit ${rc}); continuing" >&2
    fi
  done
done

echo "=== sweep complete: ${ok} ok / ${fail} failed ==="
if [ -n "$failed" ]; then echo "failed runs:${failed}"; fi
uv run python -m scripts.build_results_summary
