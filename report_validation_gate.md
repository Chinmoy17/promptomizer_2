# Validation-Gated FDPO: Run Report

**Date:** 2026-07-26
**Method:** `simple_fdpo`, 3-round keep-best, **held-out validation gate**
(new), gpt-4o-mini solver + gpt-4.1 optimizer, temps solver 0.0 / optimizer 0.7.
**Seed prompt:** the same vague one-liner as yesterday
(`prompts/hearsay_oneliner.md`) → *"This is a legal hearsay task. For each
statement, decide whether it is hearsay and answer Yes or No."*
**Test set:** 59 examples, fixed across seeds (stratified split-mode).

> **What changed since yesterday.** The accept gate no longer scores candidate
> prompts on the *same* examples the optimizer mined failures from. The 40-item
> train pool is now split into a **mining set M (26)** and a **held-out
> validation set V (14)**, stratified. The optimizer sees failures from M; each
> candidate prompt is scored on V; the kept prompt is the one with the best V
> accuracy. The final accept is **lenient** (`--accept-margin 1.0` default): the
> best-validation structured prompt is *shipped* to test rather than reverting
> to the bare one-liner. Mining + validation = the old train size, so this costs
> **no extra API calls**.

---

## 1. Headline

Every seed now ships a real structured prompt, and the three runs land in the
same place instead of scattering.

| Metric | Yesterday (train-failure gate) | Today (validation gate) |
|---|---|---|
| Seeds that shipped a structured prompt | **1 / 3** | **3 / 3** |
| Seeds that reverted to the empty one-liner | 2 / 3 | **0 / 3** |
| Test delta — seed 0 | +17.0 | +8.5 |
| Test delta — seed 1 | −5.1 (revert noise) | +8.5 |
| Test delta — seed 2 | 0.0 (revert) | +8.5 |
| **Mean test delta** | +4.0 | **+8.5** |
| **Spread across seeds** | 22.1 pp | **0.0 pp** |

The two headline effects are **the revert bug is gone** (3/3 ship structured,
no empty sections) and **variance collapsed** (22.1 pp → 0.0 pp). The mean
improved too (+4.0 → +8.5 pp), but see the honest caveats in §4 — the mean is
the least trustworthy line in this table.

---

## 2. Per-seed result (today)

All three seeds start from the identical one-liner on the identical 59-item
test set, so the baseline is the same 62.7%.

| Seed | Baseline TEST | Final TEST | Δ | Shipped | Winning round (by V) |
|---|---:|---:|---:|---|---|
| 0 | 62.7% | 71.2% | **+8.5** | structured | R1 (V 78.6%) |
| 1 | 62.7% | 71.2% | **+8.5** | structured | R1 (V 78.6%) |
| 2 | 62.7% | 71.2% | **+8.5** | structured | R2 (V 71.4%) |

Final test accuracy is 42/59 for all three; `macro_f1` differs (0.699 / 0.665 /
0.709), so the *predictions* are not identical — the seeds converge on the same
*count* correct, not the same answers.

---

## 3. Why the validation split matters (the mechanism, caught in the act)

Baseline accuracy on the mining set is 76.9% (6/26 wrong); on validation it is
71.4% (4/14 wrong). The interesting rounds are the ones where **mining accuracy
and validation accuracy move in opposite directions** — exactly the situation
the old gate got wrong.

**Seed 0, round 1 — the old gate would have thrown this away.**

| | mining acc | validation acc |
|---|---:|---:|
| baseline | 76.9% | 71.4% |
| round 1 | 61.5% ⬇ | **78.6%** ⬆ |

Round 1 *regressed* on the mining set (failures 6 → 10). The old
"must reduce train failures" gate would have **rejected** it and reverted to the
bare one-liner. The validation gate sees V rise to 78.6% and **ships it** — and
test rises 62.7% → 71.2%. The held-out signal was right; the mining signal was
misleading.

**Seed 2, round 1 — the old gate would have locked onto an overfit prompt.**

| | mining acc | validation acc |
|---|---:|---:|
| baseline | 76.9% | 71.4% |
| round 1 | **80.8%** ⬆ | 64.3% ⬇ |
| round 2 | 69.2% ⬇ | 71.4% ⬆ |

Here round 1 *improves* mining (failures 6 → 5) but *drops* validation to
64.3%. The old gate would have crowned round 1. The validation gate declines to
lock onto it and instead keeps round 2 (V back to 71.4%), which is what ships.

These two cases are the empirical argument for the split: on this task, mining
accuracy is a biased estimate of generalization (the optimizer is optimizing
against it), and gating on a held-out slice corrects for that bias.

### Full validation trajectories

| Seed | R1 (mining / V) | R2 (mining / V) | R3 (mining / V) | Shipped |
|---|---|---|---|---|
| 0 | 61.5 / **78.6** | 61.5 / 57.1 | 61.5 / 71.4 | R1 |
| 1 | 65.4 / **78.6** | 61.5 / 71.4 | 65.4 / 78.6 | R1 |
| 2 | 80.8 / 64.3 | 69.2 / **71.4** | 76.9 / 71.4 | R2 |

(Ties do not displace an earlier best, so seed 1 keeps R1 over the equal-V R3,
and seed 2 keeps R2 over the equal-V R3.)

---

## 4. Honest caveats — do not over-read this

1. **Azure is not deterministic at temp 0.** Yesterday the *same* one-liner on
   the *same* 59 test items scored 62.7 / 66.1 / 64.4 across the three seed runs
   — a 3.4 pp spread from noise alone. Today it scored 62.7 all three. That is
   the noise floor, and it means **cross-day deltas are confounded**. The clean
   comparison is within-today: +8.5 pp over the same-day baseline.

2. **The mean did not strictly dominate.** Seed 0 today (+8.5) is *lower* than
   yesterday's lucky +17.0. The validation gate traded that seed's
   noise-inflated peak for consistency across seeds. It fixes the revert bug and
   collapses variance; it does **not** guarantee beating a lucky run.

3. **All three landing on exactly 71.2% is partly coincidence.** With n=59 the
   accuracy grid is coarse (1 item ≈ 1.7 pp), the three shipped prompts differ,
   and their macro-F1 differs. Read this as "a strong attractor around ~71%,"
   not "the mechanism is perfectly reproducible."

4. **Validation is a 14-item proxy.** V accuracy moves in ~7 pp steps
   (1/14); best_val = 78.6% is 11/14. It is a better estimator than the mining
   set, but it is still small and noisy.

5. **One dataset, one model.** This is LegalBench-hearsay on gpt-4o-mini. No
   general claim is implied.

---

## 5. Bottom line

The validation-gated lenient accept does what it was asked to do: **no seed
reverts to an empty-section one-liner anymore (3/3 ship structured), and the
run-to-run scatter collapses from 22 pp to ~0.** On this task it also lifts the
mean (+4.0 → +8.5 pp within-day), and §3 shows the split correcting the
mining-set bias in two concrete rounds. The honest ceiling on the claim is set
by Azure's ~3–5 pp noise and the small test/validation sizes — the effect is
real and consistent here, but the exact magnitude should not be quoted to the
decimal.

**Artifacts.** Runs:
`results/smoke/legalbench_hearsay_simple_fdpo_gpt-4o-mini_s{0,1,2}_20260726-1211…`.
Numbers regenerated by `_dl/analyze_val_split_runs.py`. Shipped prompts:
`prompt_current.md` in each run dir.
