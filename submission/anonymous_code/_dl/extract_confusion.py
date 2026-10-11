import json
from pathlib import Path

files = {
    "AIME_GPT4OMINI": r"results\reflect_aime_v1\aime_reflect_fdpo_gpt-4o-mini_s0_20260829-223614\metrics.json",
    "AIME_GPT41MINI": r"results\reflect_aime_gpt41mini_v3\aime_reflect_fdpo_gpt-4.1-mini_s0_20260916-203408\metrics.json",
    "PUPA_GPT4OMINI": r"results\pupa_pilot_v1\pupa_reflect_fdpo_gpt-4o-mini_s0_20260830-153941\metrics.json",
    "PUPA_GPT41MINI": r"results\pupa_pilot_gpt41mini_v2\pupa_reflect_fdpo_gpt-4.1-mini_s0_20260916-170119\metrics.json",
    "IFBENCH_GPT4OMINI_V1": r"results\reflect_ifbench_v1\ifbench_reflect_fdpo_gpt-4o-mini_s0_20260829-134611\metrics.json",
    "IFBENCH_GPT4OMINI_V2": r"results\reflect_ifbench_v2\ifbench_reflect_fdpo_gpt-4o-mini_s0_20260829-140120\metrics.json",
    "IFBENCH_GPT41MINI": r"results\reflect_ifbench_gpt41mini_v2\ifbench_reflect_fdpo_gpt-4.1-mini_s0_20260916-163821\metrics.json",
    "HEARSAY_GPT41MINI": r"results\reflect_hearsay_gpt41mini_v1\legalbench_hearsay_reflect_fdpo_gpt-4.1-mini_s0_20260916-220125\metrics.json",
    "MMLU_4OMINI_COLLEGE_MATH": r"results\mmlu_reflect_college_mathematics\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-144018\metrics.json",
    "MMLU_4OMINI_COMPSEC": r"results\mmlu_reflect_computer_security\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-151324\metrics.json",
    "MMLU_4OMINI_ECON": r"results\mmlu_reflect_econometrics\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-145654\metrics.json",
    "MMLU_4OMINI_HSBIO": r"results\mmlu_reflect_high_school_biology\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-150241\metrics.json",
    "MMLU_4OMINI_PHIL": r"results\mmlu_reflect_philosophy\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-145252\metrics.json",
    "MMLU_4OMINI_LAW": r"results\mmlu_reflect_professional_law\mmlu_reflect_fdpo_gpt-4o-mini_s0_20260830-150810\metrics.json",
    "MMLU_41MINI_COLLEGE_MATH": r"results\mmlu_reflect_gpt41mini_college_mathematics\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-221726\metrics.json",
    "MMLU_41MINI_COMPSEC": r"results\mmlu_reflect_gpt41mini_computer_security\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-221911\metrics.json",
    "MMLU_41MINI_ECON": r"results\mmlu_reflect_gpt41mini_econometrics\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-222331\metrics.json",
    "MMLU_41MINI_HSBIO": r"results\mmlu_reflect_gpt41mini_high_school_biology\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-222802\metrics.json",
    "MMLU_41MINI_PHIL": r"results\mmlu_reflect_gpt41mini_philosophy\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-222836\metrics.json",
    "MMLU_41MINI_LAW": r"results\mmlu_reflect_gpt41mini_professional_law\mmlu_reflect_fdpo_gpt-4.1-mini_s0_20260916-223205\metrics.json",
}

for label, rel in files.items():
    p = Path(rel)
    if not p.exists():
        print(f"LABEL={label}; FILE_NOT_FOUND")
        continue
    data = json.loads(p.read_text(encoding="utf-8"))
    tc = data.get("optimization", {}).get("test_confusion") or data.get("test_confusion")
    if tc is None:
        print(f"LABEL={label}; NO_TEST_CONFUSION")
        continue
    rec = len(tc.get("recoveries", []))
    reg = len(tc.get("regressions", []))
    net = tc.get("net_gain")
    print(f"LABEL={label}; RECOVERED={rec}; REGRESSED={reg}; NET={net}")
