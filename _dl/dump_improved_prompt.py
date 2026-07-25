"""Ad-hoc: dump the full improved prompt + active-pointer state from a
simple_fdpo run's registry.json."""
import json
import sys

path = sys.argv[1]
r = json.load(open(f"{path}/registry.json", encoding="utf-8"))
titles = {
    "system_role": "System Role", "context": "Context",
    "task_details": "Task Details", "constraints": "Constraints",
    "output_format": "Output Format",
}
schema = ["system_role", "context", "task_details", "constraints", "output_format"]

print("=" * 70)
print("FULL IMPROVED PROMPT (last optimizer version of each section)")
print("=" * 70)
for sec in schema:
    v = r["sections"][sec]["versions"]
    changed = "CHANGED by optimizer" if len(v) > 1 else "kept vague (untouched)"
    print(f"\n## {titles[sec]}   [{changed}, {len(v)} versions]")
    print(v[-1]["text"])

print("\n" + "=" * 70)
print("ACTIVE POINTERS  (which version was FINALLY tested)")
print("=" * 70)
for sec in schema:
    st = r["sections"][sec]
    n = len(st["versions"])
    active = st["active_version"]
    tag = "VAGUE SEED" if active == 0 else f"optimizer v{active}"
    print(f"  {sec:14s} active = v{active} of {n-1}  -> {tag}")
