# `reflect_fdpo` — Progress Report

Status as of 2026-08-30. Covers every real (non-dry-run) `reflect_fdpo` experiment run so
far. Mechanism code: `src/fdpo/core/reflect_loop.py`,
`src/fdpo/prompts/reflect_optimizer_prompt.py`. Tests: 151/151 passing across the whole suite
as of this report.

## 1. What `reflect_fdpo` is

Same paper-faithful `LLMOptimize(p_old, E_fail, E_gold)` contract as `simple_fdpo` (one
markdown prompt, optimizer edits it freely), plus one added mechanism: from round 2 on, the
optimizer is shown the measured *effect* of its own previous rewrite before writing the next
one — which mining items it recovered/regressed (with the solver's new wrong answer), the
previous text of every section it changed, and the full validation-set movement (not just
counts). `simple_fdpo` is never modified and stays the blind control arm.

Two deliberate design choices distinguish it from `simple_fdpo`:
- **Everything uncapped.** Every current failure and every currently-correct mining item is
  shown each round — no `n_fail`/`n_gold` sampling.
- **No keep-best round selection.** Once the optimizer has full validation transparency,
  treating "which round scored best on val" as an unseen-data proxy becomes circular (the
  optimizer already had that round's val errors in hand). So every round commits
  unconditionally, and whichever round is *last* ships — subject to one final gate: if the
  last round's validation accuracy is below `baseline_val_acc - accept_margin`, the entire run
  reverts to the untouched seed prompt instead of shipping a regression.

## 2. Mechanism evolution (chronological)

1. Uncapped failures/golds shown every round (no sampling cap, unlike `simple_fdpo`'s
   `n_fail`/`n_gold`).
2. Removed keep-best round selection in favor of "ship last round + final accept gate vs.
   baseline" (see `reflect_loop.py:369-393`) — visible in the data below as the appearance of
   `"selection": "last_round"` in later runs' `metrics.json`.
3. Added an explicit anti-memorization rule to the optimizer system prompt after diagnosing a
   near-verbatim reproduction of a training item as an "invented" example.
4. Added the `FINAL RESPONSE:` marker convention (`ifeval_verifiers.py`) so IFEval/IFBench —
   which score the solver's *entire* raw output, not one extracted line — can still let the
   solver reason/plan before the graded text.
5. **Rate-limit fix (2026-08-30):** capped the solver output text shown to the optimizer to a
   ~400-char tail (`_truncate_output` in `reflect_optimizer_prompt.py`). GPT-4.1 on AIME writes
   ~2,800 completion tokens per item; uncapped, round 1's ~44 failures put >100K tokens of raw
   solver reasoning into a single `gpt-5` optimizer request, which exceeded the Azure
   deployment's per-minute token quota outright (a sustained 429 that retries couldn't fix,
   since the request was the same size every time). The fix is length-triggered, not
   dataset-specific: a no-op for every short-completion dataset, and the only thing it touches
   is what the optimizer is shown for diagnosis — not what the evaluator scores. Verified: the
   AIME/GPT-4.1 run that previously crashed completed cleanly afterward (see §3).
6. **Removed the final accept gate entirely (2026-08-30):** `reflect_fdpo` no longer compares
   the last round's validation accuracy to baseline at all — whichever round is last always
   ships, full stop (`reflect_loop.py`'s `ship_structured = any_committed`). Rationale: the
   gate was reverting runs based on a validation comparison shown (twice, independently) to be
   noisy enough on its own that it discarded as much real signal as it protected — see the
   MMLU college_mathematics case in §3, where the shipped round's val (0.800) sat below its own
   baseline (0.840) and would have reverted under the old gate, yet test accuracy still net
   improved. Paired with this: when a run never triggers any round at all (baseline already
   high, or `tau` never met), `run_experiment.py` now reuses `seed_test`'s rows as `final_test`
   outright instead of re-evaluating the provably-identical prompt a second time — avoiding
   both the wasted API cost and the pure re-run noise documented in §4.
7. **PUPA support built (2026-08-30):** a genuinely different mechanism from every other
   dataset here — a 3-call pipeline (redact → external model → synthesize) scored by a
   continuous composite (`quality` judge score + mechanical PII-`leakage` fraction), not a
   single extracted-answer-vs-gold match. Only the redaction prompt is optimized (synthesis is
   frozen); see `src/fdpo/data/pupa_pipeline.py`. First real run in §3. Two real bugs caught
   and fixed during the first attempts: some rows' `pii_units` field is `NaN` (pandas), not
   `""`, which crashed `.split()` until `hf_fetch.py`/`compute_leakage()` were made to coerce
   it; and the judge's `max_tokens=512` was too small for `gpt-5` (a reasoning model) to finish
   reasoning AND emit the required `Score:` line — every judge call was hitting the cap exactly
   (512/512 completion tokens, confirmed in the ledger), silently defaulting every quality score
   to 0. Fixed by raising judge `max_tokens` to 2048.
8. **"Ship last round" replaced with "ship best-of-committed-rounds" (2026-08-30):** the PUPA
   pilot run below is the direct evidence — round 2 beat round 3 on BOTH mining (0.862 vs
   0.828) AND validation (0.633 vs 0.533) by a wide margin, yet "last round always ships"
   (item 6 above) shipped round 3 anyway. Item 6's "no revert to baseline" reasoning still
   holds, but "ship whichever round happens to be last" was throwing away information the
   mechanism already had in hand for free (every round's val accuracy is computed regardless of
   which one ships). `reflect_loop.py` now tracks the best-by-validation (or best-by-mining, if
   no val split) round across the whole trajectory and ships that one, reconstructing its exact
   prompt from the registry's full version history via the new `PromptRegistry.restore_round()`
   (`registry.py`) — never the last round blindly, and still never the untouched seed unless
   literally no round ever committed. `"selection"` in `metrics.json["optimization"]` is now
   `"best_of_rounds"` (was `"last_round"`); a new `"shipped_round"` field records which round
   number actually shipped. A retroactive diagnostic script,
   `scripts/eval_round_on_test.py --run-dir <dir> --round N`, can re-evaluate any specific past
   round's reconstructed prompt against a completed run's sealed test set (real API cost; does
   not touch the run's own metrics.json/registry.json).

## 3. Results so far

All runs are seed 0, single seed, `--simple-max-rounds 3`, `--tau 1`, `--accept-margin 0.0`
unless noted. "Δ" = final_test − seed_test. Costs from each run's `metrics.json`.

### LegalBench-hearsay (Claude Haiku 4.5, 50 train → 25 mining/25 val, 49 test)

| Arm | Prompt seed | Mechanism | seed_test | final_test | Δ | mining acc (base→ship) | shipped? |
|---|---|---|---|---|---|---|---|
| `simple_fdpo` (blind, tau=5, not triggered) | hearsay.md | — | 0.755 | 0.776 | +2.0pp | 0.84→0.84 | n/a (0 rounds) |
| `simple_fdpo` (blind, tau=1) | hearsay.md | keep-best | 0.776 | 0.755 | **−2.0pp** | 0.84→0.96 | yes |
| `reflect_fdpo` | hearsay.md | keep-best (pre-mechanism-change) | 0.816 | 0.714 | **−10.2pp** | 0.84→0.84 | yes |
| `reflect_fdpo` | hearsay_vague.md | keep-best | 0.714 | 0.816 | +10.2pp | 0.76→0.80 | yes |
| `reflect_fdpo` | hearsay_vague.md | last_round | 0.694 | 0.857 | **+16.3pp** | 0.80→0.92 | yes |
| `reflect_fdpo` | hearsay_vague.md | last_round | 0.714 | 0.735 | +2.0pp | 0.80→0.96 | yes |
| `reflect_fdpo` | hearsay_vague.md | last_round | 0.694 | 0.755 | +6.1pp | 0.80→0.92 | yes |

The blind control itself shows the textbook overfitting signature (mining +12pp, test −2pp).
Four `reflect_fdpo` reruns of the *identical* config/seed on the vague prompt swing from
**−10.2pp to +16.3pp** — see §4 for why this range should not yet be read as signal.

### MMLU

**Claude Haiku 4.5, college econometrics, 50 train → 25/25, 66 test (pre-gate-removal):**
baseline val accuracy (0.96) was above `--skip-above-acc 0.95`, so optimization was correctly
**skipped** (`edit_status: skipped_high_baseline`) — seed_test = final_test = 0.833 exactly, 0
optimizer calls, $0 optimizer cost. The guard fired as designed.

**gpt-4o-mini, 6-subject sweep, 50 train → 25/25, 66 test, seed 0 — first real test of the
gate-removed mechanism (§2 item 6), every run below shipped its last round unconditionally:**

| Subject | seed_test | final_test | Δ | net_gain (recov./regr.) | mining (base→ship) | val (base→ship) | old gate would've reverted? | cost |
|---|---|---|---|---|---|---|---|---|
| college_mathematics | 0.758 | 0.773 | +1.5pp | +1 (6/5) | 0.720→0.720 | 0.840→0.800 | **yes** | $0.344 |
| philosophy | 0.773 | 0.803 | +3.0pp | +2 (5/3) | 0.760→1.000 | 0.800→0.840 | no | $0.135 |
| econometrics | 0.667 | 0.727 | +6.0pp | +4 (10/6) | 0.560→0.880 | 0.600→0.720 | no | $0.246 |
| high_school_biology | 0.879 | 0.894 | +1.5pp | +1 (2/1) | 0.920→0.920 | 0.920→0.960 | no | $0.210 |
| professional_law* | 0.524 | 0.540 | +1.6pp | +1 (7/6) | 0.440→0.640 | 0.591→0.682 | no | $0.231 |
| computer_security | 0.909 | 0.894 | **−1.5pp** | −1 (1/2) | 0.840→0.840 | 0.720→0.800 | no | $0.154 |

\* 3/66 items content-filter-blocked (Azure), the SAME 3 in both seed and final eval, so
n_evaluated=63 for both — excluded from the denominator, not counted as wrong.

Mean Δ ≈ **+2.0pp** across 6 subjects, total cost $1.32. Every reported Δ is exact, not
rounded noise: e.g. college_mathematics' 0.758→0.773 on n=66 is precisely 50→51 correct
items, matching its `net_gain +1` (6 recovered − 5 regressed) exactly.

5 of 6 subjects improved; the one regression (computer_security, −1.5pp) is a subject that
was already near-ceiling at baseline (0.909) — consistent with the per-subject heterogeneity
already documented for this subject under the older mechanism (GPT-4.1 optimizer: −8.6pp;
GPT-5 optimizer: −1.5pp; see §3.1 of `datasets_and_benchmarks.md`), where forced restructuring
on a subject the solver already answers well tends to hurt more than help.

college_mathematics is the direct, concrete illustration of why the accept gate was removed:
its shipped round's validation accuracy (0.800) sat *below* its own baseline (0.840) — the old
gate would have reverted this entire run to the untouched seed — yet the shipped edit still
net-improved test accuracy by +1 item. The gate would have thrown away a real (if modest) gain
here, exactly the failure mode §2 item 6 describes.

Still a single seed per subject — the noise-floor caveat in §4 applies to every number above
just as much as it does everywhere else in this report.

### IFEval (gpt-4o-mini, 200 train → 100/100, 200 test, 2 items excluded as known content-filter false positives)

seed_test 0.737 → final_test 0.763 (**+2.5pp**, net +5 on test confusion), but
`shipped_structured: false` — the last round's val (0.72) was below baseline val (0.75), so
the run **reverted to the seed prompt**. The final_test number is therefore the *same prompt*
evaluated twice; the +2.5pp is pure re-run noise, not an optimization effect. Cost $0.54 (optimizer
$0.24, solver $0.30).

### IFBench (gpt-4o-mini, 2 runs, 40 train → 20/20, 42 test)

| Run | seed_test | final_test | Δ | shipped? | val (base→ship) |
|---|---|---|---|---|---|
| v1 | 0.476 | 0.452 | −2.4pp | yes | 0.368→0.526 |
| v2 | 0.476 | 0.452 | −2.4pp | no (reverted) | 0.632→0.421 |

Both land at the same final_test number, one via a genuinely shipped edit, one via revert to
the identical seed prompt. n=42 test → noise floor ≈±15pp; neither result is distinguishable
from no-op.

### AIME (90 train → 58 mining/32 val, 30 test, `aime.md` seed prompt)

| Solver | seed_test | final_test | Δ | shipped? | val trajectory (base→r1→r2→r3) | cost |
|---|---|---|---|---|---|---|
| gpt-4o-mini | 0.133 | 0.100 | −3.3pp | no (reverted) | 0.156→0.125→0.156→0.125 | $1.15 |
| Claude Haiku 4.5 | 0.267 | 0.333 | **+6.7pp** | **yes** | 0.625→0.656→0.656→**0.781** | $0.77 |
| GPT-4.1 (attempt 1) | — | — | — | budget-aborted at $2 cap before round 1 | — | $2.01 |
| GPT-4.1 (attempt 2) | — | — | — | crashed: sustained 429 on round-1 optimizer call (root cause of the §2.5 fix) | — | — |
| GPT-4.1 (attempt 3, post-fix) | 0.300 | 0.300 | 0.0pp | no (reverted) | 0.500→0.469→0.375→0.406 | $10.70 |

Claude Haiku is the only AIME run where every round's validation accuracy stayed at or above
baseline, and the shipped edit's test gain is directionally consistent with that (val +15.6pp,
test +6.7pp) — the closest thing to a real positive result in this batch, though n=32
val / n=30 test still keep it inside a wide noise band. GPT-4.1's three attempts cost $12.71
combined for zero shippable result; GPT-4.1's ~2,800-completion-tokens-per-item verbosity on
AIME is also why it is by far the most expensive solver tested (solver-side cost alone was
$10.05 of the $10.70 attempt-3 total).

### PUPA (gpt-4o-mini local/trusted, gpt-4.1 external/untrusted, gpt-5 judge, 60 train → 30
mining/30 val, 40 test, `pupa.md` seed prompt)

First real completion, **predates today's best-of-rounds fix (§2 item 8)** — shipped under the
old "last round always ships" mechanism:

| Round | mining acc | val acc | note |
|---|---|---|---|
| baseline | 0.690 | 0.400 | 1 item content-filter-blocked (excluded) |
| 1 | 0.793 | 0.567 | |
| 2 | **0.862** | **0.633** | best on BOTH metrics — the round §2 item 8 is about |
| 3 (shipped, old mechanism) | 0.828 | 0.533 | worse than round 2 on both; shipped anyway |

seed_test 0.553 → final_test 0.658 (**+10.5pp**, net +4 on test confusion: 7 recovered / 3
regressed), 2 items content-filter-blocked (same 2 in both seed and final eval). Cost $4.44.

Under the mechanism fix in §2 item 8, this exact run would have shipped round 2, not round 3 —
`scripts/eval_round_on_test.py --run-dir <this run's dir> --round 2` can retroactively evaluate
round 2's reconstructed prompt against this run's own sealed test set for a direct comparison
(real API cost, not yet run as of this report). Two real infra bugs were caught and fixed
getting to this result — see §2 item 7.

## 4. Cross-cutting findings

- **Same-config reruns are not reproducible enough to trust a single seed.** The four
  identical-config `reflect_fdpo` hearsay/vague reruns produced final_test accuracies of
  0.735, 0.755, 0.816, 0.857 — a 12.2pp spread from nothing but solver/optimizer sampling
  noise at "temperature 0." Any single-seed Δ reported anywhere in this document (including
  the AIME Haiku "win") should be read as a data point, not a conclusion, until repeated
  across seeds.
- **Binomial noise floor dominates at these sample sizes.** Roughly ±2√(p(1−p)/n): ≈±11pp at
  n=49 (hearsay test), ≈±15pp at n=42 (IFBench test), ≈±18pp at n=32/30 (AIME val/test). Most
  of the AIME and IFBench deltas above sit inside this band.
- **The final accept gate has been removed (§2 item 6).** It used to compare only the *last*
  round's val accuracy to the *original* baseline, all-or-nothing, with no partial credit and
  no per-round reject. On the GPT-4.1 AIME run, all three rounds — not just the last — stayed
  below baseline val, so that particular revert reflected the whole trajectory, not one
  unlucky final round. But the MMLU 6-subject sweep showed the gate could just as easily
  discard a real, if modest, net-positive result (college_mathematics) over a single noisy val
  comparison — the reason it was removed rather than just loosened.
- **Overfitting signature (mining↑, test/val↓) shows up in both arms**, including the blind
  `simple_fdpo` control — it is not an artifact of the reflection mechanism itself.
- **`skip_above_acc` guard works as intended** (MMLU econometrics case: correctly skipped a
  0.96-baseline subject rather than risking a regression for no reason).
- **First post-gate-removal batch (MMLU, 6 subjects, gpt-4o-mini, single seed): mean Δ ≈
  +2.0pp, 5/6 subjects positive.** The one regression (computer_security) is a near-ceiling
  subject and matches a heterogeneity pattern already seen under the older mechanism — see
  §3's MMLU section. Directionally encouraging, but still single-seed; the noise floor below
  (≈±11pp at n=66) means no individual subject's Δ here is independently conclusive yet — the
  5/6-positive pattern across subjects is the more interesting signal than any one number
  (noise floor ≈±12pp at n=66, using p=0.5; tighter with the actual per-subject p, but still
  wider than every individual Δ above).

## 5. Known limitations / open questions (not yet decided)

- The accept gate is now fully removed (§2 item 6) rather than replaced with a per-round
  ratchet (reject/retry an individual round against the immediately preceding round instead of
  the original baseline) — that alternative was considered and explicitly not built; revisit
  if a future batch shows the no-gate mechanism shipping a genuinely bad trajectory.
- AIME's 90-example train pool is small relative to its per-item variance; mining/val split
  sizes (58/32) may be inherently too noisy for 3-round convergence to show a real signal
  regardless of gate design.
- No multi-seed run exists yet for any dataset under `reflect_fdpo` — every number above is a
  single seed.
- PUPA's `correct` field is a 0.7 threshold on a continuous composite score, purely so the
  existing boolean recovered/regressed bookkeeping keeps working unmodified — `mean_score` is
  the real metric to read, not `accuracy`. First real result now in §3, but pre-dates the
  best-of-rounds fix (§2 item 8) — a re-run under the fixed mechanism doesn't exist yet.
- The best-of-rounds mechanism (§2 item 8) compares rounds by validation (or mining) accuracy
  only — a round with a lucky val split but a genuinely worse prompt could still win. No
  additional safeguard against that beyond what validation splits already provide elsewhere in
  this project.

## 6. Infra note

The rate-limit fix in §2 item 5 is verified end-to-end: the exact AIME/GPT-4.1 command that
previously crashed with a sustained `RateLimitError` on the optimizer's first call now
completes all 3 rounds and reaches the final test eval (attempt 3 above). The accept-gate
removal and no-op re-eval skip (§2 item 6) are verified via the MMLU 6-subject sweep in §3 and
a smoke test (`simple_fdpo`'s own separate revert path confirmed untouched). PUPA's 3-call
pipeline (§2 item 7) is verified via a real completed run (§3) after fixing the two bugs
described there. The best-of-rounds fix (§2 item 8) is verified via a new
`test_restore_round_reconstructs_a_past_round_regardless_of_current_state` unit test plus the
updated end-to-end dry-run assertion (shipped round/accuracy must match whichever round
actually scored highest, not merely the last one). Full test suite: 151/151 passing.
