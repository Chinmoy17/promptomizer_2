# Complete MMLU Report — Per-Subject FDPO from a Neutral Baseline

**Date:** 2026-07-26
**Method:** `simple_fdpo`, per-subject, validation-gated **lenient** accept
(`--accept-margin 1.0`), 3 rounds.
**Solver:** gpt-4o-mini · **Optimizer:** gpt-4.1 · temps 0.0 / 0.7.
**Seed (baseline):** a **neutral headerless one-liner** (no "step by step") — FDPO
must introduce reasoning itself.
**Split:** `balanced`, one subject per run, **50 train (33 mining / 17 validation)
/ 66 test**, `tau 3`, `--max-workers 3`. 6 subjects × 3 seeds = 18 runs.

---

## 1. Headline — honest version

**FDPO, from a neutral one-liner, reliably discovers chain-of-thought — but the
*net* MMLU effect is roughly flat (+0.4 macro), because the win is concentrated
in reasoning-amenable subjects and one near-ceiling subject blew up.**

| Subject | Baseline | Final | Δ (mean) | Per-seed | Old mixed (n=50) |
|---|---:|---:|---:|---|---:|
| college_mathematics | 76.8 | 82.3 | **+5.6** | +10.6 / +1.5 / +4.5 | 75→70 |
| philosophy | 77.3 | 81.3 | **+4.0** | +1.5 / +6.1 / +4.5 | 74→75 |
| econometrics | 66.7 | 68.7 | +2.0 | +7.6 / −3.0 / +1.5 | 62→58 |
| high_school_biology | 87.9 | 88.4 | +0.5 | 0.0 / 0.0 / +1.5 | 82→88 |
| professional_law | 53.0 | 52.0 | −1.0 | −1.5 / +1.5 / −3.0 | 53→62 |
| computer_security | 92.4 | **83.8** | **−8.6** | −7.6 / −6.1 / −12.1 | 92→94 |
| **MACRO-AVERAGE** | **75.7** | **76.1** | **+0.4** | | |

---

## 2. The three regimes FDPO falls into

**(a) Helps — reasoning-amenable + headroom:** math **+5.6**, philosophy **+4.0**,
econometrics **+2.0**. Here FDPO wrote an explicit step-by-step reasoning prompt
(it *discovered* CoT from a neutral seed) and it unlocked latent ability. This is
the real value of the method on MMLU.

**(b) Neutral — no room or wrong lever:**
- **biology +0.5** — near its knowledge ceiling (~88%); reasoning adds no facts.
- **professional_law −1.0** — knowledge-bound. Note the mixed run showed law
  **+9.3**, but that **did not survive isolation**: a law-only reasoning prompt
  can't inject legal knowledge the model lacks. The mixed-run gain was a
  side-effect of the shared prompt, not a real law improvement.

**(c) HURTS — near-ceiling + lenient gate + noisy validation:**
**computer_security −8.6.** This is the important failure. Diagnosis from the
metrics:

| seed | baseline_val (17) | best_struct_val | shipped | test Δ |
|---|---:|---:|---|---:|
| 0 | 0.667 | 0.778 | yes | −7.6 |
| 1 | 0.944 | 0.944 (tie) | yes | −6.1 |
| 2 | 0.778 | 0.778 (tie) | yes | −12.1 |

Baseline test was 0.924 but baseline **validation** was as low as 0.667 — the
17-item validation draw was unrepresentative. The optimizer improved (or tied)
that noisy validation, the **lenient gate shipped the structured prompt on a
tie**, and it regressed the real test by 6–12 pp on all three seeds. On a
92%-baseline subject, elaborate added reasoning makes the model second-guess
answers it already had right.

**If the gate had correctly kept baseline on `computer_security`, the MMLU macro
would be ~+1.9 instead of +0.4.** The −8.6 blow-up is what erases the gains.

---

## 3. FDPO did discover CoT (as intended)

From a one-liner with **no** reasoning instruction, the optimizer wrote, e.g.:
- **Math:** a 7-step procedure ("show each line of manipulation"; rank–nullity,
  compactness, "must vs could"). Constraint: *"Always show detailed, step-by-step
  reasoning before stating your final answer."*
- **Biology / philosophy:** *"reason step by step and clearly justify your
  answer before providing it."*

So the mechanism works — it's the **acceptance decision**, not CoT discovery,
that's the current weak point.

---

## 4. Actionable fixes (before/at TAMUK)

1. **Tighten the gate for high-baseline subjects.** The lenient default
   (`--accept-margin 1.0`, ships on ties) is wrong when the baseline is already
   strong. Options: require the structured prompt to **beat** baseline validation
   by a real margin; or skip optimization when baseline accuracy is high (raise
   `tau` adaptively / add a "don't optimize above X%" guard). This alone would
   have prevented the `computer_security` and part of the `law` losses.
2. **Bigger / less noisy validation.** 17 items is too noisy to gate on
   (`baseline_val` 0.667 vs `baseline_test` 0.924). More train, higher
   `--simple-val-frac`, or multi-sample validation.
3. **Deterministic open-model inference (TAMUK / Llama).** Removes the Azure
   ~5 pp noise that makes 17-item validation unreliable, and — per the headroom
   argument — **weaker open models have more room, so deltas should be larger**
   (MPO reported Llama-3-8B MMLU +4.3). Expect the reasoning-amenable subjects to
   gain more there, and the near-ceiling regression risk to shrink.

---

## 5. Honest caveats

- **n = 66 test / 17 validation per subject** → wide CIs (±~6 pp test; validation
  much worse). Math's per-seed spread is +1.5…+10.6.
- The **old mixed (n=50, letter-only)** column is a different setup — context, not
  a matched control. Its `law +9.3` explicitly did **not** replicate per-subject.
- **Azure non-determinism ~5 pp**; single solver (gpt-4o-mini).
- Macro-average is over the 6 committed subjects, on a re-split of MMLU's
  val+test pool (disclosed; zero train/test overlap).

---

## 6. Bottom line for the paper / TAMUK handoff

- **The vague-one-liner → structured-prompt claim holds where it should:** FDPO
  discovers CoT and lifts reasoning-amenable subjects (math +5.6, philosophy
  +4.0, econometrics +2.0).
- **It is honestly flat overall on MMLU (+0.4 macro)** because near-ceiling and
  knowledge-bound subjects have nothing to gain, and the **lenient gate can ship
  a regressor** (computer_security −8.6) — a fixable gate issue, not a mechanism
  failure.
- **The code is ready to transfer to TAMUK**: per-subject runs via
  `--subjects`, neutral headerless baseline, `--split-mode balanced`, and the
  validation-gated loop. The two things to change there are a **stricter gate for
  high-baseline subjects** and **deterministic inference**, which should turn the
  flat macro positive and make the per-subject CIs trustworthy.

**Artifacts:** `results/mmluneutral_<subject>/` (6 subjects × 3 seeds). Numbers via
`_dl/analyze_mmlu_all6.py`; per-subject churn via `_dl/mmlu_churn.py`; shipped
prompts in each run's `prompt_current.md`.
