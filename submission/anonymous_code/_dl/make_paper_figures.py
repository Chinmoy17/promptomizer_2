"""Paper-ready figures, written to Paper_COLING/figures/ (the folder paper.tex
reads from, so the Overleaf upload is self-contained).

Numbers: reported_results.json mirrors the author-selected RESULTS.md rows.
Rows whose recovered count is still pending (null) are omitted; a null regressed
count draws only the recovered bar.
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
         row["recovered"], row["regressed"]) for row in SOURCE["results"]
        if row["recovered"] is not None]

# ---- Figure: recovered vs regressed (main text, full width) ----------------
fig, ax = plt.subplots(figsize=(6.3, 2.75))
for i, (b, m, _, _, rec, reg) in enumerate(DATA):
    ax.bar(i, rec, color=C_REC, width=0.62, zorder=2, edgecolor="white")
    if reg is None:
        ax.text(i, rec + 1.3, f"+{rec}", ha="center", fontsize=7, color=C_REC)
        continue
    ax.bar(i, -reg, color=C_REG, width=0.62, zorder=2)
    ax.scatter([i], [rec - reg], marker="D", s=22, color="black", zorder=3)
    if rec:
        ax.text(i, rec + (3.0 if reg == 0 else 1.3), f"+{rec}", ha="center", fontsize=7, color=C_REC)
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

for script in ("make_architecture_v3.py", "make_metric_figure.py", "make_transfer_figure.py"):
    runpy.run_path(str(ROOT / "_dl" / script), run_name="__main__")
