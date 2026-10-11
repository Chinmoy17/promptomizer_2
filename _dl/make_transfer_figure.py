"""Matched non-AIME outcome funnel and paired accuracy means for the paper."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Paper_COLING" / "figures"
plt.rcParams.update({"font.family": ["Times New Roman", "DejaVu Serif"], "pdf.fonttype": 42, "savefig.dpi": 300,
                     "hatch.linewidth": 0.5})

BLUE, BLUE_M, BLUE_L = "#3E86C5", "#9CC4E8", "#D6E8F8"
GREEN, GREEN_L = "#2E9B5F", "#CFEBDA"
RED, RED_L = "#D9534F", "#FBDAD7"
INK, GREY = "#22344A", "#6B7C8E"

rows = json.loads((ROOT / "Paper_COLING/Artifacts/val_test_gap.json").read_text("utf-8"))
source = json.loads((ROOT / "Paper_COLING/Artifacts/reported_results.json").read_text("utf-8"))
rows = [row for row in rows if not any(row["run"].startswith(prefix)
        for prefix in source["validation_excluded_prefixes"])]
for row in rows:
    row["val_gain_pp"] = 100 * (row["val_best"] - row["val_base"])
    row["test_delta_pp"] = 100 * (row["test_final"] - row["test_base"])
shipped = [r for r in rows if r["shipped"]]
up = [r for r in shipped if r["val_gain_pp"] > 0]
fell = [r for r in up if r["test_delta_pp"] < 0]
assert (len(rows), len(shipped), len(up), len(fell)) == (18, 16, 11, 3)


def mean(group, key):
    return sum(g[key] for g in group) / len(group)


groups = [("Non-MMLU", [r for r in shipped if not r["run"].startswith("MMLU")]),
          ("MMLU", [r for r in shipped if r["run"].startswith("MMLU")]),
          ("All eligible", shipped)]

fig = plt.figure(figsize=(3.15, 3.45))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(-3, 112)
ax.axis("off")


def bar(x0, x1, y0, y1, fill, edge):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=1.6",
                                fc=fill, ec=edge, lw=0.9, zorder=2))


def txt(x, y, s, fs, color=INK, weight="normal", ha="center", style="normal", z=5):
    ax.text(x, y, s, fontsize=fs, color=color, fontweight=weight, ha=ha, va="center", style=style, zorder=z,
            linespacing=1.15)


# ---- panel A: funnel -------------------------------------------------------------------------
txt(2, 108, "A", 7.5, BLUE, "bold", "left")
txt(7, 108, "Validation/test outcome counts", 6.6, INK, "bold", "left")
CX, W = 37, 68
rowsA = [(94, 18, W, "18 matched non-AIME records", BLUE_L, BLUE),
         (80, 16, W * 16 / 18, "16 shipped an optimized prompt", BLUE_L, BLUE),
         (66, 11, W * 11 / 18, "11 raised validation accuracy", BLUE_M, BLUE)]
for y, n, w, label, fc, ec in rowsA:
    bar(CX - w / 2, CX + w / 2, y - 5, y + 5, fc, ec)
    txt(CX, y, label, 5.8, INK, "bold")
for (y0, y1), note in (((89, 85), "2 kept the\nseed prompt"), ((75, 71), "5 did not raise\nvalidation")):
    ax.plot([CX, CX], [y0, y1 + 0.2], color=BLUE, lw=0.8, zorder=1)
for y, note in ((87, "2 kept the\nseed prompt"), ((73), "5 did not raise\nvalidation")):
    txt(76, y, note, 5.0, GREY, ha="left", style="italic")
wu = W * 8 / 18
wf = W * 3 / 18
x0 = CX - W * 11 / 18 / 2
bar(x0, x0 + wu - 0.6, 46, 58, GREEN_L, GREEN)
bar(x0 + wu + 0.6, x0 + wu + wf, 46, 58, RED_L, RED)
txt(x0 + wu / 2, 54.2, "8", 8, GREEN, "bold")
txt(x0 + wu / 2, 49.4, "test went up", 5.0, INK)
txt(x0 + wu + wf / 2 + 0.3, 54.2, "3", 8, RED, "bold")
txt(x0 + wu + wf / 2 + 0.3, 49.4, "test fell", 5.0, INK)
ax.plot([CX, CX], [60.8, 59.0], color=BLUE, lw=0.8, zorder=1)
txt(76, 52, "IFBench,\nHearsay, MMLU\nsecurity", 5.0, GREY, ha="left", style="italic")
ax.plot([x0 + wu + 1, 75.5], [52, 52], color="#C9D3DD", lw=0.5, zorder=1)

# ---- panel B: gain budget ---------------------------------------------------------------------
txt(2, 38, "B", 7.5, BLUE, "bold", "left")
txt(7, 38, "Mean accuracy changes (percentage points)", 6.1, INK, "bold", "left")
SX, SC = 29, 3.0
for tick in (0, 5, 10, 15, 20):
    ax.plot([SX + tick * SC, SX + tick * SC], [5, 33.5], color="#E3EAF1", lw=0.5, zorder=0)
    txt(SX + tick * SC, 3.8, str(tick), 5.0, GREY)
for i, (name, grp) in enumerate(groups):
    y = 30 - i * 10.5
    v, t = mean(grp, "val_gain_pp"), mean(grp, "test_delta_pp")
    txt(2, y + 0.4, name, 5.4, INK, "bold", "left")
    txt(2, y - 3.6, f"{len(grp)} runs", 4.8, GREY, "normal", "left")
    ax.plot([SX + t * SC, SX + v * SC], [y, y], color="#AEBACA", lw=1.4, zorder=1)
    ax.scatter([SX + v * SC], [y], color=BLUE, s=25, zorder=3)
    ax.scatter([SX + t * SC], [y], color=GREEN, marker="D", s=25, zorder=3)
    txt(SX + v * SC, y + 3.2, f"{v:+.1f}", 5.5, BLUE, "bold")
    txt(SX + t * SC, y - 3.2, f"{t:+.1f}", 5.5, GREEN, "bold")
ax.scatter([SX], [-0.1], color=BLUE, s=20)
txt(SX + 3, -0.1, "validation", 5.2, GREY, ha="left")
ax.scatter([SX + 33], [-0.1], color=GREEN, marker="D", s=20)
txt(SX + 36, -0.1, "test", 5.2, GREY, ha="left")

fig.savefig(OUT / "fig_val_vs_test.pdf", bbox_inches="tight")
fig.savefig(OUT / "fig_val_vs_test.png", dpi=300, bbox_inches="tight")
print("wrote fig_val_vs_test", [(n, round(mean(g, 'val_gain_pp'), 1), round(mean(g, 'test_delta_pp'), 1)) for n, g in groups])
