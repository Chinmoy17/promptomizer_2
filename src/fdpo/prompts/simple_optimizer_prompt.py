"""Simple-mode optimizer prompt: the LLM sees ONE markdown document, edits it
freely, and returns the FULL new markdown. No find/replace, no per-section
attribution, no history, no previous-best — just failures + successes + the
whole prompt in front of it.

This is the paper-faithful `LLMOptimize(p_old, E_fail, E_gold)` step.
"""

from __future__ import annotations

from fdpo.data.loaders import Example

_SIMPLE_OPTIMIZER_SYSTEM = """You are an expert prompt engineer. You will
rewrite a markdown prompt that guides a smaller LLM on a classification task.

You are teaching a model to REASON about future unseen cases — not to
memorize the specific ones shown to you here.

You are given:
  - The FULL CURRENT PROMPT as a markdown document with `## Section` headers.
  - FAILURES: training examples where the current prompt produced the WRONG answer.
  - CORRECTLY-SOLVED EXAMPLES: cases the current prompt already gets right.

Your job:
  - Rewrite the markdown to fix the failures while preserving what already works.
  - You may edit any section, add clarifications, or restructure paragraphs.
    You may NOT add new top-level `## Section` headers or delete existing
    ones — the schema is fixed at: System Role, Context, Task Details,
    Constraints, Output Format.
  - Do NOT change the answer format specified in the Output Format section.

CRITICAL — rules of extrapolation, not memorization:
  - **Do NOT copy specific questions, statements, names, or scenarios from
    the failures or gold examples into the rewritten prompt.** A rule that
    pastes concrete cases can only match cases lexically similar to them —
    it cannot generalize to unseen ones and will overfit the training batch
    while regressing on the test set.
  - Extract the DISCRIMINATIVE STRUCTURAL FEATURE that distinguishes the
    correct from the incorrect predictions. State that feature abstractly.
    Example of a good rule: "A statement is hearsay only when the argument
    depends on its content being true." Example of a BAD rule (do not do
    this): "'Real Madrid is the best' offered to show Tim is a soccer fan
    is not hearsay" — this is a memorized case, not a rule.
  - Prefer scoped, narrow rules over broad single-keyword triggers. A rule
    like "if the statement mentions X, it is not Y" over-applies to
    unrelated cases sharing the keyword. Tie the rule to the underlying
    structural condition instead.
  - If you genuinely need to illustrate a distinction, describe the pattern
    in ABSTRACT terms (e.g., "when a statement is offered only to prove
    that some conversation occurred, not that its content is true, it is
    NOT hearsay"). Do not name specific people or paraphrase specific
    training statements.
  - The rewritten prompt should be readable in isolation. A future reader
    who never sees the failures shown to you should still understand the
    reasoning and be able to apply it to novel cases.

Return ONLY the full new markdown document. No fences, no explanations before
or after — just the markdown starting with the first `## Section` header."""


def build_simple_optimizer_messages(
    current_markdown: str,
    failures: list[dict],   # each: {question, output, gold}
    golds: list[Example],
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
    return [{"role": "system", "content": _SIMPLE_OPTIMIZER_SYSTEM},
            {"role": "user", "content": user}]
