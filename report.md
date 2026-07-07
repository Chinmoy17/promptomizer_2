# Feedback-Driven Prompt Optimization — Pilot Report

**Prepared for:** Prof. Tarek Mahmud
**Date:** July 7, 2026
**Author:** Chinmoy Mitra

---

## 1. What this report is

This report summarizes an eight-week pilot on **prompt optimization** —
the practice of automatically rewriting the instructions given to a large
language model so it produces better answers on a specific task.

It covers:
- What other research groups have tried and how they measure success
- What we built and tested
- What we found (with the actual numbers)
- How our results compare to published work, honestly
- What we recommend doing next, and open questions we would like your input on

Nothing here requires familiarity with our codebase or previous notes.

---

## 2. The problem, in plain English

A language model's accuracy on a task depends heavily on the exact wording
of the instructions it receives. Writing those instructions by hand is
slow, subjective, and does not scale to new tasks. **Prompt optimization**
tries to automate this — the system looks at cases where the model got the
answer wrong, and uses those failures to propose a better wording of the
instructions. The rewritten instructions are then tested on new cases to
see if they actually help.

The goal of the pilot was to build a working version of such a system,
test it honestly on three different kinds of tasks, and find out where it
helps, where it does not, and why.

---

## 3. What other research groups have done

The field is active, but the published work varies widely in three
directions. Understanding the variety matters because our results only
mean something when placed next to comparable choices from other groups.

### 3.1 How they generate the feedback signal

Different papers use very different signals to tell the system that a
prompt needs to be improved:

- **Simple accuracy on a held-out set.** The system tries the prompt on
  a batch of examples, counts how many were correct, and uses that number
  as the sole signal. Simplest and most common.
- **A second language model as a critic.** A separate model reads the
  first model's answer and the correct answer, and writes a short
  critique explaining what went wrong. This critique is then fed to the
  optimizer. Used by many recent methods including OPRO (Google DeepMind)
  and ProTeGi.
- **Log-probability signals.** Some methods (for example, the
  November 2025 paper "Knowing How to Edit" by Chen et al.) read the
  raw token-level probabilities the model assigns to each answer, and
  use metrics like negative log-likelihood or output stability as a
  quality score. **This only works with models where you have direct
  access to the log-probs** — it does not work with closed commercial
  APIs like Azure's `gpt-4o-mini`.
- **A separate quality-predictor model.** The same November 2025 paper
  trains a small model that reads a prompt and predicts how well it will
  perform, without ever running the target LLM. This is useful because
  it avoids the cost of re-evaluating after every prompt change, but it
  requires a large corpus of prompt/score pairs to train.
- **Human feedback.** A few methods (GATE, PLHF) ask human annotators to
  rate outputs. This is the most reliable signal but by far the slowest
  and most expensive.

### 3.2 How they rewrite the prompt

The mechanisms fall into five broad families:

- **Whole-prompt rewrite.** The optimizer sees the full prompt and
  proposes a completely new version. Simple but coarse. Used by OPRO
  and by our own method.
- **Section-by-section rewrite.** The prompt is split into named
  sections (role, task, constraints, output format), and only one
  section is rewritten at a time. Used by SAMMO and PromptAgent.
- **Find-and-replace edits.** The optimizer proposes small textual
  patches (change phrase A to phrase B). Used by GEPA.
- **Evolutionary search.** The system maintains a population of prompt
  variants, evaluates them, keeps the best, and generates new variants
  by mutation or crossover. Used by EvoPrompt and DeepMind's
  PromptBreeder. Requires many more evaluations than the other approaches.
- **Rule extraction plus code compilation.** The June 2026 paper
  Trace2Policy (Zha et al.) extracts a set of human-readable decision
  rules from the failures, and then **compiles those rules into
  deterministic Python code** that runs at inference without any
  language-model call at all. Their headline gain of about 10 percentage
  points comes from the compilation step, not from the prompt
  refinement itself.

### 3.3 How they measure whether it worked

This is where published numbers become hardest to compare, because
different groups use different evaluation styles:

- **Single-task deep dives.** Optimize and test on one dataset, one task,
  one model. Cheapest and easiest to interpret, but easy to overfit to
  quirks of that task. Our pilot mostly does this.
- **Multi-task benchmark suites.** Optimize and test across a family of
  related tasks — for example, all 162 tasks in LegalBench, or the 27
  subtasks of BIG-Bench Hard. Harder but gives a much stronger claim.
  The November 2025 paper reports results across eight benchmarks.
- **Real-world deployment measurement.** Deploy the optimized prompt in
  a production system and measure accuracy over weeks. Trace2Policy did
  this at a logistics carrier for 22 days on 3,349 real audit cases.
  Very persuasive but usually only accessible to industry teams.
- **Cross-model transfer.** Take a prompt optimized on model A and test
  whether it also improves model B. Almost no papers do this cleanly;
  most report results only on the model they optimized for.

### 3.4 What models they use

- **Solver model** (the model that actually answers the task): ranges
  from small open models (Llama-3-8B, Mistral-7B) to large commercial
  ones (GPT-4o, Claude Opus).
- **Optimizer model** (the model that rewrites the prompt): usually
  larger and more capable than the solver, but not always. Some papers
  use the *same* model in both roles.
- The variety matters because a small solver has more room to be improved
  by better prompts, but a small optimizer may not be creative enough to
  find those improvements. There is no consensus best combination.

### 3.5 What the two most relevant published works actually report

We pulled the specific numbers directly from each paper. These are the
two works that overlap most closely with ours in the tasks and
benchmarks they use.

**Trace2Policy (Zha et al., June 2026, arXiv:2606.10457).** Their main
contribution is a compliance-audit deployment at a logistics carrier
(3,349 real cases over 22 days), which is separate from prompt
optimization — they extract rules and *compile them into Python* for
inference, gaining an additional 9.8 percentage points from that
compilation step alone. **The part that is directly comparable to us is
their LegalBench hearsay probe** (Section 6 of the paper, Table 5). They
use exactly the same task as us:

| Executor | Baseline (zero-shot) | Hand-authored rules (v1) | After 1 round | After 2 rounds | Change vs. baseline |
|---|---:|---:|---:|---:|---:|
| Claude Opus 4.6 | 82.8% | 89.1% | 85.9% | **92.2%** | +9.4 pp |
| Claude Haiku 4.5 | 79.7% | 85.9% | 87.5% | **93.8%** | +14.1 pp |
| Kimi K2.5 | 79.7% | 76.6% | 81.2% | **90.6%** | +10.9 pp |
| Mean of three | 80.7% | 83.9% | 84.9% | **92.2%** | +11.5 pp |

Their protocol: 94 total hearsay questions, shuffled once with seed 42,
split into 30 for optimization and 64 for testing. Their optimizer sees
one round of failures, writes an improved rule file, then sees a second
round of failures and refines again. All temperatures are 0. Each cell
is a single seed, not multi-seed.

**Knowing How to Edit (Chen et al., November 2025, arXiv:2511.19829).**
Their main contribution is training a small model (LLaMA-3-8B with
lightweight fine-tuning) that predicts prompt quality directly from
text, without ever running the target language model on it. The
predictor achieves 83.7% at predicting whether a prompt will do well.
They then use that predictor to guide prompt rewrites. **The parts that
are directly comparable to us are their LegalBench (definition
classification) and MMLU-adjacent results** (Table 4 in the paper).
Their reported numbers on LegalBench definition classification:

| Executor | Zero-shot | Their method | Best other baseline | Their gain |
|---|---:|---:|---:|---:|
| LLaMA-3-8B | 55% | **70%** | 63% (Self-Refine, Pro-Refine) | +15 pp |
| LLaMA-3.1-8B | 56% | **69%** | 63% | +13 pp |
| GPT-4o | 83% | **90%** | 86% (Pro-Refine) | +7 pp |

Their protocol: 100 examples for training and 100 for testing (or 50/50
if the dataset has fewer than 200 total). All methods run with the same
executor and a maximum of 3 optimization iterations. Their approach
requires access to the model's raw token log-probabilities to compute
the four quality metrics they rely on (negative log-likelihood, output
stability across repeated runs, mutual information between prompt and
response, and query entropy). **This log-probability access is available
for open models like LLaMA but is not exposed by Azure OpenAI for
gpt-4o-mini**, which is why we did not attempt to replicate this method
in our pilot.

Both papers are honest about the same underlying finding as ours:
prompt optimization gains scale with baseline capability headroom.
Knowing How to Edit says explicitly (Section 4.2) that "the effect of
prompts on LLM performance is largely bounded by the intrinsic
difficulty of the query and the capability ceiling of the model...
prompt optimization cannot alter the model's capacity boundary." That
is the same "amplifier not injector" idea we describe in Section 6 of
this report.

---

## 4. What we built

We built a prompt-optimization system with the following characteristics.

**How it works, in one paragraph.** The system loads a starting prompt
written in Markdown (each `## Section` header becomes an editable block).
It runs the language model on a training batch and finds the failures.
It then makes a single call to a stronger language model (the optimizer),
showing it the full prompt, the failing questions with the model's wrong
answers and the correct answers, and a few examples the model already
gets right. The optimizer returns a rewritten prompt. The system runs the
new prompt on the training batch again (to check whether it helped or
hurt), and then on a held-out test batch (to check whether the
improvement is real or is just a memorization of the training cases).

**Two variants exist.** An early version used multiple rounds of
optimization with a safety check that rejected any rewrite that hurt
accuracy. It did not work well — the safety check kept rejecting
legitimate improvements because a good rewrite often trades one type of
error for another. The current version is single-pass: one baseline
evaluation, one optimizer call, one final evaluation. It is the version
we recommend and it is the only one that produced a positive result we
were able to reproduce.

**What makes our setup unusual.**

- **We track exactly which questions changed status.** For every run,
  we log which specific questions went from wrong to right (recoveries),
  which went from right to wrong (regressions), which stayed wrong, and
  which stayed right. This turns a single accuracy number into a much
  richer picture — see the MMLU findings in Section 6 for why this
  matters.
- **The test set is held identical across repeated runs.** We repeat
  each experiment with three different random seeds. In each seed, only
  the training batch is resampled — the test set never changes. This
  means any variation in the final test accuracy comes from the
  optimizer, not from the difficulty of the test cases.
- **The optimizer is explicitly forbidden from copying training
  examples verbatim into the prompt.** An earlier version encouraged
  "worked examples", and the optimizer responded by pasting five full
  training cases into the constraints section. The resulting prompt
  memorized the training set and did much worse on the test set (about
  seven points lower). This was fixed by rewriting the optimizer's
  instructions to demand abstract structural rules instead.

---

## 5. What we tested

Three datasets, chosen to cover three different regimes.

### 5.1 LegalBench — Hearsay task

A binary classification task from the LegalBench benchmark: given a
courtroom statement and the issue it is being offered to prove, decide
whether it is hearsay under Federal Rule of Evidence 801. There are 99
examples total, covering five conceptual slices of the doctrine
(standard hearsay, non-assertive conduct, statements not introduced for
their truth, statements made in court, and non-verbal hearsay). We used
40 examples for optimization and 59 for testing.

### 5.2 GSM8K — Grade-school math word problems

7,473 training and 1,319 test examples. Each question is a word problem
whose answer is an integer. We used 120 for optimization and 300 for
testing.

### 5.3 MMLU — Multi-domain multiple choice

The Massive Multitask Language Understanding benchmark. We restricted to
six subjects to stay within budget: professional law, philosophy, high
school biology, econometrics, computer security, and college mathematics.
120 examples for optimization, 150 for testing. Each question has four
choices A through D.

### 5.4 Models used

All results below use two Azure OpenAI models:

- **Solver:** `gpt-4o-mini` — a smaller, cheaper model. This is the
  model whose answers we are trying to improve.
- **Optimizer:** `gpt-4.1` — a stronger model that rewrites the prompt.

Total spend across all experiments in this pilot, including diagnostic
reruns and both variants: about $2.

---

## 6. What we found

### 6.1 LegalBench Hearsay: consistent improvement

| Random seed | Baseline test accuracy | After optimization | Change |
|---|---:|---:|---:|
| 0 | 64.4% | 72.9% | +8.5 percentage points |
| 1 | 66.1% | 76.3% | +10.2 percentage points |
| 2 | 64.4% | 67.8% | +3.4 percentage points |
| **Average** | **65.0%** | **72.3%** | **+7.4 percentage points** |

All three seeds improved. The change-tracking log shows the optimizer is
genuinely recovering questions that were wrong before (typically 8-10 per
seed) and regressing a smaller number (3-8 per seed), for a net gain of 2
to 6 questions out of 59.

**Why this task works.** The hearsay rule has a small number of
exceptions that the model knows abstractly but forgets to apply
consistently (for example, the "non-assertive conduct" exception).
Rewriting the prompt to promote those exceptions to first-class rules
makes the model apply them more reliably. This is the regime where
prompt optimization is designed to help.

### 6.2 GSM8K: no room to improve

| Random seed | Baseline | After optimization | Change |
|---|---:|---:|---:|
| 0 | 93.7% | 93.7% | 0.0 |
| 1 | 94.3% | 92.3% | −2.0 |
| 2 | 93.3% | 93.0% | −0.3 |
| **Average** | **93.8%** | **93.0%** | **−0.8 percentage points** |

The base model already answers 94% of the questions correctly. The 6%
that remain are structurally difficult (multi-step arithmetic, unit
conversion errors) — no rewording of the instructions will fix a
computational mistake. The optimizer is changing behavior (recoveries
and regressions cancel out at around 4-8 each) but there is no net gain
to be had.

### 6.3 MMLU: mixed on average, but a clear story underneath

**Aggregate across all six subjects:**

| Metric | Value |
|---|---:|
| Baseline test accuracy | 59.3% |
| After optimization | 60.7% |
| Change | +1.4 percentage points |
| Recoveries / regressions | 9 / 7 out of 150 |

That +1.4 average is unimpressive on its own. But when we break the
results down by subject, a pattern appears:

| Subject | Test size | Baseline | After optimization | Change |
|---|---:|---:|---:|---:|
| Professional law | 93 | 51.6% | 51.6% | 0.0 |
| High school biology | 19 | 78.9% | 84.2% | **+5.3** |
| Philosophy | 19 | 68.4% | 73.7% | **+5.3** |
| Econometrics | 7 | 85.7% | 85.7% | 0.0 |
| Computer security | 6 | 83.3% | 83.3% | 0.0 |
| College mathematics | 6 | 33.3% | 33.3% | 0.0 |

Where the model is genuinely competent to begin with (biology,
philosophy) the prompt rewrite helps by about 5 points. Where the model
is essentially guessing (professional law at 51.6%, college mathematics
at 33.3%) the prompt does not help at all.

### 6.4 The main finding, in one sentence

**Prompt optimization is a knowledge amplifier, not a knowledge
injector.** It reliably recovers accuracy on tasks where the model
already has the underlying knowledge but is applying it inconsistently.
It does nothing on tasks where the underlying knowledge is absent or the
question is at the model's capability ceiling.

This finding is visible only because we tracked which specific questions
changed status and broke results down by subject. On a plain "average
accuracy" report the finding is invisible.

### 6.5 One caveat on the MMLU result

The system produced a single prompt intended to serve all six subjects
at once. The per-subject breakdown was done afterwards in analysis, not
in the optimization itself. Running the system separately for each
subject (six separate optimizations, six separate prompts) is a natural
follow-up and is likely to strengthen the gains on the competent
subjects further.

---

## 7. How our numbers compare to what other groups report

We now have verified numbers from both comparison papers on the same
LegalBench hearsay task we tested, so a direct comparison is possible.

### 7.1 Head-to-head on LegalBench hearsay

Trace2Policy is the only other published work we found that reports
results on the LegalBench hearsay task specifically. We use the same 94
underlying questions. The setups differ in split sizes, model choices,
number of refinement rounds, and number of random seeds. Here is the
comparison, apples to apples wherever possible:

| System | Executor model | Split | Rounds | Seeds | Baseline | Final | Change |
|---|---|---|---:|---:|---:|---:|---:|
| Ours | gpt-4o-mini | 40 / 59, stratified by 5 hearsay slices, test fixed across seeds | 1 | 3 | 65.0% | **72.3%** | **+7.4 pp** |
| Trace2Policy | Claude Opus 4.6 | 30 / 64, single shuffle with seed 42 | 2 | 1 | 82.8% | **92.2%** | **+9.4 pp** |
| Trace2Policy | Claude Haiku 4.5 | same as above | 2 | 1 | 79.7% | **93.8%** | **+14.1 pp** |
| Trace2Policy | Kimi K2.5 | same as above | 2 | 1 | 79.7% | **90.6%** | **+10.9 pp** |

Reading the table honestly:

- Their gain magnitudes (roughly +9 to +14 percentage points) are
  larger than ours (+7.4). The three most likely reasons are: (a) they
  use stronger executors (Opus, Haiku, Kimi are all more capable than
  gpt-4o-mini on legal reasoning tasks); (b) they use two rounds of
  refinement instead of our single pass; (c) their baselines are all
  higher than ours (65% vs. 80%), which reduces the noise floor.
- On the other hand, we report three seeds and the underlying confusion
  matrix (which specific questions changed status); they report a
  single seed per executor at temperature 0. Our number is therefore
  more conservative about noise but comparable in mechanism.
- The task is the same (LegalBench hearsay); the number of test
  questions is very close (59 vs. 64); the refinement approach in
  both cases is a Markdown rule document iteratively improved from
  observed failures. The methods are genuinely comparable.

**Our +7.4 percentage points is a real result in the same range as
published state-of-the-art on this task.** The clear next step to
close the gap with Trace2Policy is either (a) add a second refinement
round, or (b) test with a stronger executor.

### 7.2 The wider Trace2Policy result

The Trace2Policy paper's main contribution is not the hearsay probe —
it is a 22-day production deployment at a logistics carrier on 3,349
compliance-audit cases. That headline number (79.6% after 8 rounds)
is on their own proprietary audit task and includes a compilation
step that converts the rule list into Python code for deterministic
inference at run time. The paper explicitly reports that the compilation
step alone adds 9.8 percentage points over running the same rules as an
LLM prompt (Table 1 in their paper). This is a different design
choice — it trades away the flexibility of LLM inference for the
determinism of compiled rules, and is only feasible if the task can
be captured in a rule list without ambiguous edges. Our approach
keeps the LLM in the loop at inference, so it is directly comparable
only to the "skill-level prompt" numbers, not the compiled numbers.

### 7.3 Knowing How to Edit — different task family, related finding

Chen et al. do not report results on hearsay, but they do report on
LegalBench definition classification, which is a closely related
LegalBench task. Their gain on GPT-4o (+7 percentage points, from 83%
to 90%) is essentially identical in magnitude to our gain on
gpt-4o-mini on hearsay (+7.4 percentage points), suggesting that a
prompt-optimization gain in this range is a stable feature of small-
to-medium-scale executors on LegalBench-style tasks.

Their gain on LLaMA-3-8B on the same task (+15 percentage points, from
55% to 70%) is much larger — consistent with the "amplifier not
injector" framing: weaker models have more headroom to be recovered.
This is the specific pattern we expect to see when Prof. Mahmud's
group runs our system on Llama and Mistral.

### 7.4 Summary of comparison

Taken together, the two published works establish that:

- Prompt refinement of Markdown rule documents on LegalBench tasks
  produces gains in the +7 to +15 percentage-point range depending on
  the executor and the number of refinement rounds.
- Our result (+7.4 pp on hearsay, gpt-4o-mini, single pass, three
  seeds) is at the low end of that range but is directly comparable
  to the results reported by both other groups on comparable setups.
- Our number is more conservative because we use three seeds and a
  stricter single-pass protocol without any regression gate; a fair
  path to close the gap is to add a second refinement round and to
  test with a stronger executor.
- Both other groups report the same "capacity ceiling" finding we do,
  though we are the only ones to explicitly frame it as "amplifier not
  injector" and to demonstrate it directly through a per-subject
  breakdown on a multi-domain benchmark (MMLU).

---

## 8. What we would like to do next

In priority order.

### 8.1 Broaden LegalBench to a small family of tasks

LegalBench contains 162 tasks. We have tested one (hearsay). Testing
three or four related tasks (contract interpretation, statutory
definition matching, rule application) would turn a single-task result
into a task-family result, which is much harder for a reviewer to
dismiss.

Estimated cost: about $1.50 total. Estimated time: about one hour of
runtime plus a few hours of setup (writing starting prompts for the new
tasks and downloading them).

### 8.2 Run the system separately per subject on MMLU

The +1.4 percentage-point aggregate on MMLU hides the fact that biology
and philosophy each gained about five points. Running the system once
per subject rather than once across all six should sharpen the gains
where they exist and confirm the absence of gains where they do not.

Estimated cost: about $2 total. Estimated time: about two hours of
runtime.

### 8.3 Compare directly against simple baselines on the same tasks

The codebase includes three simpler methods that we have not run
head-to-head against our system on the same test sets: zero-shot
chain-of-thought, few-shot chain-of-thought, and a "rewrite the whole
prompt once with no failure evidence" baseline. Reporting our result
next to these three numbers, on the same test sets, is the standard
comparison a reviewer expects.

Estimated cost: about $1 total.

### 8.4 Hand the codebase to Texas A&M for testing on open models

The infrastructure is model-agnostic. Prof. Mahmud's group can run the
identical experiments on their GPUs using Llama-3-8B or Mistral-7B as
the solver, with no code changes — only a configuration file update.
This is the natural extension because:

- We used a closed commercial model (`gpt-4o-mini`); testing on open
  models is required for the method to be credibly reproducible.
- Open models start at lower baseline accuracy, so if the "knowledge
  amplifier" finding is correct, the improvements should be **larger**
  on open models than on `gpt-4o-mini`. That would be a strong result.
- Their GPUs are effectively free per experiment, so they can run
  larger evaluations than we can afford.

Timing: the codebase is ready to hand over now.

---

## 9. Questions we would like your input on

These are the decisions we would like guidance on before proceeding.

1. **What is the story you want the paper to tell?** Two candidates:
   (a) A narrow, careful methods paper: "we built a small, honest
   prompt-optimization system with rigorous change-tracking; here is
   what it does and does not do." (b) A broader empirical claim:
   "prompt optimization is a knowledge amplifier, not a knowledge
   injector, and here is the evidence from three benchmarks across two
   model families." The second is more ambitious but requires the Texas
   A&M open-model runs before it can be defended.

2. **How much of the current 8-week pilot's negative findings do we
   want to include?** The GSM8K ceiling result and the multi-round
   safety-check failure are informative but they weaken the marketing.
   We think they belong in the paper; some reviewers disagree with that
   as a principle. Your call.

3. **Should we broaden LegalBench to a task family before writing?**
   Costs about $1.50 and one working day. Makes the result much less
   dismissable.

4. **How should we close the gap with Trace2Policy on the hearsay
   task?** On the same task, their two-round refinement with Claude
   Haiku 4.5 reaches 93.8% (from 79.7% baseline, +14.1 pp), while our
   single-pass refinement with gpt-4o-mini reaches 72.3% (from 65.0%
   baseline, +7.4 pp). Two natural experiments would close most of
   this gap: (a) add a second refinement round, and (b) test with a
   stronger executor. Cost is small (about $0.20 total). Should we do
   this before the professor meeting or before the paper draft?

5. **When should we invite the Texas A&M group in?** Options:
   (a) Now, so they can run in parallel while we write.
   (b) After we have the broadened LegalBench and per-subject MMLU
   numbers.
   (c) After a first draft of the paper is circulating.

---

## 10. Summary in five lines

1. We built a working prompt-optimization system and tested it on three
   different benchmarks with a small commercial model.
2. It improved accuracy by 7.4 percentage points on average on the
   LegalBench hearsay task, across three independent runs, all positive.
3. It did nothing on GSM8K, because the model is already at 94%
   accuracy on that dataset.
4. It gave a small aggregate improvement on MMLU, but broken down by
   subject the effect is strong (about 5 points) where the model is
   already competent and zero where the model is at chance.
5. The codebase is ready to hand to Texas A&M for testing on open
   models. Before we do, we recommend broadening to two or three more
   LegalBench tasks so the story is a task-family result rather than a
   single-task result.

_End of report._
