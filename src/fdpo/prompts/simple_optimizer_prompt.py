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
    "legalbench_contract_nli": (
        "a binary contract-clause classification task (deciding whether a "
        "confidentiality clause requires Confidential Information to be "
        "explicitly marked or identified as confidential). The output is "
        "Yes or No."
    ),
    "gsm8k": (
        "a grade-school math word problem where the correct answer is a "
        "specific integer. The output must end with a line containing the "
        "final numeric answer."
    ),
    "aime": (
        "a competition-level (AIME) math problem, substantially harder than "
        "grade-school word problems -- multi-step algebra, combinatorics, "
        "number theory, geometry, or probability. The correct answer is "
        "always a specific integer between 0 and 999. The output must end "
        "with a line containing the final numeric answer."
    ),
    "mmlu": (
        "a 4-way multiple-choice exam question (options A, B, C, D) from one "
        "academic subject. Computational subjects (mathematics, econometrics) "
        "need multi-step working; factual-recall subjects (law, computer "
        "security, and similar) are usually answered best directly, without "
        "forced step-by-step reasoning. The final answer is a single letter "
        "A, B, C, or D on an 'Answer:' line."
    ),
    "arc": (
        "an ARC-Challenge science multiple-choice question (options A, B, "
        "C, D). The output is a single letter A, B, C, or D."
    ),
    "ifeval": (
        "an instruction-following task: the user's request embeds one or "
        "more mechanically VERIFIABLE constraints (e.g. exact word/sentence/"
        "paragraph counts, forbidden or required keywords, output format "
        "such as JSON or a title wrapped in << >>, letter case, punctuation "
        "rules, quotation wrapping). There is no single correct 'answer' to "
        "match against a gold label -- correctness means the CHECKED text "
        "satisfies every listed constraint, checked by code, not by content "
        "quality. UNLIKE every other task type: the checker scores the "
        "solver's ENTIRE raw output, not one extracted final line -- EXCEPT "
        "that text before a standalone 'FINAL RESPONSE:' line (if the "
        "solver writes one) is ignored, and only the text after it is "
        "checked. This means the solver MAY reason/plan out loud before "
        "that marker (e.g. counting words, checking a forbidden-word list) "
        "-- keep the Output Format section instructing the solver to use "
        "this marker; do NOT tell it to give zero reasoning/commentary at "
        "all, since planning genuinely helps on multi-constraint items, as "
        "long as the planning stays before the marker so it is never "
        "checked. A failure means one or more specific constraints were "
        "violated in the checked text; the fix is to make the solver track "
        "and satisfy ALL stated constraints simultaneously."
    ),
    "ifbench": (
        "an instruction-following task with the same mechanically verifiable "
        "constraint structure and the same 'FINAL RESPONSE:' marker "
        "convention as IFEval (see that description for the full "
        "explanation), but drawn from a broader set of constraint types "
        "(word/consonant/vowel counts, keyword-frequency and forbidden-word "
        "rules, formatting requirements, and more). Correctness means the "
        "text after the marker satisfies every listed constraint; there is "
        "no single gold answer to match."
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
on future unseen cases from the same task distribution.

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

You may be given SEVERAL refinement rounds rather than a single shot. Treat
each rewrite as a deliberate, measurable experiment: make high-conviction
changes, not timid paraphrases, and when you are told what your previous
rewrite recovered or regressed, keep what worked and repair what broke.

A good rewrite:

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
    round_num: int = 1,
    max_rounds: int = 1,
    prev_outcome: str | None = None,
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

    iteration_context = ""
    if max_rounds > 1:
        note = f" {prev_outcome}" if prev_outcome else ""
        iteration_context = (
            f"ITERATION CONTEXT: This is refinement round {round_num} of "
            f"{max_rounds}. This is NOT a one-shot job -- your rewrite is scored "
            f"on held-out examples and you will get further rounds to refine it, "
            f"so make one deliberate, testable change this round.{note}\n\n"
        )

    user = (
        iteration_context
        + "FULL CURRENT PROMPT (markdown):\n"
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
