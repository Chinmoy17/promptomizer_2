"""Reflect-mode optimizer prompt (`--method reflect_fdpo`).

Same contract as `simple_optimizer_prompt` (the LLM sees ONE markdown document
and returns the FULL new markdown), with one mechanism change: from round 2 on
the optimizer is shown the MEASURED EFFECT of its own previous rewrite --

  - the previous text of every section it changed,
  - the specific working-set items its edit recovered (wrong -> right),
  - the specific working-set items its edit regressed (right -> wrong),
    including the solver's NEW wrong answer,
  - the aggregate held-out validation movement (counts only; the validation
    items themselves are never shown, so validation stays a fair referee),

and is instructed to diagnose cause -> effect before editing again. The reply
may open with an `## Analysis` section; `parse_markdown()` skips unknown
headers, so the analysis is discarded automatically and only the five schema
sections survive.

This file deliberately does NOT modify `simple_optimizer_prompt.py` -- the
blind mechanism stays byte-identical as the control arm. Diff the two files to
see exactly what reflect mode changes.
"""

from __future__ import annotations

from fdpo.data.loaders import Example
# Shared task descriptions (data, not mechanism): reuse the simple-mode table
# so both arms describe the task identically.
from fdpo.prompts.simple_optimizer_prompt import (_DEFAULT_TASK_DESCRIPTION,
                                                  _TASK_DESCRIPTIONS)

_REFLECT_OPTIMIZER_SYSTEM_TEMPLATE = """You are working with an expert prompt
engineer to help a smaller LLM (the "solver") solve {task_description} more
reliably.

HOW THIS PROCESS WORKS (read carefully -- this is a measured, multi-round
experiment, not a one-shot rewrite):
  1. You get up to {max_rounds} rewrite rounds. After each round, your
     rewritten prompt is run on a WORKING SET of examples and on a HELD-OUT
     VALIDATION set that you never see.
  2. From round 2 on, you are shown the measured EFFECT of your previous
     rewrite: the exact working-set items it RECOVERED (wrong -> right), the
     exact items it REGRESSED (right -> wrong) together with the solver's new
     wrong answer, the previous text of every section you changed, and how the
     held-out validation accuracy moved.
  3. In those later rounds your job is causal: first diagnose WHICH of your
     previous edits caused WHICH regressions and recoveries, then rewrite --
     keep the edits that recovered items, revert or repair the edits that
     regressed items, and address the remaining failures. Do not churn wording
     that was not implicated by the evidence.
  4. The prompt that ships is the round with the best held-out validation
     accuracy, so a rewrite that fixes 2 working-set items but breaks 3
     held-out items is a net loss. Optimize for generalization, not for the
     specific examples shown.

You will see:
  - the solver's current markdown-formatted prompt,
  - (from round 2) the EFFECT REPORT of your previous rewrite described above,
  - a batch of FAILURES -- questions the solver currently gets wrong, with the
    solver's answer and the correct answer alongside,
  - a small batch of CORRECTLY-SOLVED examples the current prompt
    already handles.

CRITICAL FACT ABOUT THE SOLVER: it has NO hidden scratchpad. Its ONLY
reasoning space is the text it actually writes out. So "think step by step"
works only if the solver WRITES the steps in its output, before the final
answer line. Instructions like "reason internally", "use a scratchpad but do
not show it", or "output only the answer" DESTROY the reasoning entirely --
for this model they are identical to "do not reason". Never put them on a
task that benefits from reasoning.

FIRST, identify the task type from the failures you are shown:
  - Reasoning tasks -- anything needing calculation, derivation, formal
    logic, OR applying a rule/definition to a specific scenario (e.g.
    mathematics, econometrics, and hearsay / most legal analysis): the
    solver RELIABLY does better when it WRITES OUT its working step by step
    before the final answer line. A bare answer starves it.
  - Pure factual-recall / lookup tasks -- where the answer is simply known
    or not, with no intermediate steps (e.g. a memorised definition or
    fact): forced step-by-step reasoning can make the solver over-think and
    second-guess a fact it already recalled, LOWERING accuracy. Sharpen the
    definitions and framing instead, and keep the answer direct.
When unsure which it is, ALLOW visible reasoning -- it helps more often than
it hurts, and the final answer line is extracted either way. Match your
rewrite to the task type before doing anything else.

A good rewrite:

  - Surfaces the general reasoning principle that separates correct
    from incorrect answers on this task, and states it in terms the
    solver can apply to any new case it has not seen before.

  - Gives the solver the mental scaffolding it needs -- a clearer way
    to think about the problem, a checklist, a decision procedure, a
    definition it can lean on. Whatever helps a competent-but-fallible
    model be more consistent.

  - Illustrates principles with invented examples when helpful, not
    with training cases pasted verbatim. Copying training questions
    causes the solver to pattern-match on wording and overfit.

  - Keeps the fixed markdown schema (## System Role, Context, Task
    Details, Constraints, Output Format). You may edit any section but
    must not add or remove these headers.

  - Keeps the FINAL answer line's format exactly (e.g. a line
    "Answer: <LETTER>" or "Answer: Yes/No"). That final line is ALL the
    scorer reads, and it is searched for anywhere in the output -- so you
    MAY, and for reasoning tasks SHOULD, let the solver write visible
    step-by-step working BEFORE it. NEVER add "output only the answer",
    "do not show your working", or "reason internally": those suppress the
    reasoning and score reasoning tasks worse.

  - MATCHES the reasoning style to the task type (see the CRITICAL FACT at
    the top): for reasoning / rule-application tasks, INSTRUCT the solver to
    write its working step by step BEFORE the final answer line; for pure
    fact-recall tasks, keep it direct and sharpen definitions instead. The
    final answer line stays in the fixed format either way. The objective is
    accuracy, never verbosity for its own sake.

RESPONSE FORMAT: you MAY begin your reply with a short `## Analysis` section
(2-6 sentences diagnosing which previous edit caused which regression or
recovery -- state the cause before the fix; in round 1 you may use it to state
your hypothesis instead). The `## Analysis` section is discarded automatically
by the parser. After it, output the full rewritten markdown with the five
standard section headers. No other prose, no code fences, nothing after the
last section."""


def _build_system_prompt(dataset: str, max_rounds: int) -> str:
    task_desc = _TASK_DESCRIPTIONS.get(dataset, _DEFAULT_TASK_DESCRIPTION)
    return _REFLECT_OPTIMIZER_SYSTEM_TEMPLATE.format(
        task_description=task_desc, max_rounds=max_rounds)


# Display caps: keep the effect report informative but bounded. Regressions
# get more room than recoveries because they are what the optimizer must
# repair; recoveries only need to be recognizable so they are not reverted.
_MAX_RECOVERED_SHOWN = 5
_MAX_REGRESSED_SHOWN = 10


def _render_reflection(reflection: dict) -> str:
    """Render the effect report of the previous rewrite.

    MUST stay free of triple-backtick fences: the dry-run mock optimizer
    extracts the first fenced block in the message as the current prompt, and
    this block is inserted AFTER that fence.
    """
    lines: list[str] = []
    lines.append(
        f"EFFECT OF YOUR PREVIOUS REWRITE (round {reflection['prev_round']}) "
        "-- measured results:"
    )

    changed = reflection.get("changed_sections", [])
    if changed:
        lines.append("")
        lines.append("Sections you changed, with their PREVIOUS text (the "
                     "current text is in the full prompt above):")
        for c in changed:
            prev = c["previous_text"].strip() or "(was empty)"
            lines.append(f"[Section '{c['section']}' previously read:]")
            lines.append(prev)

    recovered = reflection.get("mining_recovered", [])
    n_rec = reflection.get("n_mining_recovered", len(recovered))
    lines.append("")
    if n_rec:
        shown = recovered[:_MAX_RECOVERED_SHOWN]
        lines.append(f"Working-set items your rewrite RECOVERED "
                     f"(wrong -> right), {n_rec} total"
                     + (f", {len(shown)} shown:" if n_rec > len(shown) else ":"))
        for i, r in enumerate(shown, 1):
            lines.append(f"[Recovered {i}]")
            lines.append(f"Question: {r['question']}")
            lines.append(f"Correct answer: {r['gold']}")
    else:
        lines.append("Working-set items your rewrite RECOVERED: none.")

    regressed = reflection.get("mining_regressed", [])
    n_reg = reflection.get("n_mining_regressed", len(regressed))
    lines.append("")
    if n_reg:
        shown = regressed[:_MAX_REGRESSED_SHOWN]
        lines.append(f"Working-set items your rewrite REGRESSED "
                     f"(right -> wrong), {n_reg} total"
                     + (f", {len(shown)} shown" if n_reg > len(shown) else "")
                     + ", with the solver's NEW wrong answer:")
        for i, r in enumerate(shown, 1):
            lines.append(f"[Regressed {i}]")
            lines.append(f"Question: {r['question']}")
            lines.append(f"Model's new wrong answer: {r['output']}")
            lines.append(f"Correct answer: {r['gold']}")
    else:
        lines.append("Working-set items your rewrite REGRESSED: none.")

    if reflection.get("val_before") is not None:
        lines.append("")
        lines.append(
            f"Held-out validation (items you never see): accuracy "
            f"{reflection['val_before']:.3f} -> {reflection['val_after']:.3f}; "
            f"your edit recovered {reflection['val_recovered']} and regressed "
            f"{reflection['val_regressed']} held-out item(s)."
        )

    lines.append("")
    lines.append("Diagnose which of your edits caused the regressions and "
                 "which caused the recoveries BEFORE rewriting. Keep what "
                 "worked; revert or repair what broke.")
    return "\n".join(lines)


def build_reflect_optimizer_messages(
    current_markdown: str,
    failures: list[dict],   # each: {question, output, gold}
    golds: list[Example],
    dataset: str = "unknown",
    round_num: int = 1,
    max_rounds: int = 1,
    reflection: dict | None = None,
) -> list[dict]:
    """Build the two-message optimizer call for reflect mode.

    `reflection` (None in round 1) carries the effect report of the previous
    committed rewrite:
        {
          "prev_round": int,
          "changed_sections": [{"section": str, "previous_text": str}],
          "mining_recovered": [{"question", "gold"}],
          "mining_regressed": [{"question", "output", "gold"}],
          "n_mining_recovered": int, "n_mining_regressed": int,
          "val_before": float | None, "val_after": float | None,
          "val_recovered": int, "val_regressed": int,
        }
    """
    fail_blocks = []
    for i, f in enumerate(failures, 1):
        fail_blocks.append(
            f"[Failure {i}]\n"
            f"Question: {f['question']}\n"
            f"Model's wrong answer: {f['output']}\n"
            f"Correct answer: {f['gold']}"
        )

    gold_blocks = []
    for i, g in enumerate(golds, 1):
        gold_blocks.append(
            f"[Correct {i}]\n"
            f"Question: {g.question}\n"
            f"Correct answer: {g.reference}"
        )

    iteration_context = (
        f"ITERATION CONTEXT: This is refinement round {round_num} of "
        f"{max_rounds}. Your rewrite is scored on held-out examples"
        + (" and you will be shown its measured per-item effect next round"
           if round_num < max_rounds else "")
        + ", so make one deliberate, testable change this round.\n\n"
    )

    # NOTE: the "FULL CURRENT PROMPT (markdown)" marker and its fenced block
    # must come before any other content the mock/dry-run client could match;
    # the reflection block is inserted AFTER it and is fence-free.
    reflection_block = ""
    if reflection is not None:
        reflection_block = _render_reflection(reflection) + "\n\n"

    user = (
        iteration_context
        + "FULL CURRENT PROMPT (markdown):\n"
        "```\n"
        f"{current_markdown.rstrip()}\n"
        "```\n\n"
        + reflection_block
        + f"FAILURES ({len(failures)} training examples the current prompt "
        "gets WRONG):\n"
        + "\n\n".join(fail_blocks)
        + "\n\n"
        f"CORRECTLY-SOLVED EXAMPLES ({len(golds)} cases the current prompt "
        "already gets right — do not break these):\n"
        + "\n\n".join(gold_blocks)
        + "\n\nRewrite the markdown now. You may start with a short "
        "`## Analysis` section (it is discarded), then the full new markdown."
    )
    return [{"role": "system",
             "content": _build_system_prompt(dataset, max_rounds)},
            {"role": "user", "content": user}]
