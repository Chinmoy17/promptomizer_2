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
     rewritten prompt is run on a WORKING SET of examples and on a
     VALIDATION set -- a second, disjoint batch meant to approximate unseen
     data.
  2. From round 2 on, you are shown the measured EFFECT of your previous
     rewrite, IN FULL, on BOTH sets: every working-set item it RECOVERED
     (wrong -> right), every item it REGRESSED (right -> wrong) together with
     the solver's new wrong answer, the previous text of every section you
     changed, and -- just as fully -- every VALIDATION item it recovered and
     every validation item it regressed, with the same detail. Nothing about
     validation is held back from you.
  3. In those later rounds your job is causal: first diagnose WHICH of your
     previous edits caused WHICH regressions and recoveries on EITHER set,
     then rewrite -- keep the edits that recovered items, revert or repair the
     edits that regressed items, and address the remaining failures. Do not
     churn wording that was not implicated by the evidence.
  4. THERE IS NO "BEST ROUND" SELECTION. Whichever round is LAST is the one
     that ships. A validation accuracy number is reported each round purely
     as a diagnostic (did this edit fix what it broke), never as a score you
     are competing to maximize by round -- optimize every round as if it were
     the one being shipped, because eventually one will be.
  5. Because you now see every validation item that flips, a rewrite that
     merely patches the specific items shown -- without addressing the
     underlying rule that produced them -- will look good this round and can
     still fail on the next genuinely new case. Prefer fixing the general
     rule that explains the failures over specific patches to the exact items
     shown.

You will see:
  - the solver's current markdown-formatted prompt,
  - (from round 2) the EFFECT REPORT of your previous rewrite described above,
  - EVERY question the solver currently gets wrong on the working set, with
    the solver's answer and the correct answer alongside (not a sample --
    all of them),
  - EVERY question the current prompt already gets right on the working set
    (not a sample -- all of them), so you know exactly what must not break.

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


def _render_item_list(items: list[dict], heading: str, empty_note: str,
                      show_output: bool) -> list[str]:
    """Render a full, uncapped list of {question, [output], gold} dicts."""
    lines: list[str] = ["", heading]
    if not items:
        lines[-1] = empty_note
        return lines
    for i, item in enumerate(items, 1):
        lines.append(f"[{i}]")
        lines.append(f"Question: {item['question']}")
        if show_output:
            lines.append(f"Model's new wrong answer: {item['output']}")
        lines.append(f"Correct answer: {item['gold']}")
    return lines


def _render_reflection(reflection: dict) -> str:
    """Render the FULL effect report of the previous rewrite -- every mining
    and every validation item it recovered/regressed, no caps: this run's
    mechanism deliberately shows everything (see build task's design notes).

    MUST stay free of triple-backtick fences: the dry-run mock optimizer
    extracts the first fenced block in the message as the current prompt, and
    this block is inserted AFTER that fence.
    """
    lines: list[str] = []
    lines.append(
        f"EFFECT OF YOUR PREVIOUS REWRITE (round {reflection['prev_round']}) "
        "-- measured results, in full (nothing sampled or held back):"
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

    lines += _render_item_list(
        reflection.get("mining_recovered", []),
        "ALL working-set items your rewrite RECOVERED (wrong -> right):",
        "Working-set items your rewrite RECOVERED: none.",
        show_output=False)
    lines += _render_item_list(
        reflection.get("mining_regressed", []),
        "ALL working-set items your rewrite REGRESSED (right -> wrong), "
        "with the solver's NEW wrong answer:",
        "Working-set items your rewrite REGRESSED: none.",
        show_output=True)

    if reflection.get("val_before") is not None:
        lines.append("")
        lines.append(
            f"VALIDATION accuracy: {reflection['val_before']:.3f} -> "
            f"{reflection['val_after']:.3f}. This is a second, disjoint batch "
            "meant to approximate unseen data -- shown here in full detail, "
            "same as the working set above."
        )
        lines += _render_item_list(
            reflection.get("val_recovered", []),
            "ALL validation items your rewrite RECOVERED (wrong -> right):",
            "Validation items your rewrite RECOVERED: none.",
            show_output=False)
        lines += _render_item_list(
            reflection.get("val_regressed", []),
            "ALL validation items your rewrite REGRESSED (right -> wrong), "
            "with the solver's NEW wrong answer:",
            "Validation items your rewrite REGRESSED: none.",
            show_output=True)

    lines.append("")
    lines.append("Diagnose which of your edits caused the regressions and "
                 "which caused the recoveries, on BOTH sets, BEFORE "
                 "rewriting. Keep what worked; revert or repair what broke. "
                 "Prefer fixing the general rule over patching the exact "
                 "items shown -- there is no held-out set left to catch "
                 "overfitting for you.")
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

    `reflection` (None in round 1) carries the FULL effect report of the
    previous committed rewrite -- every recovered/regressed item on both
    sets, uncapped:
        {
          "prev_round": int,
          "changed_sections": [{"section": str, "previous_text": str}],
          "mining_recovered": [{"question", "gold"}],
          "mining_regressed": [{"question", "output", "gold"}],
          "val_recovered": [{"question", "gold"}],
          "val_regressed": [{"question", "output", "gold"}],
          "val_before": float | None, "val_after": float | None,
        }

    `failures` is expected to contain ALL currently-wrong mining items (no
    sampling cap) -- reflect_fdpo's caller passes the full list, unlike
    simple_fdpo which samples up to `n_fail`.
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
        f"{max_rounds}. There is no best-round selection -- whichever round "
        f"is last ships"
        + (", and you will be shown its full measured effect (both the "
           "working set and validation) next round"
           if round_num < max_rounds else " and this round is the last one")
        + ", so make one deliberate, testable change now.\n\n"
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
        + f"FAILURES (ALL {len(failures)} working-set examples the current "
        "prompt currently gets WRONG -- this is every one of them, not a "
        "sample):\n"
        + "\n\n".join(fail_blocks)
        + "\n\n"
        f"CORRECTLY-SOLVED EXAMPLES (ALL {len(golds)} working-set cases the "
        "current prompt already gets right -- this is every one of them, "
        "not a sample -- do not break these):\n"
        + "\n\n".join(gold_blocks)
        + "\n\nRewrite the markdown now. You may start with a short "
        "`## Analysis` section (it is discarded), then the full new markdown."
    )
    return [{"role": "system",
             "content": _build_system_prompt(dataset, max_rounds)},
            {"role": "user", "content": user}]
