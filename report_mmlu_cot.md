# MMLU Per-Subject FDPO with a Neutral Baseline — Report

**Date:** 2026-07-26
**Method:** `simple_fdpo`, per-subject, validation-gated lenient accept, 3 rounds.
**Solver:** gpt-4o-mini · **Optimizer:** gpt-4.1 · temps solver 0.0 / optimizer 0.7.
**Seed (baseline):** a **neutral headerless one-liner** — *"Answer the following
multiple-choice exam question by selecting the single best option. Give your
answer in exactly this form: Answer: <LETTER> …"* — **no "step by step"**, so
FDPO has to introduce reasoning itself.
**Split:** `balanced`, one subject per run, **50 train (33 mining / 17 validation)
/ 66 test**, `tau 3`, `--max-workers 3`. Test items fixed across seeds.
**Pilot subjects:** `college_mathematics`, `high_school_biology`, 3 seeds each.

---

## 1. Headline

**From a neutral one-liner, FDPO spontaneously wrote a chain-of-thought,
subject-specialized prompt — and it delivered where there was headroom.**

| Subject | Baseline | Final | Δ (mean) | Per-seed |
|---|---:|---:|---:|---|
| college_mathematics | 76.8% | **82.3%** | **+5.6** | +10.6 / +1.5 / +4.5 |
| high_school_biology | 87.9% | 88.4% | +0.5 | 0.0 / 0.0 / +1.5 |

Math is the win: FDPO turned a neutral prompt into a rigorous reasoning prompt
and gained **+5.6 pp** (all three seeds positive). Biology is flat — it starts
near its ceiling (~88%) and there is no room to move.

---

## 2. The design journey (why the baseline matters)

Same 66 test items per subject in the two per-subject configs; the "letter-only"
row is from the earlier **mixed** 6-subject run (n=50, different setup) and is
context only.

### college_mathematics
| Config | Baseline | Final | Δ | What happened |
|---|---:|---:|---:|---|
| Letter-only (mixed, n=50) | 75.3 | 70.0 | −5.3 | optimizer wrote "output only a letter" → **suppressed CoT** |
| CoT-in-baseline (n=66) | 75.3 | 75.3 | +0.0 | CoT pre-baked into the seed → FDPO had nothing to add |
| **Neutral → FDPO (n=66)** | 76.8 | **82.3** | **+5.6** | FDPO **discovered** CoT itself → real gain |

### high_school_biology
| Config | Baseline | Final | Δ |
|---|---:|---:|---:|
| Letter-only (mixed, n=50) | 82.0 | 88.0 | +6.0 |
| CoT-in-baseline (n=66) | 90.4 | 88.4 | −2.0 |
| **Neutral → FDPO (n=66)** | 87.9 | 88.4 | +0.5 |

Biology's **final lands ~88% under every config** — it is prompt-insensitive at
the top (knowledge-bound ceiling for gpt-4o-mini).

**Two takeaways:** (a) putting CoT in the *baseline* hides FDPO's value (the gain
becomes a higher baseline, not a delta); (b) a *neutral* baseline both measures
the honest delta **and** gives the optimizer freedom to build a richer prompt —
the neutral math final (82.3) actually beats the CoT-in-baseline final (75.3) on
the identical test set.

---

## 3. FDPO discovered CoT on its own (both subjects)

Starting from a one-liner with **no reasoning instruction**, the optimizer wrote:

- **Math:** a 7-step procedure — *"Restate the problem … Recall relevant
  theorems … Step-by-Step Solution Process: show each line of manipulation …
  Check hidden/edge cases"* — with math-specialized hooks (rank–nullity,
  compactness, "must vs could"). Constraint: *"Always show detailed, step-by-step
  reasoning before stating your final answer."*
- **Biology:** *"You must reason step by step and clearly justify your answer
  before providing it,"* plus definition-focused elimination of "trap" options.

This is the intended behavior: FDPO **finds** that reasoning helps, rather than
being hand-fed it.

---

## 4. Why math gains and biology doesn't

- **Math** has latent ability that CoT unlocks: the model *can* do the linear
  algebra / probability once it's allowed to work step by step → **+5.6**.
- **Biology** is near-ceiling (~88%) and knowledge-bound — reasoning space
  doesn't add facts it doesn't have → **+0.5 (noise)**. The validation gate
  correctly **reverted seed 0 to baseline** (no structured round beat it).

This matches the broader pattern: FDPO pays off where there's **headroom + a
reasoning/framework gap** (math CoT here; hearsay/law definitional framework
elsewhere, +8.5 / +9.3), and adds ~0 at a knowledge ceiling.

---

## 5. Mechanism health

- **Validation-gated lenient accept:** shipped a structured prompt on 5/6 runs;
  reverted 1 (biology s0) when nothing beat baseline — gate working as designed.
- **Extraction:** ~0–1 failures / 66 — the neutral `Answer:` sentinel and FDPO's
  reasoning both parse cleanly (no truncation-before-answer).
- **Headerless baseline:** `render_system` now renders a single-section prompt as
  raw text (no `##` headers); full/enriched prompts keep headers. Applies to
  LegalBench one-liners too; default full-prompt seeds unchanged. 97 tests pass.
- **No pin** this round — the optimizer was free, guided only by the softer
  "never forbid reasoning" rule, and it chose CoT anyway.

---

## 6. Honest caveats

- **n = 66 per subject → ±~6 pp.** Math's seed spread is wide (+1.5 … +10.6);
  read "+5.6" as *solidly positive, magnitude noisy*. Biology's +0.5 is noise.
- The **letter-only** row is a different setup (mixed 6-subject, n=50) — use it
  as narrative context, not a matched control.
- **Azure ~5 pp non-determinism** still applies; single model (gpt-4o-mini).
- Two subjects only — see next step.

---

## 7. Next step

Run the remaining four subjects (`professional_law`, `philosophy`,
`econometrics`, `computer_security`) with this neutral-baseline setup:
- **econometrics** should *recover* like math (it was CoT-suppressible).
- **professional_law** is the real test of FDPO's *framework* value (mixed run
  showed +9.3 even letter-only) — expect CoT + framework to compound.
- philosophy / computer_security likely small / near-ceiling.

That completes the honest per-subject story: **FDPO turns a vague one-liner into
a strong prompt — discovering CoT where reasoning is the bottleneck and
definitional structure where the framework is — and correctly does little where
the model is already at its ceiling.**

**Artifacts:** `results/mmluneutral_college_mathematics/`,
`results/mmluneutral_high_school_biology/`. Numbers via
`_dl/analyze_mmlu_cot.py`; shipped prompts in each run's `prompt_current.md`.
