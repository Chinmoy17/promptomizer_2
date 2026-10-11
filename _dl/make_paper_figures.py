"""Paper-ready figures, written to Paper_COLING/figures/ (the folder paper.tex
reads from, so the Overleaf upload is self-contained).

Numbers: reported_results.json mirrors the author-selected RESULTS.md rows.
GPT-4.1 Mini AIME uses its matched v3 run. The retained GPT-4o-mini AIME
summary is marked separately and excluded from matched transfer analysis.
"""
from __future__ import annotations

import json
import runpy
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
    "pdf.fonttype": 42,
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


SOURCE = json.loads((ROOT / "Paper_COLING/Artifacts/reported_results.json").read_text("utf-8"))
DATA = [(row["benchmark"], row["solver"], row["baseline_pct"], row["final_pct"],
         row["recovered"], row["regressed"]) for row in SOURCE["results"]]
DELTA = {(row["benchmark"], row["solver"]): row["delta_pp"] for row in SOURCE["results"]}
SUMMARY_ONLY = {(row["benchmark"], row["solver"]) for row in SOURCE["results"]
                if row["provenance"] != "saved"}

# ---- Figure: recovered vs regressed (main text, full width) ----------------
fig, ax = plt.subplots(figsize=(6.3, 2.75))
for i, (b, m, _, _, rec, reg) in enumerate(DATA):
    if rec is None or reg is None:
        ax.text(i, 5, "R/G\nunknown", ha="center", fontsize=6.5, color="#555555")
        continue
    reported_only = (b, m) in SUMMARY_ONLY
    ax.bar(i, rec, color=C_REC, width=0.62, zorder=2,
           hatch="///" if reported_only else None, edgecolor="white")
    ax.bar(i, -reg, color=C_REG, width=0.62, zorder=2)
    ax.scatter([i], [rec - reg], marker="D", s=22, color="black", zorder=3)
    if rec:
        ax.text(i, rec + 1.3, f"+{rec}", ha="center", fontsize=7, color=C_REC)
    if reg:
        ax.text(i + 0.36, -reg - 0.2, f"-{reg}", ha="left", va="top", fontsize=7, color=C_REG)
ax.axhline(0, color="black", lw=0.7)
ax.set_xticks(range(len(DATA)))
ax.set_xticklabels([f"{b}{'*' if (b, m) in SUMMARY_ONLY else ''}\n{'4o-mini' if '4o' in m else '4.1 Mini'}"
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
fig.text(0.01, 0.01, "* GPT-4o-mini AIME: retained summary; excluded from matched transfer and resource analyses.", fontsize=6.2)
fig.tight_layout(rect=(0, 0.06, 1, 1))
save(fig, "fig_recovered_regressed")

# ---- Appendix: baseline -> final dumbbells ---------------------------------
fig, ax = plt.subplots(figsize=(6.3, 2.95))
order = ["AIME", "PUPA", "IFBench", "Hearsay", "MMLU"]
# deltas exactly as in the tables (computed from unrounded scores)
for gi, b in enumerate(order):
    for off, m, col in ((-0.17, "GPT-4o-mini", C_4O), (0.17, "GPT-4.1 Mini", C_41)):
        _, _, base, fin, *_ = next(d for d in DATA if d[0] == b and d[1] == m)
        x = gi + off
        lc = C_REC if fin >= base else C_REG
        ax.plot([x, x], [base, fin], color=lc, lw=2.0, zorder=1, solid_capstyle="round",
                linestyle="--" if (b, m) in SUMMARY_ONLY else "-")
        ax.scatter([x], [base], facecolor="white", edgecolor=col, s=34, lw=1.4, zorder=3)
        ax.scatter([x], [fin], facecolor=col, edgecolor=col, s=34, zorder=3)
        ax.text(x, max(base, fin) + 3, f"{DELTA[(b, m)]:+.1f}", ha="center", fontsize=6.8,
                color=lc, fontweight="bold")
ax.set_xticks(range(5))
ax.set_xticklabels(["AIME*", "PUPA (composite)", "IFBench", "Hearsay", "MMLU (macro)"])
ax.set_ylabel("Score (%)")
ax.set_ylim(0, 100)
ax.legend(handles=[
    Line2D([0], [0], marker="o", color="w", markerfacecolor=C_4O, markersize=6, label="GPT-4o-mini"),
    Line2D([0], [0], marker="o", color="w", markerfacecolor=C_41, markersize=6, label="GPT-4.1 Mini"),
    Line2D([0], [0], color=C_REC, lw=2, label="improved"),
    Line2D([0], [0], color=C_REG, lw=2, label="regressed")],
    loc="upper center", ncol=4, frameon=False, bbox_to_anchor=(0.5, 1.15))
fig.text(0.01, 0.01, "* Only GPT-4o-mini AIME is summary-based; GPT-4.1 Mini uses the matched v3 record.", fontsize=6.5)
fig.tight_layout(rect=(0, 0.06, 1, 1))
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

for script in ("make_architecture_v3.py", "make_metric_figure.py", "make_transfer_figure.py"):
    runpy.run_path(str(ROOT / "_dl" / script), run_name="__main__")
