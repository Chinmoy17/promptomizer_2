"""Simple-mode optimizer prompt: the LLM sees ONE markdown document, edits it
freely, and returns the FULL new markdown. No find/replace, no per-section
attribution, no history, no previous-best — just failures + successes + the
whole prompt in front of it.

This is the paper-faithful `LLMOptimize(p_old, E_fail, E_gold)` step.

The system prompt is parameterized by dataset via a short task description
(one sentence, no error-mode hints). See `_TASK_DESCRIPTIONS` below.
"""

from __future__ import annotations

from fdpo.data.loaders import Example

# One-sentence description of what the task actually is, per dataset. Injected
# into the optimizer's system message so the optimizer knows what kind of
# rewrite makes sense. Intentionally does NOT include error-mode hints (e.g.
# "hearsay questions often confuse effect-on-listener with truth-of-content")
# because those would be doing the optimizer's diagnosis job for it.
_TASK_DESCRIPTIONS = {
    "legalbench_hearsay": (
        "a binary hearsay classification task under U.S. Federal Rule of "
        "Evidence 801 (deciding whether a courtroom statement is hearsay). "
        "The output is Yes or No."
    ),
    "gsm8k": (
        "a grade-school math word problem where the correct answer is a "
        "specific integer. The output must end with a line containing the "
        "final numeric answer."
    ),
    "mmlu": (
        "a 4-way multiple-choice exam question (options A, B, C, D) that "
        "may come from any of several academic subjects (law, biology, "
        "philosophy, econometrics, computer security, mathematics). The "
        "output is a single letter A, B, C, or D."
    ),
    "arc_challenge": (
        "an ARC-Challenge science multiple-choice question (options A, B, "
        "C, D). The output is a single letter A, B, C, or D."
    ),
}

_DEFAULT_TASK_DESCRIPTION = "a classification task"


_SIMPLE_OPTIMIZER_SYSTEM_TEMPLATE = """You are working with an expert prompt
engineer to help a smaller LLM (the "solver") solve {task_description} more
reliably.

You will see:
  - the solver's current markdown-formatted prompt,
  - a batch of FAILURES — questions the solver got wrong, with the
    solver's answer and the correct answer alongside,
  - a small batch of CORRECTLY-SOLVED examples the current prompt
    already handles.

Your job is to rewrite the markdown so the solver reasons more reliably
on future unseen cases from the same task distribution. A good rewrite:

  - Surfaces the general reasoning principle that separates correct
    from incorrect answers on this task, and states it in terms the
    solver can apply to any new case it has not seen before.

  - Gives the solver the mental scaffolding it needs — a clearer way
    to think about the problem, a checklist, a decision procedure, a
    definition it can lean on. Whatever helps a competent-but-fallible
    model be more consistent.

  - Illustrates principles with invented examples when helpful, not
    with training cases pasted verbatim. Copying training questions
    causes the solver to pattern-match on wording and overfit.

  - Keeps the fixed markdown schema (## System Role, Context, Task
    Details, Constraints, Output Format). You may edit any section but
    must not add or remove headers.

  - Preserves the Output Format exactly. Changing it breaks the answer
    extractor, and every answer scores wrong regardless of correctness.

Return only the full rewritten markdown, starting with the first
`## Section` header. No prose, no fences, no commentary before or after."""


def _build_system_prompt(dataset: str) -> str:
    """Fill in the task description for the given dataset. Unknown datasets
    fall back to a generic 'classification task' phrasing so this never
    breaks; the fallback is intentional and OK for exploratory use."""
    task_desc = _TASK_DESCRIPTIONS.get(dataset, _DEFAULT_TASK_DESCRIPTION)
    return _SIMPLE_OPTIMIZER_SYSTEM_TEMPLATE.format(task_description=task_desc)


def build_simple_optimizer_messages(
    current_markdown: str,
    failures: list[dict],   # each: {question, output, gold}
    golds: list[Example],
    dataset: str = "unknown",
) -> list[dict]:
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

    user = (
        "FULL CURRENT PROMPT (markdown):\n"
        "```\n"
        f"{current_markdown.rstrip()}\n"
        "```\n\n"
        f"FAILURES ({len(failures)} training examples the current prompt "
        "got WRONG):\n"
        + "\n\n".join(fail_blocks)
        + "\n\n"
        f"CORRECTLY-SOLVED EXAMPLES ({len(golds)} cases the current prompt "
        "already gets right — do not break these):\n"
        + "\n\n".join(gold_blocks)
        + "\n\nRewrite the markdown now. Return ONLY the full new markdown."
    )
    return [{"role": "system", "content": _build_system_prompt(dataset)},
            {"role": "user", "content": user}]
