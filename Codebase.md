# FDPO Codebase — How It Actually Works, Start to Finish

> Companion to [plan.md](plan.md) (design/scope) and [progress.md](progress.md)
> (build status). This file explains the *mechanics*: what prompt is used,
> what happens on every API call, where every byte of output lands on disk.
> Every code reference below is `path:line`, and every concrete example is
> pulled from a real completed run, not a hypothetical.

## 1. The one-paragraph version

FDPO treats a prompt as **5 named sections**. Each round: the solver answers
a batch of training questions using the *currently active* version of each
section; every wrong answer is programmatically detected (regex-extracted
answer vs. gold), then sent to a judge LLM that names which single section is
most responsible; the optimizer LLM rewrites *only* that section using the
failures + some correctly-solved gold examples as context; a regression gate
re-runs the OLD and NEW prompt on a held-out pool of previously-correct
examples, and only accepts ("commits") the rewrite if accuracy doesn't drop
more than `ρ` (default 2%) — otherwise it's rejected and the old text stays.
Repeat for `max_rounds`. Everything — every version of every section, every
gate decision, every dollar spent — is written to disk as it happens.

## 2. Who plays which role

Three LLM roles, each independently configured in `.env` (`src/fdpo/config.py:26-50`):

| Role | What it does | Current model | How often it's called |
|---|---|---|---|
| **solver** | answers the actual question — this is "the model under test" | `gpt-4o-mini` (Azure resource `aifeedbackloop`) | every train/test example, every round — by far the most calls |
| **judge** | given a wrong answer, decides which section caused it | `gpt-4.1` (Azure resource `shift-llm`) | only on incorrect examples |
| **optimizer** | rewrites the implicated section | `gpt-4.1` (same resource as judge) | only when a section has ≥1 attributed failure |

This asymmetry (weak solver, strong judge/optimizer) is deliberate — see
`progress.md`'s course-correction notes. It's also why judge/optimizer calls
are a small fraction of total API calls: in the real run referenced below,
158 solver calls vs. 7 judge + 3 optimizer calls.

`load_role()` (`src/fdpo/config.py:26-50`) resolves each role from `.env`:
role-specific `{ROLE}_MODEL/BASE_URL/API_KEY/API_VERSION` vars take priority;
anything left unset falls back to the shared `AZURE_OPENAI_*` vars. A
non-empty `api_version` tells `OpenAICompatClient` (`src/fdpo/clients/openai_client.py`)
to build an `AzureOpenAI` client instead of a plain `OpenAI` client (Azure
needs a different auth header + an `api-version` query param).

## 3. The prompt: schema + actual seed text

A prompt is just an ordered dict of named sections (`src/fdpo/core/prompt.py:10`):

```python
SCHEMA_5 = ("system_role", "context", "task_details", "constraints", "output_format")
```

(`monolithic-FDPO`, an ablation baseline, uses a single `full_prompt` section
instead — same loop, same gate, just no attribution granularity.)

At render time (`render_messages`, `src/fdpo/core/prompt.py:32-41`) the 5
sections are concatenated into ONE system message headed by `## <Title>` per
section, then any few-shot exemplar pairs, then the actual question — so the
solver only ever sees one system message + the question, never the section
boundaries as separate API messages.

**This is the actual GSM8K seed prompt** (version 0 of every section, before
any optimization — `src/fdpo/prompts/seeds.py:13-21`):

| Section | Seed text |
|---|---|
| `system_role` | "You are a careful math tutor who solves word problems." |
| `context` | "You will be given a grade-school math word problem." |
| `task_details` | "Solve the problem step by step, showing your arithmetic." |
| `constraints` | "Do not skip steps. Do not invent quantities that are not in the problem." |
| `output_format` | "After your reasoning, write the final numeric answer on its own line in exactly this form: `#### <number>`" |

Every dataset (`gsm8k`, `arc`, `mmlu`, `legalbench_hearsay`) has its own hand-written
seed set in the same file — deliberately plain, since they're the starting
point FDPO is supposed to improve. The `output_format` section for each
dataset is written to exactly match its answer-extraction regex (see §4) —
if you ever edit a seed's output format, the corresponding regex in
`src/fdpo/data/extraction.py` must still match it.

## 4. Datasets: HuggingFace → committed files → seeded subsamples

Datasets are fetched **once**, not at run time:

```
scripts/download_datasets.py  →  src/fdpo/data/hf_fetch.py  →  Dataset/<name>/{train,test}.jsonl
```

`hf_fetch.py` deliberately avoids the `datasets` library's `load_dataset()`
(its "xet" backend hangs behind this network's TLS-inspecting proxy) and
instead hits the HF `datasets-server` parquet API directly via plain
`requests` + `truststore` (bridges the OS trust store into Python's SSL
context). Every experiment run reads ONLY the committed `Dataset/*.jsonl`
files (`src/fdpo/data/loaders.py`) — zero HuggingFace calls at run time, so
a fresh `git clone` (e.g. on TAMU's cluster) works offline and both sites see
byte-identical examples.

Currently committed:

| Dataset | Train rows | Test rows | Notes |
|---|---|---|---|
| `gsm8k` | 7,473 | 1,319 | full official GSM8K split |
| `arc` (ARC-Challenge) | 1,119 | 1,172 | full official split |
| `legalbench_hearsay` | 5 | 94 | **entire upstream task is only 99 examples** — see the shortfall handling below |
| `mmlu` | not yet fetched | — | loader/fetcher ready, not needed for the current smoke matrix |

`load_splits()` (`src/fdpo/data/loaders.py:89-114`) does a **seeded shuffle**
(same `--seed` ⇒ same examples, every machine) and subsamples to
`--n-train`/`--n-test`. Special case for tiny pools like LegalBench-hearsay:
if the committed train pool is smaller than `--n-train`, the shortfall is
carved out of the *shuffled test pool* first (before test subsampling), so
train and test never overlap — but this means you must NOT use the default
`--n-train 150 --n-test 200` on `legalbench_hearsay` (only 99 examples total)
or the test set gets drained to zero. Use small explicit sizes for that one.

Each `Example` (`src/fdpo/data/loaders.py:30-36`) is `{id, question, gold,
reference, meta}` — `question` is the fully-formatted prompt-ready text
(multiple-choice options already inlined as `A. ... B. ...`), `gold` is the
normalized answer used for verdicts, `reference` is the full solution/answer
text (fed to the judge for context).

## 5. Answer verdicts are programmatic, not LLM-judged

This is the most commonly misunderstood part: **whether an answer is
"correct" is decided by regex + exact match, never by an LLM** (default
`--verdict-mode programmatic`; `--verdict-mode llm` exists for an ablation
but isn't the default path). Per dataset (`src/fdpo/data/extraction.py`):

- **GSM8K**: extract the number after `####` (or the last number in the text
  if that's missing) → compare as floats, `abs(pred - gold) < 1e-6`.
- **ARC / MMLU**: extract the letter after `Answer:` (or the last standalone
  `A`–`E` letter) → case-insensitive string match.
- **LegalBench-hearsay**: extract `Yes`/`No` after `Answer:` (or standalone)
  → case-insensitive string match.

The judge LLM is called **only after** an answer has already been
programmatically marked wrong — its job is purely diagnostic (which section
caused it, why), never to decide correctness.

## 6. One full round, walked through with real numbers

This is what actually happened in a completed run
(`results/smoke/gsm8k_fdpo_gpt-4o-mini_s1_20260705-133900/`, gpt-4o-mini
solver, 15 train / 15 test, `ρ=0.02`):

**Step 0 — seed eval.** Solver answers all 15 test questions with the
version-0 prompt → 100% test accuracy logged as `seed_test` in `metrics.json`.

**Round 1 — evaluate on train** (`src/fdpo/core/loop.py:52-59`). Solver
answers the 15 train questions with the active prompt → 80% train accuracy
(12/15 correct). This is lower than the test accuracy purely due to which
15 examples got sampled into train vs. test — expected sampling noise at
this toy scale.

**Round 1 — verdict + attribution** (`loop.py:61-88`). Each of the 3 wrong
answers is sent to the judge (`src/fdpo/prompts/judge_prompt.py`), which gets
the full sectioned prompt, the question, the model's raw output, and the
reference solution, and must return strict JSON:
```json
{"verdict": "incorrect", "critique": "...", "section": "task_details", "error_type": "WRONG"}
```
All 3 failures were attributed to `task_details`. (If the judge said
`"multiple"`, the failure would be replicated into every named section's
bucket; `"none"` just gets logged, no rewrite triggered — and if the judge's
JSON is malformed, `judge_failure()` retries once with a corrective message,
then falls back to `section="none"` rather than crashing the run —
`src/fdpo/core/judge.py:56-81`.)

**Round 1 — rewrite** (`loop.py:90-104`, `src/fdpo/prompts/optimizer_prompt.py`).
The optimizer gets: the current `task_details` text, the *other* 4 sections
as read-only context, up to 5 sampled failures (question + wrong output +
judge's critique), and up to 3 gold (correctly-solved) examples. It's
instructed to rewrite ONLY the target section, addressing the failure
patterns while keeping what works. The actual rewrite it produced:

> Seed (v0): *"Solve the problem step by step, showing your arithmetic."*
>
> → New (v1): *"Work through the problem step by step, carefully showing
> calculations and using the correct mathematical relationships described in
> the problem. Clearly state what each quantity represents, and methodically
> check that each step matches the information given."*

**Round 1 — regression gate** (`loop.py:106-122`, `src/fdpo/core/gate.py`).
`evaluate_candidate()` runs BOTH the old and new full prompts on a sampled
batch of previously-correct examples from the rolling `CorrectPool` (12
correct examples were available; batch size 12), plus separately re-checks
the 3 triggering failures with the NEW prompt only (for a non-gating
"recovery" measurement). Result: `acc_old=1.0 → acc_new=1.0` on the gate
batch (nothing broke), and 1 of the 3 original failures now solved. Since
`1.0 ≥ 1.0 - 0.02`, the gate **passes** → `PromptRegistry.commit()`
(`src/fdpo/core/registry.py:78-88`) archives v0 and activates v1.

**Round 2 — another rewrite attempt on `task_details`.** New candidate (v2):

> *"Follow the sequence of events or operations exactly as described in the
> problem. For each step, use only the quantities and relationships given
> ..."*

Gate result: `acc_old=1.0 → acc_new=0.923` on a 13-example batch — one
previously-correct example now broke, and neither of the 2 triggering
failures recovered. `0.923 < 1.0 - 0.02` → gate **rejects**. The rewrite is
recorded (status `"rejected"`) but the active version stays v1.
`PromptRegistry.record_round_acc()` also tracks stagnation here — 2 rounds
in a row with no improvement over the section's best-known accuracy.

**Round 3 — same pattern, same rejection.** After `--stagnation-limit`
consecutive stagnant rounds, `restore_best_snapshot()`
(`registry.py:110-118`) would roll the section back to its best-ever version
— in this run v1 already *was* the best, so nothing changes.

**Stabilization / early stop** (`loop.py:142-150`): once 4 consecutive round
accuracies vary by less than `ε` (default 0.01), the run records
`time_to_stabilization` and stops early if `--no-early-stop` wasn't passed
(this run hit `max_rounds=3` before that triggered, so it ran all 3).

**Final eval.** Solver re-answers all 15 test questions with whatever prompt
is active at the end (still 100%, since the 5-section GSM8K prompt was
already easy for gpt-4o-mini on this small sample) → `final_test` in
`metrics.json`.

The full version history above — including the 2 rejected candidates, their
exact gate numbers, and which round each happened in — is exactly what's
persisted in `registry.json` for that run. Nothing is summarized away; every
candidate the optimizer ever proposed is on disk.

## 7. Everything that lands on disk, per run

`results/<phase>/<run_id>/` (`src/fdpo/utils/io.py`,
`scripts/run_experiment.py:30-123`), where `run_id` is
`<dataset>_<method>_<solver-model-slug>_s<seed>_<timestamp>`:

| File | Written by | Content |
|---|---|---|
| `config.json` | once, at start | every `ExperimentConfig` field (API keys deliberately excluded) |
| `run.log` | throughout | same lines as the console, persisted |
| `registry.json` | after every commit/reject/restore | full section version history (see §6) |
| `train_log.csv` | every round | per-train-example: correct?, pred, gold, attributed section |
| `rounds_log.csv` | every rewrite attempt | section, n_failures, acc_old, acc_new, passed, broke, recovered, batch_size |
| `ledger.csv` | every API call | role, model, prompt/completion tokens, cost_usd, purpose |
| `events.jsonl` | every rewrite | structured event log (debugging aid) |
| `eval_log.csv` | seed + final eval | per-test-example: correct?, pred, gold, phase (`seed`/`final`) |
| `metrics.json` | once, at end | the full summary — see below |

`metrics.json` is the one file meant to be read directly:
```jsonc
{
  "status": "completed",                 // or "budget_aborted"
  "seed_test": {"accuracy": 1.0, ...},   // before optimization
  "final_test": {"accuracy": 1.0, ...},  // after optimization
  "optimization": {"rounds_run": 3, "train_acc_per_round": [...], "registry_counts": {"commits": 1, "rejects": 2}},
  "cost": {"total_calls": 168, "total_cost_usd": 0.0715, "by_role": {...}},
  "fdpo_metrics": {
    "regression_rate": 0.0,                    // fraction of gate-batch examples broken by committed rewrites
    "section_attribution_accuracy": 0.333,      // fraction of triggering failures a committed rewrite actually fixed
    "cost_per_accuracy_point_usd": null,        // optimization $ / (final_acc - seed_acc) percentage points
    "n_commits": 1, "n_rollbacks": 2
  }
}
```
These 4 `fdpo_metrics` are FDPO-specific (not standard NLP metrics) and are
computed in `src/fdpo/eval/metrics.py:38-76` purely from the rewrite records
— no extra API calls needed to compute them.

## 8. Cost tracking & the budget guard

Every single API call goes through `ModelClient.complete()`
(`src/fdpo/clients/base.py:34-44`), which unconditionally reports
`(role, model, prompt_tokens, completion_tokens)` to a `TokenLedger`, prices
it via a hardcoded substring-matched table (`src/fdpo/utils/budget.py:18-25`
— e.g. `gpt-4o-mini`, `gpt-4.1`, `deepseek`, `llama`), and appends a row to
`ledger.csv`. After every call, `BudgetGuard.check()` compares cumulative
spend to `--budget-usd`; on breach it raises `BudgetExceededError`, which
`run()` catches, writes `status="budget_aborted"` with whatever partial
results exist, and exits cleanly — a run can never silently overspend past
its cap, **provided the model is in the price table** (unpriced models
silently cost $0 in the ledger — this bit us once already; always confirm a
new model is in `PRICE_TABLE` before a real-money run, or pass
`--price-in`/`--price-out` explicitly).

`scripts/run_smoke.py` additionally tracks a *cumulative* cap across all runs
in the matrix (`--budget-usd`, default $25), skipping remaining
dataset/method combinations once less than $0.50 is left.

## 9. Baselines — same data/eval, no optimization

`src/fdpo/baselines/cot.py` builds the two non-FDPO comparison methods:

- **`zeroshot_cot`**: the seed 5-section prompt as-is, no optimization loop.
- **`fewshot_cot`**: same seed prompt + a few (`--n-shots`, default 4)
  worked examples as user/assistant turns before the real question. The
  exemplars are carved out of `train` first and never appear in
  optimization/eval for that run (`scripts/run_experiment.py:60-64`).
- **`monolithic`**: FDPO's full loop (judge → optimize → gate), but on the
  1-section `SCHEMA_MONOLITHIC` schema instead of 5 sections — this is
  ablation A1, isolating whether *sectioning* itself matters vs. just having
  a feedback loop at all.
- **`fdpo`**: the real thing, 5 sections.

All four share the exact same data loader, evaluator, extraction, and
metrics code — the only difference is prompt construction, so comparisons
are apples-to-apples.

## 10. How to actually run things

**One experiment** (what we've been running for validation):
```powershell
uv run python -m scripts.run_experiment --method fdpo --dataset gsm8k `
  --n-train 15 --n-test 15 --max-rounds 3 --budget-usd 1 --seed 1
```

**The full $25 Phase-0 smoke matrix** (2 datasets × 4 methods, one shared
cumulative budget):
```powershell
uv run python -m scripts.run_smoke --budget-usd 25
```

**Roll every run's `metrics.json` into one file** for cross-run comparison:
```powershell
uv run python -m scripts.build_results_summary
```
→ `results/summary.json`, one row per run (`scripts/build_results_summary.py:16-40`)
with accuracy before/after, cost, commits/rollbacks — this is the file to
eyeball or load into a notebook once real runs exist.

**Offline, zero-cost sanity check** (mock client, no network, no API keys
needed — what the 64 pytest tests use):
```powershell
uv run python -m scripts.run_experiment --dry-run --method fdpo --dataset gsm8k
uv run python -m pytest
```

## 11. Key config flags (`src/fdpo/config.py`)

| Flag | Default | Meaning |
|---|---|---|
| `--method` | `fdpo` | `zeroshot_cot` \| `fewshot_cot` \| `monolithic` \| `fdpo` |
| `--dataset` | `gsm8k` | `gsm8k` \| `arc` \| `mmlu` \| `legalbench_hearsay` |
| `--n-train` / `--n-test` | 150 / 200 | subsample sizes (careful with `legalbench_hearsay`, only 99 total — see §4) |
| `--max-rounds` | 5 | optimization rounds |
| `--rho` | 0.02 | regression gate tolerance |
| `--eps` | 0.01 | stabilization threshold (train-acc delta over 4 rounds) |
| `--n-fail` / `--n-gold` | 5 / 3 | failures / gold examples shown to the optimizer per rewrite |
| `--gate-batch-size` | 20 | correct-pool sample size per gate check |
| `--stagnation-limit` | 3 | stagnant rounds before best-snapshot restore |
| `--budget-usd` | 4.0 | per-run hard cap; `≤0` disables the guard |
| `--seed` | 0 | controls both data sampling and optimizer sampling — same seed ⇒ reproducible run |
| `--dry-run` | off | mock client, zero cost, zero network |

Model/endpoint/key are **never** flags — they live only in `.env`
(`SOLVER_MODEL`/`JUDGE_MODEL`/`OPTIMIZER_MODEL` + `_BASE_URL`/`_API_KEY`/
`_API_VERSION`, or the shared `AZURE_OPENAI_*` fallback), so the exact same
command runs identically at TAMU with only `.env` changed.

## 12. File map (annotated)

See `progress.md`'s "Project structure" section for the full annotated tree
— it hasn't changed since this doc was written, so it isn't duplicated here
to avoid drift between two copies.
