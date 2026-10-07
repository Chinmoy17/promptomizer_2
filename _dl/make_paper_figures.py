"""Paper-ready figures, written to Paper_COLING/figures/ (the folder paper.tex
reads from, so the Overleaf upload is self-contained).

Numbers: RESULTS.md / saved metrics.json. AIME / GPT-4.1 Mini uses the saved
v3 run (53.3 -> 50.0, 3 recovered / 4 regressed). The validation-vs-test
scatter reads Paper_COLING/Artifacts/val_test_gap.json (from _dl/val_test_gap.py).
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Paper_COLING" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

C_4O, C_41 = "#4C72B0", "#DD8452"
C_REC, C_REG = "#2E7D32", "#C62828"
C_GEPA = "#9E9E9E"
BENCH_COLORS = {"AIME": "#8172B3", "PUPA": "#55A868", "IFBench": "#C44E52",
                "Hearsay": "#4C72B0", "MMLU": "#999999"}

plt.rcParams.update({
    "font.family": "serif", "font.size": 8, "axes.titlesize": 8.5,
    "axes.labelsize": 8, "legend.fontsize": 7, "xtick.labelsize": 7.5,
    "ytick.labelsize": 7.5, "savefig.dpi": 300,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4,
})


def save(fig, name):
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    plt.close(fig)
    print("wrote", name)


# (benchmark, model, base, final, recovered, regressed)
DATA = [
    ("AIME", "GPT-4o-mini", 13.3, 10.0, 0, 1),
    ("AIME", "GPT-4.1 Mini", 53.3, 50.0, 3, 4),
    ("PUPA", "GPT-4o-mini", 68.5, 79.9, 7, 3),
    ("PUPA", "GPT-4.1 Mini", 68.2, 80.7, 10, 0),
    ("IFBench", "GPT-4o-mini", 47.6, 45.2, 2, 3),
    ("IFBench", "GPT-4.1 Mini", 42.9, 66.7, 12, 2),
    ("Hearsay", "GPT-4o-mini", 71.4, 69.4, 8, 9),
    ("Hearsay", "GPT-4.1 Mini", 71.4, 73.5, 7, 6),
    ("MMLU", "GPT-4o-mini", 75.1, 77.2, 31, 23),
    ("MMLU", "GPT-4.1 Mini", 81.0, 83.3, 17, 8),
]

# ---- Figure: recovered vs regressed (main text, full width) ----------------
fig, ax = plt.subplots(figsize=(6.3, 2.45))
for i, (b, m, _, _, rec, reg) in enumerate(DATA):
    ax.bar(i, rec, color=C_REC, width=0.62, zorder=2)
    ax.bar(i, -reg, color=C_REG, width=0.62, zorder=2)
    ax.scatter([i], [rec - reg], marker="D", s=22, color="black", zorder=3)
    if rec:
        ax.text(i, rec + 1.3, f"+{rec}", ha="center", fontsize=7, color=C_REC)
    if reg:
        ax.text(i + 0.36, -reg - 0.2, f"-{reg}", ha="left", va="top", fontsize=7, color=C_REG)
ax.axhline(0, color="black", lw=0.7)
ax.set_xticks(range(len(DATA)))
ax.set_xticklabels([f"{b}\n{'4o-mini' if '4o' in m else '4.1 Mini'}"
                    for b, m, *_ in DATA], fontsize=7)
ax.set_ylabel("Test items")
ax.set_ylim(-30, 38)
ax.legend(handles=[
    Line2D([0], [0], marker="s", color="w", markerfacecolor=C_REC, markersize=7,
           label="Recovered (wrong to right)"),
    Line2D([0], [0], marker="s", color="w", markerfacecolor=C_REG, markersize=7,
           label="Regressed (right to wrong)"),
    Line2D([0], [0], marker="D", color="w", markerfacecolor="black", markersize=5,
           label="Net change")], loc="upper left", frameon=False, ncol=3,
    bbox_to_anchor=(0.0, 1.16))
fig.tight_layout()
save(fig, "fig_recovered_regressed")

# ---- Figure: validation gain vs test change (single column) ----------------
rows = json.loads((ROOT / "Paper_COLING/Artifacts/val_test_gap.json").read_text("utf-8"))
fig, ax = plt.subplots(figsize=(3.15, 3.0))
lim = 28
ax.axhline(0, color="black", lw=0.6)
ax.axvline(0, color="black", lw=0.6)
ax.plot([-6, lim], [-6, lim], ls="--", color="#888888", lw=0.8, zorder=1)
ax.fill_between([0, lim], -8, 0, color="#fde2e2", zorder=0)
ax.text(lim - 0.5, -6.9, "validation up,\ntest flat or down", ha="right", va="bottom",
        fontsize=6.3, color=C_REG, style="italic")
labelled = {"AIME / 4.1-mini": (2, 5), "IFBench / 4o-mini": (-2, -9),
            "Hearsay / 4o-mini": (5, -7)}
for r in rows:
    if not r["shipped"] or r["val_gain_pp"] is None:
        continue
    fam = "MMLU" if r["run"].startswith("MMLU") else r["run"].split(" / ")[0]
    mk = "o" if "4o-mini" in r["run"] else "s"
    ax.scatter(r["val_gain_pp"], r["test_delta_pp"], marker=mk, s=26 if fam != "MMLU" else 16,
               color=BENCH_COLORS[fam], edgecolor="white", linewidth=0.4,
               alpha=1.0 if fam != "MMLU" else 0.75, zorder=3)
    if r["run"] in labelled:
        pass
ax.set_xlim(-6, lim)
ax.set_ylim(-9, 30)
ax.set_xlabel("Validation gain, baseline to best round (pp)")
ax.set_ylabel("Sealed-test change (pp)")
handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=c, markersize=5.5, label=k)
           for k, c in BENCH_COLORS.items()]
handles += [Line2D([0], [0], marker="o", color="w", markerfacecolor="#777777", markersize=5,
                   label="4o-mini"),
            Line2D([0], [0], marker="s", color="w", markerfacecolor="#777777", markersize=5,
                   label="4.1 Mini")]
ax.legend(handles=handles, loc="upper left", frameon=False, ncol=2, fontsize=6,
          handletextpad=0.2, columnspacing=0.8, borderaxespad=0.1)
fig.tight_layout()
save(fig, "fig_val_vs_test")

# ---- Appendix: baseline -> final dumbbells ---------------------------------
fig, ax = plt.subplots(figsize=(6.3, 2.7))
order = ["AIME", "PUPA", "IFBench", "Hearsay", "MMLU"]
# deltas exactly as in the tables (computed from unrounded scores)
DELTA = {("AIME", "GPT-4o-mini"): -3.3, ("AIME", "GPT-4.1 Mini"): -3.3,
         ("PUPA", "GPT-4o-mini"): 11.4, ("PUPA", "GPT-4.1 Mini"): 12.5,
         ("IFBench", "GPT-4o-mini"): -2.4, ("IFBench", "GPT-4.1 Mini"): 23.8,
         ("Hearsay", "GPT-4o-mini"): -2.0, ("Hearsay", "GPT-4.1 Mini"): 2.0,
         ("MMLU", "GPT-4o-mini"): 2.0, ("MMLU", "GPT-4.1 Mini"): 2.3}
for gi, b in enumerate(order):
    for off, m, col in ((-0.17, "GPT-4o-mini", C_4O), (0.17, "GPT-4.1 Mini", C_41)):
        _, _, base, fin, *_ = next(d for d in DATA if d[0] == b and d[1] == m)
        x = gi + off
        lc = C_REC if fin >= base else C_REG
        ax.plot([x, x], [base, fin], color=lc, lw=2.0, zorder=1, solid_capstyle="round")
        ax.scatter([x], [base], facecolor="white", edgecolor=col, s=34, lw=1.4, zorder=3)
        ax.scatter([x], [fin], facecolor=col, edgecolor=col, s=34, zorder=3)
        ax.text(x, max(base, fin) + 3, f"{DELTA[(b, m)]:+.1f}", ha="center", fontsize=6.8,
                color=lc, fontweight="bold")
ax.set_xticks(range(5))
ax.set_xticklabels(["AIME", "PUPA (composite)", "IFBench", "Hearsay", "MMLU (macro)"])
ax.set_ylabel("Score (%)")
ax.set_ylim(0, 100)
ax.legend(handles=[
    Line2D([0], [0], marker="o", color="w", markerfacecolor=C_4O, markersize=6, label="GPT-4o-mini"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=C_41, markersize=6, label="GPT-4.1 Mini"),
    Line2D([0], [0], color=C_REC, lw=2, label="improved"),
    Line2D([0], [0], color=C_REG, lw=2, label="regressed")],
    loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.15))
fig.tight_layout()
save(fig, "fig_dumbbell")

# ---- Appendix: optimizer-call budget, GEPA vs ours (log scale) -------------
budget = {
    "AIME": [24, 90, 3, 3], "PUPA": [46, 38, 3, 3], "IFBench": [21, 17, 3, 3]}
names = ["GEPA (GPT-4.1 Mini)", "GEPA (Qwen3-8B)", "Ours (GPT-4o-mini)", "Ours (GPT-4.1 Mini)"]
cols = [C_GEPA, "#C9C9C9", C_4O, C_41]
fig, ax = plt.subplots(figsize=(6.3, 2.4))
w = 0.19
for si, (n, c) in enumerate(zip(names, cols)):
    xs = [gi + (si - 1.5) * w for gi in range(3)]
    vals = [budget[b][si] for b in budget]
    ax.bar(xs, vals, width=w, color=c, label=n, zorder=2)
    for x, v in zip(xs, vals):
        ax.text(x, v * 1.15, str(v), ha="center", fontsize=7)
ax.set_yscale("log")
ax.set_ylim(2, 160)
ax.set_xticks(range(3))
ax.set_xticklabels(list(budget))
ax.set_ylabel("Optimizer LM calls")
ax.legend(loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.2), fontsize=6.8)
fig.tight_layout()
save(fig, "fig_call_budget")
