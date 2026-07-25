# One-liner → FDPO Enrichment: Run Report

**Date:** 2026-07-25
**Method:** `simple_fdpo`, 3-round keep-best, gpt-4o-mini solver + gpt-4.1 optimizer
**Seed prompts:** deliberately vague **one-liners** (no structure), which FDPO
must enrich into a full 5-section prompt.

- Hearsay seed: `prompts/hearsay_oneliner.md` → *"This is a legal hearsay task. For each statement, decide whether it is hearsay and answer Yes or No."*
- GSM8K seed: `prompts/gsm8k_oneliner.md` → *"This is the GSM8K dataset of 8th-grade school math word problems. Solve each problem and give the final integer answer."*

Total spend: ~$0.55 across 6 runs. Temperatures: solver 0.0, optimizer 0.7.

---

## 1. Headline result

**The mechanism works: FDPO demonstrably turns a one-line instruction into a
full, structured, legally-accurate 5-section prompt** (see §4). On the run
where it stuck, this lifted hearsay accuracy by **+17 percentage points**.

**But the results are high-variance, and regression is a real and recurring
problem** — which is the focus of this report (§5).

| Dataset | Seed 0 | Seed 1 | Seed 2 | Mean | Range |
|---|---:|---:|---:|---:|---:|
| **Hearsay** (one-liner baseline) | 62.7 → 79.7 (**+17.0**) | 66.1 → 61.0 (**−5.1**) | 64.4 → 64.4 (0.0) | **+4.0** | −5.1 … +17.0 |
| **GSM8K** (one-liner baseline) | 96.0 → 95.0 (**−1.0**) | 95.0 → 96.0 (+1.0) | 94.0 → 95.0 (+1.0) | **+0.3** | −1.0 … +1.0 |

GSM8K is at ceiling (baseline already 94-96% even from a one-liner — the model
does step-by-step math regardless of prompt), so there is nothing to gain and
the small movements are noise. **Hearsay is the informative dataset.**

---

## 2. Failures at baseline (the one-liner)

Both datasets, all seeds, started from the same one-liner. Train batch:
hearsay 40 examples, GSM8K 60 examples.

| Dataset | Seed | Baseline TRAIN wrong | Baseline TEST acc |
|---|---|---:|---:|
| Hearsay | 0 | 10 / 40 | 62.7% |
| Hearsay | 1 | 10 / 40 | 66.1% |
| Hearsay | 2 | 10 / 40 | 64.4% |
| GSM8K | 0 | 5 / 60 | 96.0% |
| GSM8K | 1 | 6 / 60 | 95.0% |
| GSM8K | 2 | 5 / 60 | 94.0% |

The hearsay one-liner produces a genuinely weak baseline (~64% test, 25% train
error) — real headroom. The GSM8K one-liner does not (near-ceiling) — no
headroom.

---

## 3. Failures at each training stage (per round)

Each round: `|F|` = training failures before → after; `+x/−y` = examples
recovered / regressed **on the training batch** that round. **Bold** = the
round that became the trajectory-best.

### Hearsay

| Seed | R1 | R2 | R3 | Winner | Final vs baseline |
|---|---|---|---|---|---|
| 0 | \|F\| 10→12  (+2/−4) | \|F\| 12→11  (+2/−1) | **\|F\| 11→9  (+3/−1)** | R3 (beat baseline) | committed |
| 1 | \|F\| 10→12  (+2/−4) | \|F\| 12→12  (+0/−0) | \|F\| 12→13  (+0/−1) | none | reverted to baseline |
| 2 | \|F\| 10→12  (+3/−5) | \|F\| 12→10  (+4/−2) | \|F\| 10→12  (+1/−3) | none (R2 tied, not <) | reverted to baseline |

### GSM8K

| Seed | R1 | R2 | R3 | Winner | Final vs baseline |
|---|---|---|---|---|---|
| 0 | **\|F\| 5→4  (+2/−1)** | converged (\|F\|<τ) | — | R1 | committed |
| 1 | **\|F\| 6→4  (+3/−1)** | converged | — | R1 | committed |
| 2 | \|F\| 5→7  (+1/−3) | \|F\| 7→7  (+1/−1) | \|F\| 7→6  (+2/−1) | none | reverted to baseline |

**Observation:** in every single round, the optimizer both **recovers** some
examples and **regresses** others. There is no round that only helps. The
question is always whether recoveries outnumber regressions — and often on
this small, noisy batch, they do not.

---

## 4. Proof the enrichment works — the prompt FDPO built (hearsay seed 0)

Starting from the 18-word one-liner, FDPO produced this (excerpted):

> **## System Role**
> You are a legal reasoning assistant. Your job is to determine whether a given statement is hearsay under U.S. Federal Rule of Evidence 801...
>
> **## Context**
> Under U.S. Federal Rule of Evidence 801, "hearsay" is an out-of-court statement offered to prove the truth of the matter asserted... A statement or conduct is not hearsay if it is introduced for a reason other than proving the truth—such as showing knowledge, state of mind, notice, or effect on a listener. Nonverbal conduct is only hearsay if intended to communicate an assertion...
>
> **## Task Details**
> Step 1: Is There an Out-of-Court Assertion? ... Step 2: What Is the Purpose for Offering the Evidence? ... Step 3: Analyze Assertions and Conduct Carefully ... Step 4: Special Considerations ... [+ a decision checklist and 6 invented illustrative examples]
>
> **## Constraints**
> Do not consider hearsay exceptions... Focus exclusively on the purpose for which the evidence is offered...

This is a genuine, well-structured, legally-accurate prompt built from one
line. **The core capability the user asked to see is confirmed.**

---

## 5. Regression analysis — the main event

The user's hard requirement is **no regression**. Across the 6 runs, regression
appeared in three *distinct* forms, with three *different* causes and three
*different* fixes. Separating them is essential.

### Source A — Measurement noise (false regression)

**Where:** Hearsay **seed 1**. Final test 61.0% vs baseline 66.1% (−5.1),
with **0 recovered / 3 regressed**. But the mechanism **reverted to the
baseline one-liner** — the final prompt is *byte-for-byte identical* to the
baseline prompt. The same prompt was evaluated twice and 3 test examples
flipped right→wrong (ids `hearsay_test_15, _58, _89`).

**Cause:** Azure OpenAI is **not deterministic at temperature 0**. Re-running
the identical prompt gives ~3-5 pp different accuracy on n=59. This is **not
FDPO's fault** — it is inference noise. FDPO changed nothing here.

**Fix:** deterministic inference (open models via vLLM at TAMU eliminate this
entirely), or majority-vote over multiple eval passes per question.

### Source B — Genuine trade-off regression (committed prompt)

**Where:** Hearsay **seed 0** (the +17 pp win). The enriched prompt recovered
12 test examples but regressed 2: `hearsay_test_43` and `hearsay_test_80`.

- `hearsay_test_43` (gold **Yes**, "Standard hearsay"): a wedding-congratulations
  card offered to prove a couple was married. The enriched prompt's new rule —
  *"nonverbal conduct is only hearsay if intended to communicate an assertion"*
  — caused the model to over-apply the non-assertive-conduct exception and
  answer No. The added nuance backfired on this case.
- `hearsay_test_80` (gold **No**, "Not introduced to prove truth"): *"Andrew is
  a liar and a hypocrite,"* offered to show the speaker's ill feeling
  (state of mind), not to prove Andrew is a liar. The enriched prompt's heavy
  emphasis on "offered to prove the truth" pushed the model to answer Yes.

Also GSM8K **seed 0**: committed prompt helped 1 test example, hurt 2
(`gsm8k_test_1084, _184`).

**Cause:** every prompt rewrite changes the model's behavior on examples it
was **not** targeting. Adding a rule to fix failures X can break passing
cases Y that the rule now mis-covers. This is the fundamental trade-off of
prompt optimization, and it is **inherent**, not a bug.

**Fix:** show the optimizer the passing examples it must protect (we already
raised `n_gold` to 10; going higher or specifically feeding the
previously-recovered cases would help), and — most importantly — gate
acceptance on a held-out **validation** slice (see §6).

### Source C — Train-test generalization gap

**Where:** GSM8K **seed 0**. The optimizer **improved training** (5→4
failures, +2/−1) and this round was committed as "best" — but on **test** it
**regressed** (−1, 2 regressions). The training gain did not generalize.

**Cause:** keep-best gates on the **training** failure count. A rewrite that
reduces training failures can still hurt held-out test (mild overfitting to
the 60 training examples). The gate cannot see this because it never looks at
anything but train.

**Fix:** gate on a separate **validation** slice, not the training batch (§6).

---

## 6. Where FDPO is lacking, and how to prevent regression

The user's goal — *no regression at all* — is achievable, but the current
mechanism cannot deliver it because of three gaps:

| Gap | Consequence | Fix |
|---|---|---|
| **Acceptance gates on TRAIN failure count only** | A round that overfits train (helps train, hurts test) can be committed (Source C). | **Validation-gated acceptance**: carve a 3rd slice (validation) disjoint from both the optimizer's train-failures and the final test. Commit a round only if it does not regress validation. Catches B and C without leaking test. |
| **Optimizer only sees failures + a few golds** | It rewrites freely and breaks passing cases it never saw (Source B). | Feed it **more** passing examples, and explicitly the ones prior rounds recovered, with an instruction: "these currently pass — do not break them." |
| **Single noisy eval per prompt** | Same prompt scores ±3-5 pp run to run; produces phantom regressions (Source A). | **Majority-vote / multi-sample** evaluation, or move to deterministic open-model inference (TAMU). |

### The single highest-value change: validation-gated acceptance

Right now the keep-best rule is *"keep the round with the fewest **training**
failures."* Change it to *"keep the round with the fewest **validation**
failures, and never commit a round that increases validation failures over
baseline."* This directly enforces "no regression" on a held-out set that the
optimizer cannot see, targeting both Source B and Source C. It costs one extra
eval per round (a small validation slice) and does not touch the test set, so
there is no leakage.

Combined with multi-sample evaluation (for Source A), this would get us to
the user's goal: **a mechanism that, by construction, does not ship a prompt
worse than the one it started with.**

---

## 7. Summary

1. **The one-liner → structured enrichment works** — proven qualitatively
   (§4) and, when it sticks, worth +17 pp (hearsay seed 0).
2. **It is high-variance** — mean hearsay gain +4.0 pp but range [−5.1, +17.0]
   across seeds. On 40 training examples with Azure noise, the optimizer often
   cannot find a rewrite that beats baseline, and reverts.
3. **Regression has three separable causes** — measurement noise (A), genuine
   trade-offs in a committed prompt (B), and train-test overfitting (C). Only
   B and C are FDPO's responsibility.
4. **"No regression" is achievable** via **validation-gated acceptance**
   (fixes B and C) plus **multi-sample evaluation or open-model determinism**
   (fixes A). This is the recommended next mechanism change.

### Artifacts
- Runs: `results/smoke/{legalbench_hearsay,gsm8k}_simple_fdpo_gpt-4o-mini_s{0,1,2}_20260725-*`
- Inspect any run: `uv run python -m scripts.show_rounds <run_dir>`
- Enriched prompt: `results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s0_20260725-231519/prompt_current.md`
