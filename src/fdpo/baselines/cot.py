"""Static CoT baselines: zero-shot (B1) and few-shot (B2).

Both use the same seed sections as FDPO's starting prompt so the comparison
isolates the optimization loop, not prompt authorship.
"""

from __future__ import annotations

from fdpo.data.loaders import Example

COT_TRIGGER = "Let's think step by step."


def build_shots(dataset: str, exemplars: list[Example]) -> list[tuple[str, str]]:
    """(user, assistant) exemplar pairs in the same answer format the
    extractors expect."""
    shots = []
    for ex in exemplars:
        if dataset == "gsm8k":
            answer = ex.reference  # includes reasoning and the '#### n' line
        elif dataset == "legalbench_hearsay":
            answer = f"{COT_TRIGGER}\nAnswer: {ex.gold}"
        else:  # multiple choice
            answer = f"{COT_TRIGGER}\nAnswer: {ex.gold}"
        shots.append((ex.question, answer))
    return shots
