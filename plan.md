# FDPO Pilot — Implementation & Experiment Plan (Offline Batch Mode)

> Living document. Status: Phase 0 (smoke test) scaffold under construction.
> Algorithm details: see [Docs/fdpo_experiment_plan.md](Docs/fdpo_experiment_plan.md) and [Docs/proposal.md](Docs/proposal.md).

## Context

FDPO (Feedback-Driven Modular Prompt Optimization) treats a prompt as K=5 semantic
sections, uses an LLM judge to attribute each failure to a responsible section,
rewrites only the implicated section, and protects every update with a per-section
regression gate + rollback.

The full experimental program is too expensive to run on one machine, so work is
split across two sites:

| Site | Runs | Models |
|---|---|---|
| Local (Windows, OpenAI API) | $25 Phase-0 smoke test | gpt-4o-mini (solver), gpt-4o (judge + optimizer) |
| Texas A&M (Prof. Tarek Mahmud's group, GPU cluster) | Open-model sweeps | Llama-3-8B, Qwen3-8B, DeepSeek |

The same code runs at both sites: every model sits behind one OpenAI-compatible
client, and only `.env` values change between machines (vLLM/Ollama/TGI/Together/
DeepSeek API all speak the OpenAI protocol). An HF-transformers client stub is
provided in case TAMU prefers direct GPU loading.

## Scope decisions (current)

- **Offline batch optimization only.** No τ threshold / online streaming trigger yet
  (deferred; the trigger policy is kept swappable so the online mode can be added
  later as ablation A10).
- **Datasets**: GSM8K, ARC-Challenge (smoke matrix); MMLU (6 subjects) and
  LegalBench *hearsay* loaders included, ready for the next phase.
- **Datasets are committed to the repo**, not fetched at run time. `scripts/
  download_datasets.py` pulls from HuggingFace once and writes
  `Dataset/<name>/{train,test}.jsonl`; experiment runs read only from that
  folder. This mirrors the FL-for-Aircraft repo's `Dataset/CMAPSS_NASA/`
  convention, keeps runs offline-capable, and guarantees TAMU sees byte-identical
  data via `git clone` instead of a second independent HF download.
- **Solvers**: gpt-4o-mini + gpt-4o locally; Llama-3-8B / Qwen3-8B / DeepSeek at TAMU.
  No legacy GPT-4 (12–24× the cost of gpt-4o).
- **Baselines**: zero-shot CoT, few-shot CoT, monolithic-FDPO (whole-prompt rewrite,
  same loop/gate — doubles as ablation A1), FDPO. External APO reimplementations
  (ProTeGi/MPO/aPSF) deferred.
- **Metrics**: EM (GSM8K), Accuracy (ARC/MMLU/LegalBench), macro-F1 (LegalBench),
  plus the novel FDPO metrics: regression rate, section-attribution accuracy,
  time-to-stabilization, cost per accuracy point. No BLEU/ROUGE (all tasks are
  EM/accuracy-style).
- **Verdicts are programmatic** (extracted answer vs gold label); the judge LLM is
  called only on incorrect examples for critique + section attribution
  (`--verdict-mode llm` preserves the pure LLM-judge path for ablation A11).
- **Results are JSON-first** in `results/<NN_phase>/<run_id>/` (metrics.json,
  config.json, registry.json, per-round CSVs), rolled up by
  `scripts/build_results_summary.py` into `results/summary.json`.

## The offline batch loop

Per optimization round `r = 1..max_rounds` (default 5):

1. Run the solver with the active sectioned prompt on the train subsample.
2. Verdict per example (programmatic): correct → added to the regression gate's
   rolling correct-pool; incorrect → judge returns
   `{critique, section (1–5|multiple|none), error_type (MISSING|WRONG|CONFLICT)}`
   → failures grouped per section.
3. For each section with attributed failures (descending failure count): the
   optimizer LLM rewrites that section from ≤5 sampled failures + 3 gold exemplars
   → **regression gate**: evaluate old vs new prompt on min(20, |pool|)
   previously-correct examples (+ the triggering failures, for recovery
   measurement); commit iff `acc_new ≥ acc_old − ρ` (default ρ = 0.02), else reject.
4. Best-snapshot restore after 3 stagnant rounds per section; early stop when
   |Δ pool-accuracy| < ε for 3 consecutive rounds (records time-to-stabilization).
5. `section = "multiple"` → feedback replicated to all named sections;
   `"none"` → logged only.

Monolithic-FDPO is the identical loop with a 1-section schema.

A **budget guard** checks cumulative API spend (from a per-model price table) after
every call; on breach the run persists all state and writes `metrics.json` with
`status="budget_aborted"`. Per-run default $4; the smoke orchestrator enforces the
cumulative $25.

## Repository layout

```
plan.md                       # this file
pyproject.toml / uv.lock      # uv-managed, Python 3.12.10
.env.example                  # per-role model/endpoint/key placeholders (copy to .env)
Dataset/<name>/{train,test}.jsonl  # committed data, fetched via scripts/download_datasets.py
src/fdpo/
  config.py                   # ExperimentConfig + argparse + .env role resolution
  clients/                    # ModelClient ABC, OpenAI-compatible impl, mock, HF stub (TAMU)
  data/                       # HF dataset loaders + per-dataset answer extraction
  core/                       # prompt schema, registry, judge, optimizer, gate, loop
  baselines/                  # zero-shot / few-shot CoT builders
  eval/                       # evaluator + metrics
  prompts/                    # seed section prompts, judge/optimizer templates
  utils/                      # budget guard, io, logging
scripts/
  download_datasets.py        # one-time HF fetch -> Dataset/<name>/{train,test}.jsonl (commit the result)
  run_experiment.py           # entry point: --method {zeroshot_cot,fewshot_cot,monolithic,fdpo}
  run_smoke.py                # Phase-0: {GSM8K, ARC} x 4 methods under a shared $25 cap
  build_results_summary.py    # results/**/metrics.json -> results/summary.json
tests/                        # pytest, all offline via mock client
results/                      # per-run outputs (metrics/config/registry committed; raw logs gitignored)
```

## Running (Windows PowerShell; Linux identical minus Copy-Item)

```powershell
uv sync
Copy-Item .env.example .env       # fill in real keys
uv run python -m pytest
uv run python -m scripts.download_datasets --dataset all   # once; commit Dataset/
uv run python -m scripts.run_experiment --help
uv run python -m scripts.run_experiment --method fdpo --dataset gsm8k --n-train 10 --n-test 10 --max-rounds 2 --budget-usd 1
uv run python -m scripts.run_smoke --budget-usd 25
uv run python -m scripts.build_results_summary
```

## Milestones

| # | Milestone | Verify by |
|---|---|---|
| M1 | Scaffold (pyproject, .env.example, config, utils) | `uv run python -m pytest` passes; `--help` prints flags |
| M2 | Clients + budget guard | budget tests green; HF stub raises instructive NotImplementedError |
| M3 | Loaders + extraction | extraction tests green; deterministic subsampling; `Dataset/` populated and committed |
| M4 | Prompt schema + registry | registry state-machine tests green |
| M5 | Judge / optimizer / gate | parsing + gate tests green (mock) |
| M6 | Loop + baselines + entry point | mock end-to-end writes full results tree |
| M7 | Live micro-run (n=10, ≤$1) | ledger ≈ OpenAI dashboard; ≥1 optimization round |
| M8 | Smoke orchestrator + summary | budget-abort exits cleanly with partial results |
| M9 | README (local + TAMU handoff) | fresh-clone walkthrough works |
| M10 | **$25 smoke run** | 8 metrics.json + summary.json; ≥1 committed rewrite per dataset |
