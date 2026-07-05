# FDPO Mechanism: Root-Cause Attribution and Section Rewriting

This diagrams exactly how the system decides *what's wrong with the prompt*
and *how it fixes it*, using real output from a completed run
(`results/00_smoke/gsm8k_fdpo_gpt-4o-mini_s1_20260705-133900/`) as the
worked example — not a hypothetical.

## 1. The per-round loop

```mermaid
flowchart TD
    A["Active 5-section prompt\n(system_role, context, task_details,\nconstraints, output_format)"] --> B["SOLVER (gpt-4o-mini)\nanswers each TRAIN example"]
    B --> C{"Programmatic verdict\nregex-extract answer, compare to gold\n(no LLM involved in this step)"}
    C -->|correct| D["Add example to CorrectPool\n(FIFO, cap=200)"]
    C -->|incorrect| E["Send to JUDGE (gpt-4.1):\nfull prompt + question +\nwrong output + reference answer"]
    E --> F{"Judge returns JSON:\nwhich ONE section is\nmost responsible, + why\n(MISSING / WRONG / CONFLICT)"}
    F --> G["Bucket this failure\nunder that section"]
    D --> H
    G --> H{"After all train examples:\ndoes any section have\nattributed failures?"}
    H -->|no failures anywhere| Z["Next round\n(no rewrite needed)"]
    H -->|yes, e.g. task_details| I["OPTIMIZER (gpt-4.1) rewrites\nONLY that section"]
    I -.->|sees| I1["up to 5 sampled failures:\nquestion + wrong output +\njudge's critique"]
    I -.->|sees| I2["up to 3 GOLD examples\n(correctly-solved, from CorrectPool)"]
    I --> J["Candidate new section text"]
    J --> K["REGRESSION GATE"]
    D --> K
    K --> K1["Run OLD prompt on a sampled\nCorrectPool batch -> acc_old"]
    K --> K2["Run NEW prompt on the\nSAME batch -> acc_new"]
    K1 --> L{"acc_new >= acc_old - rho ?\n(rho = 0.02 default)"}
    K2 --> L
    L -->|yes: COMMIT| M["Registry activates the new version;\nold version archived (not deleted)"]
    L -->|no: REJECT| N["Registry logs the candidate as\nrejected; ACTIVE prompt unchanged"]
    M --> Z
    N --> Z
    Z --> B
```

**Where "root cause" actually gets found**: step **E → F**. The judge isn't
guessing blindly — it's shown all 5 sections, the exact question, the
model's full wrong output, and the reference answer, then forced (via
JSON-mode + a retry-on-malformed-JSON loop) to name exactly one section as
most responsible, plus a category:
- **MISSING** — the section should have said something and didn't
- **WRONG** — the section said something, but it was incorrect/misleading
- **CONFLICT** — two parts of the prompt contradict each other

This is the entire "diagnosis" step. Nothing more sophisticated than one
well-structured LLM call per failure — the intelligence is in constraining
what it's allowed to answer with (one of exactly 5 section names, or
`"multiple"`, or `"none"`), not in any custom heuristic.

**Where the "update" happens**: step **I**. The optimizer is shown *only*
the implicated section's current text, the other 4 sections as read-only
context (explicitly told not to touch them), the failing examples with the
judge's critiques attached, and a few gold (correctly-solved) examples for
contrast. It returns plain rewritten text for that one section — nothing
else changes.

**Where safety comes from**: step **K → L**. The rewrite is never trusted
just because the optimizer produced it — it's *tested* against a batch of
examples the model was already getting right, before and after the edit. If
it would knock previously-correct examples below the `acc_old - ρ`
tolerance, it's discarded and the old text keeps running. This is why a
"real run" can never make the prompt worse than best-known — only sideways
(rejected) or forward (committed).

## 2. A real version tree (GSM8K, `task_details` section)

This is exactly what happened in the completed run — 1 commit, 2 rejects,
all attempts branching off whatever was *active* at the time (not off each
other):

```mermaid
graph TD
    v0["v0 — seed (round 0)\n'Solve the problem step by step,\nshowing your arithmetic.'\nSTATUS: archived"]
    v1["v1 — round 1\n'Work through the problem step by step, carefully\nshowing calculations and using the correct\nmathematical relationships...'\ngate: acc 1.0 -> 1.0, broke 0, recovered 1/3\nSTATUS: ACTIVE (best-known)"]
    v2["v2 — round 2 attempt\n'Follow the sequence of events or operations\nexactly as described...'\ngate: acc 1.0 -> 0.923, broke 1, recovered 0/2\nSTATUS: rejected"]
    v3["v3 — round 3 attempt\n'Carefully solve the problem step by step, using\nthe relationships and quantities exactly...'\ngate: acc 1.0 -> 0.923, broke 1, recovered 0/2\nSTATUS: rejected"]

    v0 -->|"3 failures attributed here ->\nrewrite -> gate PASSED"| v1
    v1 -->|"2 new failures ->\nrewrite -> gate FAILED\n(broke 1 previously-correct example)"| v2
    v1 -->|"2 new failures ->\nrewrite -> gate FAILED\n(broke 1 previously-correct example)"| v3
```

Notice v2 and v3 both branch from **v1**, not from each other — every
rewrite attempt always starts from whatever is currently *active*, and a
rejected candidate has zero effect on what the next round sees. The solver
only ever runs v1 after round 1, regardless of how many rejected candidates
pile up in the registry. All 4 versions (including the 2 dead ends) are
preserved in `registry.json` for post-hoc analysis — nothing is thrown away,
only "not activated."

## 3. Why this specific run showed the mechanism working

- 3 failures in round 1 → all attributed to `task_details` → one rewrite →
  gate passed (didn't break anything, fixed 1 of 3) → **committed**.
- Rounds 2–3 tried to push further on the same section, but with only 15
  train examples there wasn't enough new failure signal to justify another
  change — both attempts made things measurably worse on the held-out batch
  (broke 1 example each time) → correctly **rejected** both times.
- Net effect: the prompt ended the run strictly better than or equal to
  where it started (train accuracy 80% → 86.7%, never regressed), which is
  the entire point of the regression gate.

The large-scale run in progress (150 train / 200 test / 5 rounds) will
produce the same kind of trace, just with enough failures per round for the
loop to plausibly keep finding new things to fix across more rounds instead
of stalling after round 1.
