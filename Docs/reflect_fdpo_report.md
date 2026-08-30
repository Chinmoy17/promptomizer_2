# Reflective Feedback-Driven Prompt Optimization (`reflect_fdpo`): Results and Comparison to Prior Work

Draft material for a paper writeup. Status as of 2026-08-30. All numbers below come directly
from this repository's own experiment artifacts (`metrics.json` per run) or from
`Docs/datasets_and_benchmarks.md`, a separately-maintained literature table sourced from the
primary papers cited inline. No number in this document is estimated or interpolated.

## Abstract (draft)

We present `reflect_fdpo`, a reflective variant of feedback-driven prompt optimization in
which the optimizer is shown the measured per-item effect of its own previous rewrite —
recovered/regressed items on both a mining set and a held-out validation set, with full detail
— before writing the next revision. We evaluate it on five benchmarks spanning legal
classification (LegalBench-Hearsay), multi-subject multiple-choice QA (MMLU), verifiable
instruction-following (IFEval/IFBench), competition mathematics (AIME), and privacy-conscious
delegation (PUPA), using small, inexpensive solver models (GPT-4o-mini, Claude Haiku 4.5)
rather than the mid-scale models (Qwen3-8B, GPT-4.1 Mini) used by comparable prior work. We
report consistent, if noisy, positive deltas on most benchmarks, document two mechanism
ablations motivated directly by observed failure modes (removing an all-or-nothing
validation-gate revert; replacing "ship the last round" with "ship the best-scoring committed
round"), and are explicit throughout about where our results are — and are not — comparable to
prior published numbers.

## 1. Method

`reflect_fdpo` optimizes a single markdown-formatted prompt (five fixed sections: System Role,
Context, Task Details, Constraints, Output Format) against a small solver model, using a
larger reasoning model (GPT-5 in all experiments here) as both optimizer and judge. Each run
splits its training pool into a **mining** set (failures/successes shown to the optimizer) and
a **validation** set (held out from direct optimizer access to individual item content, but not
from aggregate feedback — see below); a separate, sealed **test** set is touched only for the
baseline and final evaluation and never during optimization.

The mechanism's distinguishing feature relative to a blind iterative-refinement baseline
(`simple_fdpo`, kept byte-identical throughout as a control arm) is **reflection**: from round 2
onward, the optimizer is shown, in full and without sampling:
- every mining item its own previous rewrite recovered or regressed, with the solver's new
  wrong output for regressions;
- the previous text of every prompt section it changed;
- every validation item recovered or regressed by that same rewrite, with the same detail.

This differs from prior LLM-as-optimizer methods (ProTeGi, GEPA, Trace2Policy) primarily in
*what* feedback is fed back: those methods show the proposer failure traces from the current
round, but not the measured causal effect — recovery/regression churn — of the proposer's own
previous edit on both a working set and a disjoint validation set simultaneously.

Two design choices were revised during development based on directly observed evidence rather
than a priori reasoning, and we report both as ablations (§5):

1. **Round-selection rule.** An earlier version shipped whichever round was simply *last*.
   Observed evidence (an MMLU run and a PUPA run, detailed in §5) showed this discarding
   rounds that scored measurably higher on validation — sometimes on both validation and the
   mining set simultaneously — purely because a worse round happened to come after them. The
   mechanism now ships whichever *committed* round scored best on validation (mining, if no
   validation split), reconstructing that round's exact prompt from full version history
   regardless of what committed afterward. It still never reverts to the untouched seed prompt
   once any round has committed.
2. **No accept-margin gate.** An earlier version reverted the entire run to the untouched seed
   if the last round's validation accuracy fell below the original baseline. This was removed
   after repeated same-configuration reruns showed validation-accuracy comparisons at these
   sample sizes (n≈25–32) are noisy enough that the gate discarded genuine, if modest, net
   gains as often as it caught real regressions (§5).

## 2. Experimental Setup

| Dataset | Task | Train pool → mining/val | Test | Solver(s) tested | Optimizer/Judge |
|---|---|---|---|---|---|
| LegalBench-Hearsay | binary hearsay classification (FRE 801) | 40–50 → ~50/50 split | 49–59 | Claude Haiku 4.5, GPT-4o-mini | GPT-5 |
| MMLU (6 subjects) | 4-way multiple-choice, per-subject balanced | 50 → 25/25 | 66 | GPT-4o-mini, Claude Haiku 4.5 | GPT-5 |
| IFEval / IFBench | verifiable instruction-following (mechanically checked constraints) | 200 / 40 → 100/100, 20/20 | 200 / 42 | GPT-4o-mini | GPT-5 |
| AIME (2022-24 → 2025) | competition mathematics, integer 0–999 answer | 90 → 58/32 | 30 | GPT-4o-mini, Claude Haiku 4.5, GPT-4.1 | GPT-5 |
| PUPA | privacy-conscious delegation (2-hop: redact → untrusted external call → synthesize) | 60 → 30/30 | 40 | GPT-4o-mini, Claude Haiku 4.5 | GPT-5 (+ GPT-4.1 as the fixed untrusted external model) |

All runs reported are **single-seed** unless otherwise noted; this is stated explicitly and
repeatedly below because it materially affects how every delta should be read (§4, §6).

## 3. Results by benchmark, with comparison to prior work

Each subsection separates *our* results from *prior published* results on the same nominal
benchmark, and states plainly what differs between the two setups (model scale, split size,
number of seeds, baseline construction) rather than presenting them as head-to-head.

### 3.1 LegalBench-Hearsay

| Method | Model(s) | Train/Test | Mechanism | Result | Notes |
|---|---|---|---|---|---|
| Trace2Policy / EISR | Claude Haiku 4.5 (1 of 6 tested) | 30/64 | clustered-error refinement, regression gate | 79.7%→93.8% (+14.1pp) | Public probe; the paper's own appendix shows one refinement round partly diagnosed from the nominally held-out test set — not fully sealed |
| FDPO (ours), sealed-test replication of the Trace2Policy protocol | Claude Haiku 4.5 solver, GPT-5 optimizer | 30/64 | single whole-prompt rewrite, 2 rounds | 68.8%→73.4% (+4.7pp) | Directly comparable protocol, genuinely sealed test, 1 seed |
| FDPO (ours), oracle/leak diagnostic | same | 64/64 (test used as mining pool) | same | 68.8%→95.3% (+26.6pp) | **Invalid as a result — diagnostic only.** Demonstrates test-set leakage alone can match or exceed the EISR gain |
| `reflect_fdpo` (ours), 4 identical-config reruns | Claude Haiku 4.5, GPT-5 | 50→25/25, 49 test | full reflection mechanism | final_test range **0.735–0.857** across 4 reruns of the *same* seed/config | Illustrates the noise floor directly — see §4 |

### 3.2 MMLU

| Method | Model | Scope | Result |
|---|---|---|---|
| MPO | LLaMA-3-8B-Instruct | full MMLU | 57.21%→61.50% (+4.29pp) |
| MPO | Mistral-7B-Instruct | full MMLU | 53.79%→55.50% (+1.71pp) |
| TextGrad (as run in MPO's own comparison) | LLaMA-3-8B-Instruct | full MMLU | 57.21%→56.40% (**−0.81pp**) |
| `reflect_fdpo` (ours), 6-subject sweep | GPT-4o-mini | 6 curated subjects, 50 train→25/25, 66 test | mean **+2.0pp** (5/6 subjects positive; college_mathematics +1.5, philosophy +3.0, econometrics +6.0, biology +1.5, professional_law +1.6, computer_security **−1.5**) |

Not directly comparable in absolute terms: MPO/TextGrad report full-MMLU aggregates (~57
subjects); ours is a 6-subject curated subset chosen for diversity (math/humanities/social
science/STEM/law/security) rather than full coverage. The direction and rough magnitude
(low-single-digit pp gains, one near-ceiling regression) are broadly consistent across both.

### 3.3 IFEval / IFBench

| Method | Model | Result |
|---|---|---|
| GEPA | Qwen3-8B | IFBench: 36.90→38.61 |
| GRPO (24,000 rollouts) | Qwen3-8B | IFBench: 36.90→35.88 (regression) |
| MIPROv2 | Qwen3-8B | IFBench: 36.90→36.22 (regression) |
| GEPA | GPT-4.1 Mini | IFBench: 47.79→52.72 |
| GEPA+Merge | GPT-4.1 Mini | IFBench: 47.79→**55.95** |
| `reflect_fdpo` (ours) | GPT-4o-mini | IFEval: 0.737→0.763 (reverted; same-prompt re-eval noise, not a real edit effect) |
| `reflect_fdpo` (ours), 2 runs | GPT-4o-mini | IFBench: 0.476→0.452 both runs (net regression, n=42, well inside the noise floor) |

**Caveat, stated plainly:** GEPA's IFBench score is produced by their own harness against a
different 58-constraint-type test set (294 items); we could not verify their score is on
identical units to our per-item pass/fail rate. Our own IFBench checker coverage is 82 of the
many constraint types present in the raw pool (see `ifeval_verifiers.py`), filtered to only
fully-covered items. These numbers should be read as two independent measurements of a related
but not identical construct, not a matched comparison.

### 3.4 AIME (2022-2024 train → AIME-2025 test)

| Method | Model | Result |
|---|---|---|
| Baseline (DSPy `ChainOfThought` scaffold) | Qwen3-8B | 27.33 |
| GRPO | Qwen3-8B | 27.33→38.00 |
| MIPROv2 | Qwen3-8B | 27.33→20.00 (regression) |
| GEPA | Qwen3-8B | 27.33→32.00 |
| Baseline (DSPy `ChainOfThought` scaffold) | GPT-4.1 Mini | 49.33 |
| GEPA | GPT-4.1 Mini | 49.33→59.33 |
| `reflect_fdpo` (ours) | GPT-4o-mini | 0.133→0.100 (reverted) |
| `reflect_fdpo` (ours) | Claude Haiku 4.5 | 0.267→**0.333** (+6.7pp; validation stayed ≥ baseline every round) |
| `reflect_fdpo` (ours) | GPT-4.1 | 0.300→0.300 (reverted) |

**Critical, verified caveat:** we confirmed directly from the GEPA paper (Appendix G.1) that
their AIME baseline is not a bare instruction — it is **DSPy's `ChainOfThought` module**, which
structurally forces a reasoning field into every generation before the answer. Our baseline is
a deliberately bare, vague markdown seed with no such structural scaffolding. This — not solver
capability alone — plausibly explains most of the gap between our baselines (13–30%) and
theirs (27–49%), and means baseline-to-baseline comparison here is not meaningful; only the
*direction and size of each method's own delta* is informative.

### 3.5 PUPA — the closest comparison we have

Unlike the other four benchmarks, PUPA's scoring formula — `(quality + (1 − leakage)) / 2` — is
one we implemented identically to the PAPILLON/GEPA construction, so this is the one benchmark
where our number and GEPA's are on the same measurement scale by construction (not merely by
report).

| Method | Model(s) | Result |
|---|---|---|
| Baseline | Qwen3-8B | 80.82 |
| GEPA | Qwen3-8B | 80.82→91.85 |
| Baseline | GPT-4.1 Mini | 78.57 |
| GEPA | GPT-4.1 Mini | 78.57→**94.47** |
| GEPA+Merge | GPT-4.1 Mini | 78.57→**96.46** |
| `reflect_fdpo` (ours) | GPT-4o-mini (local), GPT-4.1 (fixed external), GPT-5 (judge) | mean_score 0.685→**0.799** (+11.4pp; accuracy 0.553→0.658, +10.5pp; single seed, 60/40 pool; shipped round 3, under the pre-best-of-rounds mechanism, §5) |
| `reflect_fdpo` (ours) | Claude Haiku 4.5 (local), GPT-4.1 (fixed external), GPT-5 (judge) | mean_score 0.805→**0.843** (+3.8pp; accuracy 0.750→0.825, +7.5pp; single seed, 60/40 pool; shipped round 1, best_of_rounds; test confusion: 3 recovered, **0 regressed**) |

**What differs:** GEPA uses the paper's official 111 train / 111 val / 221 test split; we used
a 60-train (30 mining/30 val) / 40-test pool drawn from the same raw PUPA-New/PUPA-TNB data,
since the exact original 443-item split does not appear to be independently reproducible from
the public data alone (see below). Our local/trusted models (GPT-4o-mini, Claude Haiku 4.5) are
smaller than Qwen3-8B/GPT-4.1 Mini; our fixed "untrusted external" model (GPT-4.1) and judge
(GPT-5) were not verified to match GEPA's own choices for those roles. Single seed for both
runs. Despite all of this, the direction (baseline in the high-70s/low-80s, meaningful gain
from optimization) is consistent with GEPA's own finding that PUPA's redaction failure mode —
PII leakage — is unusually amenable to instruction-level fixes.

**GPT-4o-mini vs. Claude Haiku 4.5 on PUPA:** Haiku's baseline is already much stronger
out-of-the-box (accuracy 0.750 vs. 0.553; mean_score 0.805 vs. 0.685) — it is simply better at
the redaction/synthesis task before any optimization — leaving less ceiling headroom, which is
the likely reason its optimized mean_score gain is smaller in absolute terms (+3.8pp vs.
+11.4pp) despite its accuracy gain being comparable (+7.5pp vs. +10.5pp). Haiku's run is
notably cleaner on test: zero regressions (3 recovered, 0 regressed), vs. gpt-4o-mini's more
mixed churn. One data-quality caveat: the Haiku run's ledger reports `solver` cost as exactly
$0 — Anthropic's per-token pricing is not wired into this project's cost table, so the reported
total cost ($4.60) understates the true spend for that run (Anthropic bills separately); the
gpt-4o-mini run's $4.44 total is accurate since Azure OpenAI pricing is in the table.

## 4. The reproducibility finding that should qualify every number above

Four `reflect_fdpo` reruns of the **identical** LegalBench-Hearsay configuration (same seed,
same prompt, same split) produced final_test accuracies of 0.735, 0.755, 0.816, and 0.857 — a
12.2-point spread from nothing but LLM sampling variance at "temperature 0," not from any
change in method or data. Separately, a fully reverted MMLU run (byte-identical prompt,
evaluated once as `seed_test` and again as `final_test`) still showed 3 of 66 items flip
answers between the two identical evaluations. Binomial noise floors at the sample sizes used
here are large: roughly ±11pp at n=49, ±15pp at n=42, ±18pp at n=30–32, ±12pp at n=66. Nearly
every single-seed delta reported in §3 sits partly or fully inside its own noise band. This is
reported as a first-class finding, not a caveat to be buried: **any of the positive results
above should be read as "consistent with a real effect," not "proven," until replicated across
multiple seeds** — a limitation, not yet addressed, that a submitted paper would need to close
with multi-seed runs before making a confident claim.

## 5. Mechanism ablations (motivated by direct evidence, not a priori design)

**Ablation 1 — accept-margin gate.** The original mechanism reverted an entire run to the
untouched seed if the last round's validation accuracy fell below `baseline_val_acc −
accept_margin`. Removed after: (a) the reproducibility finding above showed validation-accuracy
comparisons at n≈25–32 are dominated by noise; (b) a concrete case (AIME, GPT-4.1 solver) where
*every* round, not just the last, stayed below baseline validation, making the revert
attributable to the whole trajectory rather than one unlucky round — but also showing the gate
had no way to distinguish "a genuinely bad trajectory" from "noise below baseline."

**Ablation 2 — round-selection rule.** The interim mechanism ("ship whichever round is last")
was replaced after two concrete cases: an MMLU subject where the shipped (last) round's
validation accuracy (0.800) was below its own baseline (0.840) yet still improved test accuracy
by one net item — a case the *old* accept-gate would have reverted entirely, losing a real
gain; and a PUPA run where round 2 beat round 3 on both mining (0.862 vs. 0.828) and validation
(0.633 vs. 0.533) by a wide margin, yet "last round" shipped round 3 regardless. Note: a
retroactive re-evaluation of that specific PUPA run's round 2 against its own sealed test set
found round 2 scored *slightly lower* than the shipped round 3 on test (accuracy 0.632 vs.
0.658; mean_score 0.782 vs. 0.799) — a gap well inside the n=38 noise floor (±16pp), so this
single case does not itself prove the new selection rule outperforms the old one on held-out
data; it demonstrates only that the new rule uses information (validation accuracy) that was
otherwise being computed and discarded for free, which is a defensible design improvement
independent of whether it wins on any one sample.

## 6. Threats to validity (for the paper's limitations section)

- **Model scale asymmetry.** Every comparison against GEPA/MIPROv2/TextGrad/GRPO/MPO/Trace2Policy
  in §3 pits our small, inexpensive solvers (GPT-4o-mini, Claude Haiku 4.5) against their
  mid-to-large models (Qwen3-8B, GPT-4.1 Mini, LLaMA-3-8B, GPT-3.5/4). This is a deliberate
  choice (testing whether reflective FDPO helps cheap models specifically) but means no
  cross-paper number in §3 should be read as "our method vs. their method" — only "our
  method's own delta, on a smaller model, vs. their method's own delta, on a larger model."
- **Baseline construction differs**, most sharply for AIME (§3.4): a bare markdown prompt vs. a
  structured DSPy `ChainOfThought` module. Baseline-to-baseline absolute comparison is not
  meaningful anywhere in §3; only within-method deltas are.
- **Single seed** for nearly every number reported. §4's reproducibility finding shows this
  matters more than it might first appear.
- **Split-size and split-composition differences** (PUPA §3.5; MMLU §3.2; the AIME test-set
  repeat-5× convention GEPA uses that we did not replicate) mean even same-metric comparisons
  are on different underlying item sets.
- **IFEval/IFBench metric-definition uncertainty** (§3.3): our per-item pass/fail rate and
  GEPA's own reported score are not verified to be the same construct.
- **PUPA role-model mismatch**: our external/judge model choices were not verified to match
  GEPA's.

## 7. Novel infrastructure contributions (for a paper's contribution list)

- The reflective effect-report mechanism itself (§1) — full, uncapped recovered/regressed
  detail on both mining and validation, shown to the optimizer every round from round 2 on.
- An anti-memorization instruction added to the optimizer's system prompt after directly
  diagnosing a near-verbatim training-item reproduction disguised as an "invented" example.
- A `FINAL RESPONSE:` marker convention enabling IFEval/IFBench-style whole-output verifiable
  constraints to coexist with free-form solver reasoning that precedes the graded text.
- Two evidence-motivated mechanism ablations (§5), each with a documented concrete case that
  triggered the change.
- A from-scratch IFBench verifier covering 82 constraint types (`ifeval_verifiers.py`), an
  AIME fetcher matching GEPA's exact train/test boundary (`hf_fetch.py`), and a PUPA pipeline
  (`pupa_pipeline.py`) implementing the two-hop redact→external→synthesize architecture with a
  continuous composite score, including a reusable `PromptRegistry.restore_round()` primitive
  for reconstructing and re-evaluating any historical round's exact prompt against a sealed
  test set after the fact.

## 8. Immediate next steps before this is submission-ready

- Multi-seed runs (≥3 seeds) for every benchmark in §3 — the single largest gap given §4's
  finding.
- Add Qwen3-8B and Llama as solver models across all five benchmarks — Qwen3-8B specifically
  would make that arm directly comparable to GEPA's own open-weight numbers throughout §3,
  closing part of the model-scale caveat in §6.
- Wire Anthropic's per-token pricing into the cost table — the Haiku PUPA run's reported $4.60
  total understates true spend (its solver cost recorded as $0; see §3.5).
- Resolve the IFEval/IFBench metric-definition question in §3.3 well enough to state
  confidently whether the two scores are comparable at all.
- Decide whether to attempt a fairer AIME baseline (matching GEPA's `ChainOfThought`-scaffolded
  construction) to isolate the mechanism-vs-scaffolding confound identified in §3.4.
