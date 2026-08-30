"""Hand-written seed prompts (version 0 of every section), one per dataset.

Deliberately plain: these are the starting points FDPO is supposed to improve.
Each output_format section MUST match the corresponding extractor in
fdpo.data.extraction (#### number / Answer: LETTER / Answer: Yes|No).
"""

from __future__ import annotations

from fdpo.core.prompt import SCHEMA_5, SCHEMA_MONOLITHIC, monolithic_text

_SEEDS: dict[str, dict[str, str]] = {
    "gsm8k": {
        "system_role": "You are a careful math tutor who solves word problems.",
        "context": "You will be given a grade-school math word problem.",
        "task_details": "Solve the problem step by step, showing your arithmetic.",
        "constraints": "Do not skip steps. Do not invent quantities that are not "
                       "in the problem.",
        "output_format": "After your reasoning, write the final numeric answer on "
                         "its own line in exactly this form: #### <number>",
    },
    "arc": {
        "system_role": "You are a knowledgeable science teacher answering "
                       "multiple-choice questions.",
        "context": "You will be given a science question with lettered options.",
        "task_details": "Reason briefly about each option and pick the single "
                        "best answer.",
        "constraints": "Choose exactly one of the given letters. Never answer "
                       "with a letter that is not offered.",
        "output_format": "End your response with a line in exactly this form: "
                         "Answer: <LETTER>",
    },
    "mmlu": {
        "system_role": "You are an expert exam-taker across academic subjects.",
        "context": "You will be given a multiple-choice exam question with "
                   "options A-D.",
        "task_details": "Think through the question, eliminate wrong options, "
                        "and select the best answer.",
        "constraints": "Choose exactly one of A, B, C, or D.",
        "output_format": "End your response with a line in exactly this form: "
                         "Answer: <LETTER>",
    },
    "legalbench_hearsay": {
        "system_role": "You are a U.S. evidence-law expert.",
        "context": "Hearsay is an out-of-court statement offered to prove the "
                   "truth of the matter asserted.",
        "task_details": "Decide whether the given statement is hearsay.",
        "constraints": "Apply the definition strictly; conduct is not hearsay "
                       "unless it is assertive.",
        "output_format": "End your response with a line in exactly this form: "
                         "Answer: Yes  (or)  Answer: No",
    },
    "legalbench_contract_nli": {
        "system_role": "You are a contract-law expert.",
        "context": "A confidentiality clause may or may not require that "
                   "Confidential Information be explicitly marked or identified "
                   "as confidential in order to be protected.",
        "task_details": "Decide whether the given clause requires Confidential "
                        "Information to be explicitly marked or identified as "
                        "confidential.",
        "constraints": "Answer Yes only if the clause conditions protection on "
                       "explicit marking/identification; answer No if it "
                       "protects information regardless of marking.",
        "output_format": "End your response with a line in exactly this form: "
                         "Answer: Yes  (or)  Answer: No",
    },
    # ifeval/ifbench: overwritten immediately by prompts/<dataset>.md via
    # bootstrap_registry_from_markdown() for simple_fdpo/reflect_fdpo (see
    # scripts/run_experiment.py) -- this is only the placeholder PromptRegistry
    # is constructed with before that swap, and the fallback if no markdown
    # file exists (true for ifbench today; see hf_fetch.py's docstring on why
    # ifbench isn't runnable yet regardless of seed prompt).
    "ifeval": {
        "system_role": "You are a helpful assistant.",
        "context": "The user's request may include one or more specific "
                   "requirements about the format, length, wording, or "
                   "content of your response.",
        "task_details": "Answer the user's request.",
        "constraints": "Follow any requirements stated in the request.",
        "output_format": "If reasoning or planning would help you satisfy the "
                         "constraints, think it through first. Then write a "
                         "line containing exactly `FINAL RESPONSE:` on its "
                         "own, followed immediately by ONLY the content that "
                         "must satisfy every stated constraint. Everything "
                         "before that line is ignored when checking "
                         "constraints; everything after it, verbatim, is "
                         "what gets checked. If no reasoning is needed, "
                         "`FINAL RESPONSE:` may be the very first line.",
    },
    "ifbench": {
        "system_role": "You are a helpful assistant.",
        "context": "The user's request may include one or more specific "
                   "requirements about the format, length, wording, or "
                   "content of your response.",
        "task_details": "Answer the user's request.",
        "constraints": "Follow any requirements stated in the request.",
        "output_format": "If reasoning or planning would help you satisfy the "
                         "constraints, think it through first. Then write a "
                         "line containing exactly `FINAL RESPONSE:` on its "
                         "own, followed immediately by ONLY the content that "
                         "must satisfy every stated constraint. Everything "
                         "before that line is ignored when checking "
                         "constraints; everything after it, verbatim, is "
                         "what gets checked. If no reasoning is needed, "
                         "`FINAL RESPONSE:` may be the very first line.",
    },
    "aime": {
        "system_role": "You are a competition mathematician.",
        "context": "You will be given a competition-style math problem whose "
                   "answer is always an integer between 0 and 999.",
        "task_details": "Solve the problem.",
        "constraints": "The final answer must be an integer between 0 and 999.",
        "output_format": "After your work, write the final numeric answer on "
                         "its own line in exactly this form: #### <number>",
    },
}


def seed_sections(dataset: str, schema: tuple[str, ...]) -> dict[str, str]:
    base = _SEEDS[dataset]
    if schema == SCHEMA_5:
        return dict(base)
    if schema == SCHEMA_MONOLITHIC:
        return {"full_prompt": monolithic_text(base)}
    raise ValueError(f"unknown schema: {schema}")
