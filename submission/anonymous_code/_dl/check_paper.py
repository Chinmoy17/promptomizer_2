"""Static checks for Paper_COLING/paper.tex (no TeX toolchain needed)."""
import json
import math
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent / "Paper_COLING"
t = (root / "paper.tex").read_text(encoding="utf-8")
b = (root / "custom.bib").read_text(encoding="utf-8")

print("em dashes:", t.count("\u2014"), "| '---':", t.count("---"))

labels = set(re.findall(r"\\label\{([^}]+)\}", t))
refs = {reference for reference in re.findall(r"\\(?:ref|pageref)\{([^}]+)\}", t)
    if not reference.startswith("#")}
failures = []
print(f"labels={len(labels)} refs={len(refs)}")
print("undefined refs:", sorted(refs - labels))
if refs - labels:
    failures.append("undefined cross-references")
print("unused labels :", sorted(labels - refs))

cites = set()
for m in re.findall(r"\\cite\w*\*?(?:\[[^\]]*\]){0,2}\{([^}]+)\}", t):
    cites |= {c.strip() for c in m.split(",")}
keys = set(re.findall(r"@\w+\{([^,\s]+),", b))
print(f"cited={len(cites)} bib_keys={len(keys)}")
print("cited but missing from custom.bib:", sorted(cites - keys))
if cites - keys:
    failures.append("missing bibliography entries")
print("in custom.bib but uncited (template leftovers ok):", sorted(keys - cites))

for g in re.findall(r"includegraphics\[[^\]]*\]\{([^}]+)\}", t):
    print(("OK       " if (root / g).exists() else "MISSING  ") + g)
    if not (root / g).exists():
        failures.append(f"missing figure: {g}")

for env in ["figure", "figure*", "table", "table*", "align", "algorithm",
            "algorithmic", "enumerate", "tabular", "abstract"]:
    d = t.count("\\begin{" + env + "}") - t.count("\\end{" + env + "}")
    if d:
        print("UNBALANCED", env, d)
        failures.append(f"unbalanced {env} environment")

artifacts = root / "Artifacts"
reported = json.loads((artifacts / "reported_results.json").read_text(encoding="utf-8"))
paired = json.loads((artifacts / "val_test_gap.json").read_text(encoding="utf-8"))
resources = json.loads((artifacts / "resource_usage.json").read_text(encoding="utf-8"))
edited = [record for record in paired if record["shipped"]]
validation_up = [record for record in edited if record["val_best"] > record["val_base"]]
test_down = [record for record in validation_up if record["test_final"] < record["test_base"]]
if (len(paired), len(edited), len(validation_up), len(test_down)) != (19, 17, 12, 4):
    failures.append("matched analysis population changed")
aime = next(record for record in reported["results"]
            if record["benchmark"] == "AIME" and record["solver"] == "GPT-4.1 Mini")
if (aime["recovered"], aime["regressed"], aime["n_test"]) != (3, 4, 30):
    failures.append("AIME transition counts changed")
if not math.isclose(aime["baseline_pct"], 100 * 16 / 30) or aime["final_pct"] != 50:
    failures.append("AIME endpoints differ from the matched v3 record")
for record in reported["results"]:
    if record["benchmark"] not in {"PUPA", "MMLU"}:
        score_delta = record["final_pct"] - record["baseline_pct"]
        count_delta = 100 * (record["recovered"] - record["regressed"]) / record["n_test"]
        if not math.isclose(score_delta, count_delta, rel_tol=0, abs_tol=0.100001):
            failures.append(f"transition identity mismatch: {record['benchmark']} / {record['solver']}")
if not resources["ledger_verified"] or len(resources["runs"]) != 19:
    failures.append("resource population is not ledger-verified")
if {record["run_id"] for record in paired} != {record["run_id"] for record in resources["runs"]}:
    failures.append("transfer and resource run IDs differ")
resource_table = next(block for block in re.findall(r"\\begin\{table\*\}.*?\\end\{table\*\}", t, re.S)
                      if r"\label{tab:resources}" in block)
for record in resources["aggregates"]:
    benchmark = "MMLU (six subjects)" if record["benchmark"] == "MMLU" else record["benchmark"]
    expected = (f"{benchmark} & {record['solver']} & {record['optimizer_calls']} & "
                f"{record['optimizer_input_tokens'] / 1000:,.1f} & "
                f"{record['optimizer_output_tokens'] / 1000:,.1f} & "
                f"{record['total_tokens'] / 1000:,.1f} & {record['total_cost_usd']:.2f}")
    if expected not in resource_table:
        failures.append(f"resource table mismatch: {benchmark} / {record['solver']}")
if r"\square" in t:
    failures.append("unavailable square symbol: use the loaded latexsym Box symbol")
print("matched records / edited / validation-up / test-down:",
      len(paired), len(edited), len(validation_up), len(test_down))
print("resource table: exact ledger aggregates checked")

print("GEPA mentions:", len(re.findall("GEPA", t)))
print("TODO/FIXME markers:", re.findall(r"TODO[^\n]*|FIXME[^\n]*", t))
body = t.split("\\section*{Limitations}")[0]
words = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[A-Za-z]+|\$[^$]*\$|%[^\n]*", " ", body)))
print("approx. words before Limitations:", words)
if failures:
    raise SystemExit("FAILED: " + "; ".join(failures))
print("PASS: static source and reporting-data checks (PDF layout not checked)")
