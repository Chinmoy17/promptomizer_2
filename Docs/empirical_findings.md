# Empirical Findings — FDPO on MMLU & LegalBench (gpt-4o-mini)

**Scope:** Synthesis of the validation-gated `simple_fdpo` experiments —
LegalBench-hearsay and MMLU (6 subjects, per-subject). Solver gpt-4o-mini,
optimizer gpt-4.1, Azure `eastus2`. These are the *transferable insights*, not a
single run's numbers.

> **One-line summary:** *Prompt optimization on multiple-choice knowledge tasks is
> governed less by "a better prompt" than by two levers — (1) whether the output
> format allows chain-of-thought, and (2) whether the baseline already banks that
> gain. The value is real but **subject-typed**, and an over-lenient acceptance
> gate can convert a near-ceiling subject's win into a loss.*

---

## Finding 1 — Chain-of-thought is a double-edged sword (output-format dissociation)

The single biggest driver of accuracy on MMLU was **not** the richness of the
5-section prompt — it was whether the **output format permitted reasoning**. The
optimizer's choice of "show your work" vs "output only the letter" flips the sign
of the result depending on the subject:

| Subject (type) | Direct-answer prompt | Chain-of-thought prompt |
|---|---:|---:|
| college_mathematics (compute) | **−5.3** | **+5.6** |
| econometrics (compute) | **−4.0** | **+2.0** |
| professional_law (recall) | **+9.3** | **−1.0** |
| computer_security (recall, ~92% ceiling) | **+2.0** | **−8.6** |

- **Reasoning/computation subjects need a scratchpad.** Forcing a bare letter
  starves them (math −5.3, econ −4.0); allowing CoT unlocks latent ability
  (+5.6, +2.0).
- **Recall subjects are hurt by CoT.** Elaborate "weigh every option / watch for
  traps / consider exceptions" reasoning makes a small model **second-guess**
  answers it already recalled correctly (law, security regress).

*(Caveat: the two columns come from different runs — a shared direct-output prompt
vs per-subject CoT prompts — so there are confounds (shared vs per-subject, n=50
vs n=66 test). But baselines match and the sign-flip is consistent across seeds,
and the prompt text confirms the output-format difference is the salient driver.)*

**Implication:** there is **no single output format that wins all subjects.** A
one-size prompt is doomed to trade one subject type for the other.

---

## Finding 2 — The baseline seed decides what the delta *measures*

Where you put CoT changes the story entirely, because `simple_fdpo`'s baseline
**is** the seed prompt:

| Config (high_school_biology) | Baseline | Final | Δ |
|---|---:|---:|---:|
| CoT in the **seed** | 90.4 | 88.4 | −2.0 |
| **Neutral** seed (FDPO adds CoT) | 87.9 | 88.4 | +0.5 |

| Config (college_mathematics) | Baseline | Final | Δ |
|---|---:|---:|---:|
| CoT in the **seed** | 75.3 | 75.3 | +0.0 |
| **Neutral** seed (FDPO adds CoT) | 76.8 | **82.3** | **+5.6** |

- Putting CoT in the *seed* makes the baseline strong and **hides FDPO's value**
  as a higher baseline (the gain is real but shows up in the wrong column).
- A **neutral** seed both measures the honest delta **and** lets the optimizer
  build a richer prompt: on the *same* 66 math test items, the neutral final
  (82.3) beat the CoT-seed final (75.3).

**Implication:** report the delta from a genuinely vague/neutral baseline;
otherwise you are measuring "FDPO on top of a head start."

---

## Finding 3 — FDPO discovers CoT on its own

From a neutral one-liner with **no** reasoning instruction, the optimizer
independently wrote step-by-step reasoning prompts for **all six** subjects
(e.g. math: a 7-step procedure with rank–nullity / compactness hooks; biology:
"reason step by step and clearly justify your answer"). The **mechanism works** —
FDPO *finds* that reasoning helps. The weak point is not discovery; it is
**acceptance** (Finding 5).

---

## Finding 4 — Near-ceiling subjects are downside-only ("break more than you fix")

`computer_security` at a 92% baseline, per-item churn (all 3 seeds):

| Seed | Baseline right | Recovered (wrong→right) | Regressed (right→wrong) | Still wrong |
|---|---:|---:|---:|---:|
| s0 | 61/66 | **0** | 5 | 5 |
| s1 | 61/66 | **0** | 4 | 5 |
| s2 | 61/66 | **0** | 8 | 5 |

- The CoT prompt **fixed zero** of the 5 hard questions — the *same 5* stayed
  wrong every seed (they need security *knowledge*, not reasoning).
- It **broke 4–8** previously-correct answers by inducing second-guessing.
- Arithmetic is forced: **0 gained − (4…8) lost = net loss** at a high baseline.

**Implication:** don't optimize (or don't *ship*) on subjects already near
ceiling — there is little to win and much to break.

---

## Finding 5 — The acceptance gate, not CoT discovery, is the failure point

The lenient gate (`--accept-margin 1.0`, ships even on a validation *tie*)
combined with a **tiny, noisy 17-item validation** shipped a regressor:

| security seed | baseline_val (17) | best_struct_val | shipped? | test Δ |
|---|---:|---:|---|---:|
| 0 | 0.667 | 0.778 | yes | −7.6 |
| 1 | 0.944 | 0.944 (tie) | yes | −6.1 |
| 2 | 0.778 | 0.778 (tie) | yes | −12.1 |

Baseline test was 0.924 but baseline *validation* was as low as 0.667 — the
17-item draw was unrepresentative, the CoT prompt "beat" that noise, and the
lenient gate shipped it. **A stricter gate (require the structured prompt to
*beat* baseline validation) would have kept the terse baseline for
security/law while still shipping the CoT prompt for math** — capturing the wins
without the losses. *If the gate had held security at baseline, the MMLU macro
would be ~+1.9 instead of +0.4.*

---

## Finding 6 — FDPO's value is subject-typed (three regimes)

| Regime | Subjects | Δ | Why |
|---|---|---:|---|
| **Helps** | math, philosophy, econometrics; hearsay | +5.6 / +4.0 / +2.0 / +8.5 | headroom **and** a reasoning/framework gap FDPO can fill |
| **Neutral** | biology (ceiling), law (knowledge-bound) | +0.5 / −1.0 | nothing to add — facts, not reasoning, are the bottleneck |
| **Hurts** | computer_security | −8.6 | near-ceiling recall + over-reasoning + lenient gate |

**Balanced 6-subject MMLU macro-average: +0.4 (flat)** — the reasoning gains are
cancelled by the security regression. The value is **per-subject**, not
aggregate, with gpt-4o-mini.

---

## Finding 7 — Mixed prompt vs per-subject: gains don't always survive isolation

`professional_law` gained **+9.3 consistently** in the mixed 6-subject run (one
shared, direct-output prompt) but went **−1.0** when run per-subject with a
CoT prompt. A **shared** prompt can be net-positive on recall subjects while
killing reasoning subjects (and vice-versa) — the mixed aggregate hides a pile
of offsetting per-subject effects. **Per-subject isolation is the only honest way
to see what FDPO actually does to each subject.**

---

## Finding 8 — The validation-gated lenient accept fixed a real bug (LegalBench-hearsay)

Replacing the noisy "train-failure-count" acceptance with a **held-out
validation gate** on hearsay:

| | Old (train-failure gate) | New (validation gate) |
|---|---|---|
| Seeds shipping a structured prompt | 1 / 3 | **3 / 3** |
| Test delta (per seed) | +17.0 / −5.1 / 0.0 | +8.5 / +8.5 / +8.5 |
| Spread across seeds | 22.1 pp | **0.0 pp** |

The old gate reverted 2/3 seeds to an empty-section one-liner (regression bug);
the new gate ships structured prompts and **collapses run-to-run variance**. This
is the mechanism that carried over to MMLU — where it then exposed Finding 5.

---

## Finding 9 — Platform artifacts (all disappear on open models)

- **Content filter is localized.** 48 blocks total, **all** in professional_law
  (4.8% of its calls), **0** for every other subject. On law's test set the
  blocks are balanced baseline-vs-final (2 vs 2 per seed), so the **delta is
  unbiased**; law's *absolute* accuracy is understated ~3 pp. Security's −8.6 is
  **not** filter-related (0 blocks).
- **Rate limiting.** `--max-workers 8` overran Azure `eastus2` and crashed a run
  (429s exhausting retries); `--max-workers 3` is the reliable setting.
- **Non-determinism ~5 pp** at temperature 0 on n≈60 test sizes — this is what
  makes a 17-item validation untrustworthy (Finding 5).

**Model-headroom corollary:** a *stronger* solver has *less* MMLU headroom and
would show *smaller* deltas; *weaker* open models (Llama-3-8B; MPO reported
+4.3 on MMLU) have more room and should show *larger, cleaner* deltas. The
reasoning-amenable subjects are where that upside lives.

---

## Practical guidance (for the method and the TAMUK/Llama handoff)

1. **Baseline = neutral one-liner** (no CoT, no header scaffolding). Let FDPO
   discover reasoning; measure the honest delta.
2. **Gate must be able to say "no."** Require the structured prompt to *beat*
   baseline on validation (not tie), and/or **skip optimization when the baseline
   is already high** — this is what prevents the security-style blow-up.
3. **Bigger / less-noisy validation** (more train, higher `--simple-val-frac`, or
   multi-sample) — 17 items is too few to gate on under Azure noise.
4. **Expect subject-typed results.** Report per-subject, not just macro; the win
   is concentrated in reasoning-amenable subjects with headroom.
5. **Deterministic open-model inference** removes the content filter, the rate
   limits, and the ~5 pp noise — making the per-subject deltas trustworthy and
   likely larger.

**Artifacts:** `results/mmluneutral_<subject>/`,
`results/mmlucot_<subject>/`, `results/smoke/…` (mixed + hearsay). Analysis:
`_dl/analyze_mmlu_all6.py`, `_dl/analyze_mmlu_cot.py`, `_dl/security_churn.py`,
`_dl/count_content_filter.py`. Run reports: `report_mmlu_cot.md`,
`report_validation_gate.md`.
