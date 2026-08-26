# FDPO Pilot — Progress Log

> Status as of 2026-07-05 (end of session). This file tracks WHAT HAS BEEN
> BUILT, WHAT WE'VE LEARNED EMPIRICALLY, and WHERE TO RESUME.
> For the experiment design and rationale, see [plan.md](plan.md).
> For the research proposal and algorithm, see [Docs/proposal.md](Docs/proposal.md)
> and [Docs/fdpo_experiment_plan.md](Docs/fdpo_experiment_plan.md).
> For exactly how the system works end-to-end, see [Codebase.md](Codebase.md).
> For the current (v2) mechanism architecture + full tunable-parameter
> reference, see [Docs/fdpo_mechanism.md](Docs/fdpo_mechanism.md) — **read
> this first when resuming**, it's the most detailed and most current doc.

## The plan, in one paragraph

FDPO optimizes a prompt by splitting it into 5 semantic sections, using an LLM
judge to blame failures on a specific section, editing the implicated
section(s), and gating every update with a regression check before committing
(rollback otherwise). The full research program is too expensive to run
alone, so it's split across two sites: **this machine** runs pilot/validation
work with Azure OpenAI models (gpt-4o-mini solver, gpt-4.1 judge + optimizer);
**Prof. Tarek Mahmud's group at Texas A&M** will clone this repo and run open
models (Llama-3-8B, Qwen3-8B, DeepSeek) on their cluster. Optimization is
**offline batch rounds only** for now.

## Status: mechanism built, validated, and redesigned once already (v1 → v2)

| Milestone | Status | Notes |
|---|---|---|
| M1 — Scaffold | ✅ Done | |
| M2 — Model clients + budget guard | ✅ Done | Azure OpenAI support added (role-based `.env`, `AzureOpenAI` client); price table gap for `gpt-4.1`/`gpt-4o-mini` found and fixed |
| M3 — Dataset loaders + extraction | ✅ Done | GSM8K (7473/1319), ARC-Challenge (1119/1172), LegalBench-hearsay (5/94) fetched; MMLU not yet fetched |
| M4 — Prompt schema + registry | ✅ Done, **redesigned once (v2)** | See "v2 architecture redesign" below |
| M5 — Judge / optimizer / gate | ✅ Done, **optimizer redesigned (v2)** | Judge unchanged; optimizer now does whole-prompt bundle edits, not sequential per-section rewrites |
| M6 — Offline batch loop + baselines + entry point | ✅ Done | |
| M7 — Smoke orchestrator + README | ✅ Done | |
| M8 — Live micro-runs | ✅ Done, extensively | See "Empirical findings" below — many real runs, not just one micro-run |
| M9 — $25 smoke run (full `run_smoke.py` matrix) | ⬜ Not started | Deliberately deferred — see "Where to resume" |
| M10 — Parallelized evaluation | ✅ Done (new) | `ThreadPoolExecutor` in `evaluate()`, ~10-25x wall-clock speedup confirmed empirically |
| M11 — `examples` schema section (contrastive worked examples) | ⬜ **Designed, not implemented** | See "Where to resume" — this is the most promising next architecture change |

**66 automated tests pass** (offline, mock client, zero cost).

---

## Empirical findings this session (2026-07-05) — the important part

Ran real, paid Azure API experiments across 3 datasets. Every run taught us
something concrete; none of them gave a clean "FDPO improves accuracy by X%"
headline, and that itself is the finding worth understanding before doing
more runs.

### Ceiling effects: gpt-4.1 and gpt-4o-mini are both too strong for GSM8K/ARC

| Dataset | Solver | Result |
|---|---|---|
| GSM8K | gpt-4.1 | 100% → 100% (toy n=10) |
| ARC-Challenge | gpt-4.1 | 100% → 100% (toy n=10) |
| GSM8K | gpt-4o-mini | 94.5% (n=200, zero-shot) |
| ARC-Challenge | gpt-4o-mini | 95.0% (n=300, zero-shot) |
| **LegalBench-hearsay** | gpt-4o-mini | **72.3%** (n=94, full test set, zero-shot) — real headroom, finally |

Why: GSM8K/ARC are heavily-benchmarked, near-saturated for any well-tuned
model, mini-tier or not. Confirmed independently by MPO's own published
numbers (see "Literature verification" below) — Llama-3-8B/Mistral-7B score
70-75% untuned on the *same* ARC-Challenge split, 20+ points below
gpt-4o-mini. **The ceiling is a property of our solver choice, not the
datasets** — this is exactly the model class TAMU will run, where real
headroom should exist on GSM8K/ARC too.

### A confirmed, fixed bug: the stagnation/tie logic was erasing real progress

First full-scale legalbench run (v1 architecture, `legalbench_hearsay_fdpo_gpt-4o-mini_s0_20260705-180022`):
`context` section committed 2 genuinely validated, zero-regression rewrites,
then got **rolled all the way back to the seed** because the registry only
counted *strict* improvement over a historical best as progress — a tie
("held steady, zero regressions") counted as stagnation. 3 ties in a row
triggered a full revert. Net effect: the *final* prompt for that entire run
was byte-for-byte identical to the seed, meaning the observed 72.9%→69.5%
accuracy "drop" was **not FDPO's doing at all** — it was pure inference
non-determinism on an unchanged prompt (gpt-4o-mini isn't bit-deterministic
even at `temperature=0`). Fixed in v2 (see below); fix directly verified
working on the rerun (ties now correctly preserved — `run_best_versions`
tracked `context: v5, constraints: v3`, not reverted to `v0`).

### Direct proof of inference non-determinism

Same seed prompt, same 59 test examples, run twice: **72.9%** vs **76.3%** —
a 3.4pp swing from literally nothing but re-running the identical
computation. This is a real, citable data point, not a guess: at this
model/dataset's scale, a few percentage points of any measured difference
could be pure noise, independent of any prompt change.

### The mechanism does real, traceable legal reasoning — with a real trade-off

v2 architecture rerun on legalbench (`legalbench_hearsay_fdpo_gpt-4o-mini_s0_20260705-191626`,
`--n-train 40 --n-test 59 --val-size 15`): 76.3% seed → 69.5% final. Traced
every flip on the test set precisely (`eval_log.csv`, cross-referenced
seed vs. final phase):

- **3 recovered** (wrong → right): e.g. `hearsay_test_31` — an in-court
  testimony case. The optimizer added *"statements made during the current
  trial or hearing are not hearsay"* to `context`, which is exactly the rule
  this example needed. Directly traceable, genuinely correct legal content.
- **7 newly broken** (right → wrong): e.g. `hearsay_test_61` — an email
  offered to prove a CEO's knowledge. The *same* new rule that helped
  `test_31` (an "offered for another purpose, e.g. knowledge/notice"
  exception) got **over-applied** here via surface keyword matching
  ("knew"/"knowledge") to a case where the email's truth is what's actually
  being relied on. A legally correct general rule, applied too broadly.

Conclusion: **the optimizer is doing genuine reasoning, not noise
generation** — but abstract prose rules have a wide, hard-to-fully-test
blast radius, and the validation slice (15-20 examples) doesn't have enough
coverage to catch every way a new rule could be over-applied before it ships.

### Literature verification: MPO paper is real, and confirms our design choices

Fetched and read the actual PDF (arXiv 2601.04055, Sharma & Henley, CMU, Jan
2026) — real paper, not hallucinated. Confirmed exact numbers (their "Untuned"
baseline = a static structured prompt, never optimized, same idea as our
`zeroshot_cot`). Their ARC-Challenge split (1,119 train / 1,172 test) is
**identical** to ours — a genuine size-matched comparison becomes possible
once TAMU runs Llama-3-8B/Mistral-7B on it. Also confirmed directly from the
primary text: **MPO has zero regression gate** (additive delta + dedup,
applied unconditionally every iteration) and reports no seeds, no variance,
no significance testing — the same rigor gaps our own `related_works.md`
flags. FDPO's regression gate is a real differentiator, not a paper claim
without substance.

---

## v2 architecture redesign (implemented this session)

Full spec: [Docs/fdpo_mechanism.md](Docs/fdpo_mechanism.md) §1-9. Summary of
what changed and why, all directly motivated by the bugs/weaknesses above:

1. **Stagnation fix** (`registry.py`): any gate **pass** resets
   `run_stagnant_rounds` to 0 and updates the best-known snapshot, tie or not.
2. **Fixed held-out validation slice** (`loop.py`): carved once per run from
   train, never resampled — replaces the old per-call resampled
   `gate_batch_size` (renamed `val_size`).
3. **Whole-prompt single-pass bundle updates**: judge attribution stays
   per-failure/per-section (unchanged — this is FDPO's actual claimed
   novelty vs. MPO/TextGrad), but instead of N sequential per-section
   rewrite→gate→commit cycles, ONE optimizer call proposes edits for every
   implicated section at once; gated and committed/rejected as one atomic
   bundle (Option A: reject-the-whole-bundle on failure, no bisection yet).
4. **Structured find/replace edit format**: optimizer returns
   `{"edits": [{"section", "find", "replace"}, ...]}`, applied
   programmatically; an unmatched `find` is skipped and logged, never crashes
   the run. (Honest caveat found on rerun: this doesn't yet force genuinely
   *minimal* edits — the optimizer can still set `find` = the whole section.
   Not yet solved — see "Where to resume".)
5. **Programmatic failure aggregation**: error_type histogram + keyword
   clustering computed in code, shown to the optimizer alongside raw
   failures (`optimizer.py: aggregate_failures()`).
6. **Richer optimizer context**: current full prompt + its validation
   accuracy, previous best full prompt + its accuracy, and this run's own
   history of past bundle attempts (`history_window`, default 3).
7. **Optimizer temperature dropped 1.0 → 0.3** — the old value was tuned for
   diversity, but diversity was producing lexical noise, not better
   candidates, and high temp makes exact-substring `find` reproduction
   unreliable.

Also implemented, orthogonal to the mechanism redesign:

- **Parallelized evaluation** (`evaluator.py`): `ThreadPoolExecutor` over
  independent solver calls within one eval batch. Confirmed **~12-25x**
  wall-clock speedup empirically (94-example batch: 18s parallel vs. ~3.5min
  sequential). `--max-workers` flag, default 8. Caught and fixed a real bug
  before it shipped: mock-client tests that script exact call-order via a
  shared response queue would have broken under concurrency — fixed by
  defaulting the bare function signature to sequential (`max_workers=1`) and
  only having production code paths opt into concurrency via `cfg.max_workers`.
- **`scripts/show_prompt.py`** — inspect any seed/active/best/full-history
  prompt, fully rendered as sent to the solver, with zero API calls.
- **`scripts/launch_run.ps1` / `scripts/watch_run.ps1`** — run and monitor
  experiments from your own terminal window, fully independent of any
  Claude Code session.

All 66 tests pass after the redesign (2 new, specifically covering the
stagnation-tie fix). Files touched: `config.py`, `registry.py`,
`optimizer.py`, `optimizer_prompt.py`, `loop.py`, `mock_client.py`,
`tests/test_registry.py`, `tests/test_loop_mock.py`. `gate.py` needed no
changes — its `evaluate_candidate()` already accepted arbitrary
old/new-section dicts and an externally-supplied batch.

---

## Where to resume — open decisions, in priority order

1. **The `examples` schema section (designed, not yet built).** Your own
   prior experience (a simpler human-feedback mechanism that also embedded
   concrete worked/contrastive examples into the prompt, not just abstract
   rules) directly explains the `test_61` over-generalization failure: an
   abstract rule ("offered to prove knowledge... not hearsay") has unbounded
   blast radius; a concrete contrastive example ("this case IS hearsay
   despite mentioning knowledge, because...") is inherently more bounded.
   Proposed design: add `examples` as a 6th schema section, judge-attributable
   and optimizer-editable exactly like the other 5, populated with concrete
   contrastive pairs rather than prose. **This is the most promising next
   change and is fully unimplemented** — needs: schema/seed updates, judge
   prompt tweak (does the taxonomy need a new case, or does "MISSING" already
   cover "missing a differentiating example"?), optimizer prompt update
   (instruct it to write contrastive examples, not rules), and a decision on
   how many examples per section / how they get selected for contrast.
2. **Stratify or diversify the validation slice** instead of random sampling
   — directly addresses why the gate didn't catch `test_61`/`test_21`-style
   over-generalization before it shipped. Cheap-ish, needs a
   clustering/tagging pass over train examples.
3. **Narrower-rule instruction to the optimizer** — explicit guidance to
   avoid single-keyword trigger conditions in prose rules. Trivial prompt
   change, worth doing regardless of whether #1 happens.
4. **Log the raw edit list** (`edit_log` from `apply_edits()` — which edits
   were proposed, applied, or skipped and why) to disk. Currently NOT
   persisted anywhere — we could only infer what happened from before/after
   text diffs during analysis. Should be in `events.jsonl` or similar.
5. **Hard-negative gold example selection** — bias gold sampling toward
   examples lexically similar to current failures but with the opposite
   label, for direct contrastive signal. Medium effort.
6. **Multi-seed, full-test-set, statistically rigorous runs** — deliberately
   deferred. Given ceiling effects + tiny-corpus noise on every dataset we
   have locally, this doesn't get us a trustworthy answer yet regardless of
   algorithm quality. **Recommendation: reserve this for TAMU's phase**,
   where weak-model headroom and larger/cheaper compute both exist. Local
   Azure runs should keep being used for mechanism validation and bug-hunting
   (which they've been very productive at), not for chasing a clean accuracy
   number.
7. **The $25 smoke matrix (`run_smoke.py`)** — also deliberately not run yet.
   Doesn't make sense to spend it until #1-4 above are decided, since
   they'll change what the loop actually does.

### Honest strategic takeaway (discussed at length, worth preserving verbatim)

The core mechanism (attribution + targeted edit + regression gate) looks
sound — every problem found this session was concrete and fixable, and we
have a directly-traced example (`test_31`) of it adding genuinely correct
domain knowledge. But we cannot yet say, with statistical confidence,
whether FDPO nets a real accuracy improvement — every local result is
confounded by ceiling effects, small-corpus noise, or proven inference
non-determinism of a similar magnitude to the effects we're trying to
measure. That question needs TAMU-scale data to answer honestly. It's also
worth going in accepting that the honest answer might be "no clean net win,
even at scale" — natural-language prompt edits may have an inherently wide
blast radius that no amount of algorithm tuning fully closes. That would
still be a real, defensible, publishable finding, especially given how much
of the surveyed literature reports single-run numbers without checking for
exactly this.

---

## Model / infra setup (for reference)

- **Solver**: `gpt-4o-mini` on Azure resource `aifeedbackloop`.
- **Judge + Optimizer**: `gpt-4.1` on Azure resource `shift-llm`.
- `.env` supports per-role overrides falling back to shared `AZURE_OPENAI_*`
  vars (`src/fdpo/config.py: load_role()`); `AzureOpenAI` client used
  automatically when `api_version` is set (`clients/openai_client.py`).
- Price table (`utils/budget.py`) includes `gpt-4o-mini`, `gpt-4.1`,
  `gpt-4.1-mini`, `gpt-4.1-nano` — **verify any new model is priced before a
  real-money run**, or the budget guard silently becomes a no-op.
- Full tunable-parameter reference (every `--flag`, default, and tuning
  guidance): [Docs/fdpo_mechanism.md](Docs/fdpo_mechanism.md) §10.

## Known issues / blockers

1. `Dataset/` and `results/` are populated on disk but **not yet committed to
   git** — needs `git add` + commit before TAMU can `git clone` and get
   identical data.
2. MMLU not fetched yet (not needed for anything run so far).
3. `edit_log` (raw find/replace proposals from the optimizer) is not
   persisted anywhere — see "Where to resume" #4.

---

## Session update — 2026-08-26: Claude Haiku 4.5 solver + gpt-5 optimizer; Trace2Policy LegalBench replication; test-leak finding + oracle diagnostic

**New model config**: solver = `claude-haiku-4-5-20251001` via Anthropic's
OpenAI-compatible endpoint (`https://api.anthropic.com/v1/`) — zero code
change, `.env` only. Critical gotcha: no `SOLVER_API_VERSION` line, or it
silently falls back to the shared `AZURE_OPENAI_API_VERSION` and routes
through the wrong (`AzureOpenAI`) client. Optimizer/judge = `gpt-5` on Azure
(`aifeedbackloop`) — needs `max_completion_tokens` instead of `max_tokens`
and no `temperature` override, handled by `_is_reasoning_model()` in
`openai_client.py`.

### Replicating Trace2Policy's LegalBench-hearsay protocol

Trace2Policy (arXiv:2606.10457, Appendix H) reports, for Claude Haiku 4.5 on
the 94-item LegalBench hearsay task (seed 42, 30-case iteration / 64-case
held-out): B1b baseline 79.7% → v_EISR (2 rounds, human-authored) 93.8%.

Ran the equivalent protocol with our mechanism (`--split-mode stratified
--n-train 30 --n-test 64 --seed 42 --simple-max-rounds 2 --simple-val-frac 0
--accept-margin 0.0`, solver=Claude Haiku 4.5, optimizer=gpt-5):

| | Baseline | Final | Delta |
|---|---:|---:|---:|
| Ours (sealed test, honest) | 68.8% (44/64) | 73.4% (47/64) | **+4.6 pp** |

Round 1 rewrote all 5 sections (mining 73.3%→90.0%, 8 recovered/3 regressed,
shipped); round 2 regressed on mining (83.3%) and was correctly **not**
shipped by the `--accept-margin 0.0` gate. Cost $0.09. Artifacts:
`results/hearsay_trace2policy_repl/legalbench_hearsay_simple_fdpo_claude-haiku-4-5-20251001_s42_20260826-140211/`.

Our baseline (68.8%) is well below theirs (79.7%) on the identical task —
likely their exact B1b phrasing ("Q: {text} Is there hearsay? A: Answer with
exactly Yes or No.") vs. our vague one-liner seed, not a solver capability gap.

### Finding: Trace2Policy's hearsay probe leaks the held-out set into training

Their own Appendix H states Round 1 was "diagnosed from v1's iter-30 errors
**plus Opus v1's heldout errors**" — their human curator read failures on
the 64-item "held-out" set and wrote rules to fix them. That set is not
actually held out from refinement. (Their *main* damage-audit study is clean
on this point — "two held-out sets ... disjoint from the pool" — the leak is
specific to the public LegalBench probe, the one comparable numbers come
from.) This plausibly explains a meaningful share of their reported gain.

### Oracle/leakage diagnostic: same leak, via LLM instead of a human

To quantify the leak's contribution, ran one deliberate oracle diagnostic
(`oracle_leak_check.py`, repo root — NOT part of the normal pipeline, NOT a
valid held-out result): pass the sealed 64-item test set in as the `train`
(mining) pool, so the gpt-5 optimizer sees the same 64 items' own failures
Trace2Policy's human curator saw.

| | Baseline | Final (oracle) | Delta |
|---|---:|---:|---:|
| Ours, test-exposed (leak) | 68.8% (44/64) | **95.3%** (61/64) | **+26.6 pp** |
| Trace2Policy, test-exposed (leak), Haiku 4.5 | 79.7% | 93.8% | +14.1 pp |

**An automated, 2-round, $0.15 LLM rewrite matches/exceeds a human curator's
multi-session rule-authoring, given the same test exposure.** This answers
"how much can FDPO gain via LLM vs. human rule-writing" (at least as much,
here) and reframes Trace2Policy's 93.8%: a large chunk of it is plausibly
explainable by the leak alone, not by EISR's mechanism. Artifacts:
`results/hearsay_ORACLE_LEAK_diagnostic/`, `oracle_leak_check.py`.

**Do not cite the 95.3% number as an FDPO result anywhere** — it is a
ceiling under test exposure, kept clearly separated (directory name, warning
log line, `oracle_summary.json`) from the legitimate 73.4% result above.
