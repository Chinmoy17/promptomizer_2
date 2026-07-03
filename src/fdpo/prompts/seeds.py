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
}


def seed_sections(dataset: str, schema: tuple[str, ...]) -> dict[str, str]:
    base = _SEEDS[dataset]
    if schema == SCHEMA_5:
        return dict(base)
    if schema == SCHEMA_MONOLITHIC:
        return {"full_prompt": monolithic_text(base)}
    raise ValueError(f"unknown schema: {schema}")
