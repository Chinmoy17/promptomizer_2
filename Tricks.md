# Tricks.md — how to honestly move our headline number

**Purpose**: this file is a working reference for things we can do to make
our result stronger, and things we should not do. It is not a plan; it is
a menu.

The verified baseline we are moving from:

> **LegalBench-hearsay, `simple_fdpo`, `gpt-4o-mini` solver, `gpt-4.1`
> optimizer, single-pass, 3 seeds stratified: 65.0 % → 72.3 % mean
> (+7.4 pp mean).**

For context, Trace2Policy on the same task with 2 rounds and stronger
executors reports +9.4 (Opus), +14.1 (Haiku), +10.9 (Kimi) — mean +11.5.
"Knowing How to Edit" on the LegalBench definition-classification task
(closely related, not the same) reports +7 on GPT-4o and +15 on
LLaMA-3-8B. Our +7.4 is at the low end of published range but is
within the range and is measured with stricter methodology (3 seeds,
fixed test across seeds, confusion matrix per run) than either paper.

---

## Section A — legitimate moves that would raise the number

Ordered by expected return per hour of work.

### A1. Add a second refinement round with best-snapshot rescue

- What: run the optimizer 1-3 times instead of once, count failures on
  train after each round, keep the version with the lowest failure count,
  stop as soon as a round regresses on train.
- Cost: ~$0.30 across 3 seeds, ~15 min of wall time.
- Expected gain: **+2 to +5 pp** on top of the +7.4. Basis: Trace2Policy
  Table 5 R1 → R2 shows lifts of +6.3 (Opus), +7.9 (Haiku), +14 (Kimi).
  Our gain would be smaller because we already commit our R1 (they don't
  commit R1 as the final artifact; they use R1 as intermediate).
- Why safe: the "best-snapshot rescue" part means a bad second round is
  reverted, so we cannot lose ground versus single-pass.

### A2. Add dataset-specific task descriptions in the optimizer system prompt

- What: inject a one-sentence task description per dataset ("binary
  hearsay classification under FRE 801" for legalbench_hearsay, etc.)
  into the optimizer's system message. No error-mode hints — just a
  description of what the underlying task actually is.
- Cost: ~15 min of code, no additional API cost.
- Expected gain: **+0 to +3 pp**. Low but nonzero. The optimizer already
  sees the task's own instructions inside the current markdown; a task
  description in the system prompt mostly helps disambiguate ambiguous
  cases (e.g., "is this a math task or a language task?").
- Why safe: task descriptions are public knowledge about the benchmark,
  not information leakage from the test set.

### A3. Run zero-shot CoT + few-shot CoT + monolithic-rewrite baselines on the same 59 test items

- What: run the three baselines that already exist in the codebase
  (`--method zeroshot_cot`, `--method fewshot_cot`, `--method monolithic`)
  on the same LegalBench-hearsay test set across the same 3 seeds.
  Report our +7.4 alongside these three baseline deltas.
- Cost: ~$0.30 total, ~15 min of wall time.
- Expected gain: no change to our number, but it makes our claim
  *defensible*. Without these baselines, our result can be dismissed as
  "any prompt rewrite would help." With them, we can point to a specific
  gap over the strongest baseline.
- Why safe: this is standard practice in any prompt-optimization paper.
  Reviewers will ask for it if we do not include it.

### A4. Test with a stronger closed-model executor as an ablation

- What: rerun the LegalBench-hearsay + MMLU experiments with gpt-4o
  (full, not mini) as the solver, keeping gpt-4.1 as optimizer.
- Cost: ~$1.50 total (~15× the token cost of gpt-4o-mini across 3 seeds
  and 2 datasets). ~30 min of wall time.
- Expected gain (LegalBench): +3 to +5 pp on baseline, delta size
  probably similar or slightly smaller (gpt-4o may already be closer to
  ceiling on hearsay).
- Expected gain (MMLU): higher baseline (65-70 %) with delta likely
  around +2 to +3 pp — the "amplifier not injector" story predicts
  smaller relative gains on stronger executors, and this run would
  confirm it.
- Why safe: this is an ablation, not a headline. The paper's main
  contribution can stay grounded on gpt-4o-mini (the practically-relevant
  small-model case) with gpt-4o included as an additional row.

### A5. Broaden LegalBench to 3-4 tasks

- What: add `definition_extraction`, `contract_nli`, `rule_qa` (or any
  three related LegalBench tasks with ≥ 100 test examples). Write a
  starting `prompts/<task>.md` for each and run 3 seeds through
  simple_fdpo on each.
- Cost: ~$1.50 total, several hours of setup (writing the starting
  prompts and downloading each dataset), ~30 min of runtime.
- Expected gain: turns "single-task result that might not generalize"
  into "task-family result across N tasks." Even if some tasks show
  smaller gains, the family average is a much less dismissable claim
  than a single 59-item result.
- Why safe: increasing task coverage is the standard response to any
  reviewer worry that a single-task result was cherry-picked.

### A6. Test-time majority voting

- What: at test time, run the optimized prompt 3-5 times per test
  question at temperature 0.3 and majority-vote. Report both the
  greedy (T=0) and the ensembled result.
- Cost: ~$0.30 to $1.00 depending on how many samples per question.
- Expected gain: **+1 to +3 pp**. Standard trick. Legitimate because
  it is a decoding-time change, not an evaluation manipulation.
- Why safe: nearly all published LLM benchmarks (including MMLU
  official) allow multi-sample voting. Just report both numbers.

### A7. Multi-seed the whole thing with more seeds

- What: run seeds 3-5 in addition to 0-2, report the mean of five instead
  of three.
- Cost: ~$0.10 per additional seed on LegalBench, ~$0.50 per additional
  seed on MMLU.
- Expected gain: tightens the confidence interval, may or may not raise
  the mean depending on whether seed 0-2 was above or below the true
  mean. Given seed 2 was our lowest (+3.4), adding more seeds could go
  either way.
- Why safe: more seeds is always methodologically stronger. The only
  risk is if we selectively drop the low seeds (see B1).

---

## Section B — improvements we should NOT do

Each of these would raise the reported number but at the cost of honesty
or defensibility.

### B1. Cherry-pick the best seed as the headline

Our seed 1 result is +10.2, close to Trace2Policy's Kimi number.
Reporting only seed 1 without disclosing seeds 0 and 2 is a form of
p-hacking. Do not do this. Reporting the **mean and range across 3
seeds** is the correct disclosure.

### B2. Drop the "Not introduced to prove truth" slice from the test set

Trace2Policy's Table 10 shows this slice regresses to 29-57 % in
R1 before recovering in R2 — it is a known hard subset. Removing it
from our test would inflate our number by roughly 3-5 pp. Do not do
this — it is transparent test-set cherry-picking.

### B3. Change the train/test split ratio to give more training data

We use 40 / 59. Increasing to 60 / 39 or 70 / 29 would give more
refinement signal at the cost of confidence in the test result.
Legitimate as an ablation ("how does gain scale with train size") but
NOT as a headline change — we would be reducing test power to inflate
the delta.

### B4. Only report accuracy for the majority class

The hearsay dataset is 43 Yes / 56 No. Reporting only No-class accuracy
(the class we do better on) would look better. Do not do this — it hides
the actual class-imbalanced accuracy and is misleading.

### B5. Silently drop extraction failures from the denominator

Some solver calls do not produce a valid "Answer: Yes/No" sentinel. We
currently count these as wrong. Reporting accuracy only over
successfully-extracted responses would inflate the number. Do not do
this — extraction failure is a real failure mode and belongs in the
denominator.

### B6. Iterate many times and report the highest test accuracy across rounds

If we ran 10 rounds and picked whichever round happened to score highest
on test, we would be **selecting on test**. The rescue mechanism in A1
selects on *train* failures only, which is legitimate. Selecting on test
is data leakage. Do not do this.

### B7. Run many random seeds and report the top three

Very close to B1. If we run seeds 0-9 and report only the three with the
highest gains, we are selecting on outcome. If we do more seeds, we
report the mean of all of them, not the mean of a subset.

---

## Section C — data-split changes: legitimate vs. cheating

### Legitimate

- **Move to 50/49 or matching Trace2Policy's ~32/68 ratio** for consistency
  with published work. Report the choice explicitly.
- **Stratified splits** (our current approach) — test set fixed across
  seeds, only train varies. This is a methodological strength.
- **Sample train from all 5 hearsay slices in proportional stratification**
  — we already do this and should keep it. It matches the class
  distribution and prevents slice bias in the training batch.

### Cheating

- **Adaptive train sampling** — putting easy cases in train and hard cases
  in test. This inflates baseline test accuracy and possibly the delta.
- **Selecting slices with the biggest baseline-to-optimized gain** —
  cherry-picking after the fact.
- **Making the test set overlap with train** — always wrong, obviously.

---

## Section D — framing tricks (present the same number better)

These are not manipulation, they are honest presentation choices.

### D1. Lead with the finding, not the number

**Bad framing** (competes on magnitude, loses):
> "We achieve +7.4 pp on LegalBench-hearsay."

**Good framing** (competes on mechanism, wins):
> "Prompt optimization behaves as a knowledge amplifier, not a knowledge
> injector. On tasks where the model has headroom, gains are consistent
> (+5 to +8 pp across three datasets and six MMLU subjects) and
> replicated across seeds. On tasks where the model is at chance, gains
> vanish. This is directly observable through per-question confusion
> matrices, which prior work does not report."

### D2. Put confusion matrices on the front page

Our unique contribution is the per-question instrumentation. On MMLU,
the +1.4 pp aggregate is unimpressive but the per-subject breakdown
(biology +5.3, philosophy +5.3, law 0.0, math 0.0) is the actual
finding. Front-load the breakdown.

### D3. Report cost explicitly

Trace2Policy quotes $5-10 per Auto-EISR cycle. Our runs are $0.04-0.16
per seed. We should report our cost — "$2 total pilot spend across all
datasets and both mechanism variants" is a real advantage for a
practitioner audience.

### D4. Frame single-pass as a feature, not a limitation

"Single-pass optimization with no gate, no rounds, no rollback — one
optimizer call per dataset" is a *strength* if positioned as "minimal
mechanism, maximal reproducibility." Do not apologize for the simplicity.

### D5. Multi-seed with fixed test as a methodological differentiator

Trace2Policy reports one seed at T=0. Knowing How to Edit does not
specify per-seed variance. We report three seeds with the test set
fixed across seeds. This is stricter — call it out explicitly.

---

## Section E — recommended priority order

If we could only do a handful of the above, in order:

1. **A1** (second round + rescue) — highest expected magnitude gain,
   cheap, safe.
2. **A3** (baselines head-to-head) — makes any number more defensible.
3. **A2** (dataset-specific task descriptions) — free, low risk.
4. **A5** (broaden LegalBench to 3-4 tasks) — turns single-task into
   task-family; most reviewer-friendly change.
5. **A6** (majority voting at test time) — cheap and standard.
6. **A4** (stronger executor ablation) — strengthens the amplifier story
   and covers the "does it generalize to bigger models" question.
7. **A7** (more seeds) — do last, only after the mechanism is settled.

An honest total: implementing 1-3 above should move the headline from
+7.4 to roughly **+10 to +13 pp mean** on LegalBench-hearsay, comparable
to Trace2Policy's Kimi result on the same task, with a stricter
methodology.

---

## Section F — what NOT to spend time on

- **Trying to match Trace2Policy's compilation-to-Python trick.** They
  gain 9.8 pp from converting rules to deterministic Python code at
  inference. That is a different design choice (trades LLM flexibility
  for rule determinism) and is only feasible on tasks with cleanly
  captured rule sets. Not applicable to us.
- **Trying to replicate "Knowing How to Edit."** Their method requires
  token log-probabilities that Azure OpenAI does not expose for
  gpt-4o-mini. Even if we could, their evaluator training pipeline
  (11,530 prompts × 10 executions each) is 100k+ API calls. Out of
  scope.
- **Chasing seed variance below ±2 pp.** Azure OpenAI is not
  bit-deterministic at temperature 0 (we measured ~3.4 pp swing across
  identical repeat runs). There is a hard floor on how tight our
  confidence intervals can be while using Azure. Getting under this
  floor requires local open-model deployment — which is exactly what the
  Texas A&M handoff is for.
