"""Static checks for Paper_COLING/paper.tex (no TeX toolchain needed)."""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent / "Paper_COLING"
t = (root / "paper.tex").read_text(encoding="utf-8")
b = (root / "custom.bib").read_text(encoding="utf-8")

print("em dashes:", t.count("\u2014"), "| '---':", t.count("---"))

labels = set(re.findall(r"\\label\{([^}]+)\}", t))
refs = set(re.findall(r"\\ref\{([^}]+)\}", t))
print(f"labels={len(labels)} refs={len(refs)}")
print("undefined refs:", sorted(refs - labels))
print("unused labels :", sorted(labels - refs))

cites = set()
for m in re.findall(r"\\cite[pt]?\{([^}]+)\}", t):
    cites |= {c.strip() for c in m.split(",")}
keys = set(re.findall(r"@\w+\{([^,\s]+),", b))
print(f"cited={len(cites)} bib_keys={len(keys)}")
print("cited but missing from custom.bib:", sorted(cites - keys))
print("in custom.bib but uncited (template leftovers ok):", sorted(keys - cites))

for g in re.findall(r"includegraphics\[[^\]]*\]\{([^}]+)\}", t):
    print(("OK       " if (root / g).exists() else "MISSING  ") + g)

for env in ["figure", "figure*", "table", "table*", "align", "algorithm",
            "algorithmic", "enumerate", "tabular", "abstract"]:
    d = t.count("\\begin{" + env + "}") - t.count("\\end{" + env + "}")
    if d:
        print("UNBALANCED", env, d)

print("GEPA mentions:", len(re.findall("GEPA", t)))
print("TODO/FIXME markers:", re.findall(r"TODO[^\n]*|FIXME[^\n]*", t))
body = t.split("\\section*{Limitations}")[0]
words = len(re.findall(r"[A-Za-z]{2,}", re.sub(r"\\[A-Za-z]+|\$[^$]*\$|%[^\n]*", " ", body)))
print("approx. words before Limitations:", words)
