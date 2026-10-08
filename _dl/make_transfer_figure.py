"""Validation-to-test transfer as a funnel plus a 'gain budget' bar -> Paper_COLING/figures/fig_val_vs_test.*"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Paper_COLING" / "figures"
plt.rcParams.update({"font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "pdf.fonttype": 42, "savefig.dpi": 300,
                     "hatch.linewidth": 0.5})

BLUE, BLUE_M, BLUE_L = "#3E86C5", "#9CC4E8", "#D6E8F8"
GREEN, GREEN_L = "#2E9B5F", "#CFEBDA"
RED, RED_L = "#D9534F", "#FBDAD7"
INK, GREY = "#22344A", "#6B7C8E"

rows = json.loads((ROOT / "Paper_COLING/Artifacts/val_test_gap.json").read_text("utf-8"))
shipped = [r for r in rows if r["shipped"]]
up = [r for r in shipped if r["val_gain_pp"] > 0]
fell = [r for r in up if r["test_delta_pp"] < 0]
assert (len(rows), len(shipped), len(up), len(fell)) == (20, 17, 12, 4)


def mean(group, key):
    return sum(g[key] for g in group) / len(group)


groups = [("Non-MMLU", [r for r in shipped if not r["run"].startswith("MMLU")]),
          ("MMLU", [r for r in shipped if r["run"].startswith("MMLU")]),
          ("All shipped", shipped)]

fig = plt.figure(figsize=(3.15, 3.45))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 100)
ax.set_ylim(0, 112)
ax.axis("off")


def bar(x0, x1, y0, y1, fill, edge):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=1.6",
                                fc=fill, ec=edge, lw=0.9, zorder=2))


def txt(x, y, s, fs, color=INK, weight="normal", ha="center", style="normal", z=5):
    ax.text(x, y, s, fontsize=fs, color=color, fontweight=weight, ha=ha, va="center", style=style, zorder=z,
            linespacing=1.15)


# ---- panel A: funnel -------------------------------------------------------------------------
txt(2, 108, "A", 7.5, BLUE, "bold", "left")
txt(7, 108, "How many runs carried their validation gain to the test set", 5.6, INK, "bold", "left")
CX, W = 37, 68
rowsA = [(94, 20, W, "20 optimization runs", BLUE_L, BLUE),
         (80, 17, W * 17 / 20, "17 shipped an optimized prompt", BLUE_L, BLUE),
         (66, 12, W * 12 / 20, "12 raised validation accuracy", BLUE_M, BLUE)]
for y, n, w, label, fc, ec in rowsA:
    bar(CX - w / 2, CX + w / 2, y - 5, y + 5, fc, ec)
    txt(CX, y, label, 5.8, INK, "bold")
for (y0, y1), note in (((89, 85), "3 kept the\nseed prompt"), ((75, 71), "5 did not raise\nvalidation")):
    ax.plot([CX, CX], [y0, y1 + 0.2], color=BLUE, lw=0.8, zorder=1)
for y, note in ((87, "3 kept the\nseed prompt"), ((73), "5 did not raise\nvalidation")):
    txt(76, y, note, 5.0, GREY, ha="left", style="italic")
wu = W * 8 / 20
wf = W * 4 / 20
x0 = CX - W * 12 / 20 / 2
bar(x0, x0 + wu - 0.6, 46, 58, GREEN_L, GREEN)
bar(x0 + wu + 0.6, x0 + wu + wf, 46, 58, RED_L, RED)
txt(x0 + wu / 2, 54.2, "8", 8, GREEN, "bold")
txt(x0 + wu / 2, 49.4, "test went up", 5.0, INK)
txt(x0 + wu + wf / 2 + 0.3, 54.2, "4", 8, RED, "bold")
txt(x0 + wu + wf / 2 + 0.3, 49.4, "test fell", 5.0, INK)
ax.plot([CX, CX], [60.8, 59.0], color=BLUE, lw=0.8, zorder=1)
txt(76, 52, "AIME, IFBench,\nHearsay, MMLU\nsecurity", 4.8, GREY, ha="left", style="italic")
ax.plot([x0 + wu + 1, 75.5], [52, 52], color="#C9D3DD", lw=0.5, zorder=1)

# ---- panel B: gain budget ---------------------------------------------------------------------
txt(2, 38, "B", 7.5, BLUE, "bold", "left")
txt(7, 38, "How much of the validation gain carried over (mean, points)", 5.6, INK, "bold", "left")
SX, SC = 28, 3.5
for i, (name, grp) in enumerate(groups):
    y = 30 - i * 10.5
    v, t = mean(grp, "val_gain_pp"), mean(grp, "test_delta_pp")
    carried = max(min(t, v), 0)
    txt(2, y + 0.4, name, 5.4, INK, "bold", "left")
    txt(2, y - 3.6, f"{len(grp)} runs", 4.8, GREY, "normal", "left")
    ax.add_patch(Rectangle((SX, y - 3.3), carried * SC, 6.6, fc=GREEN, ec="none", zorder=2))
    ax.add_patch(Rectangle((SX + carried * SC, y - 3.3), (v - carried) * SC, 6.6, fc=BLUE_L, ec=BLUE, lw=0.6,
                           hatch="////", zorder=2))
    txt(SX + carried * SC / 2, y + 0.2, f"{t:.1f}", 5.4, "white", "bold")
    txt(SX + v * SC + 1.5, y + 0.2, f"of {v:.1f}", 5.4, INK, "bold", "left")
ax.add_patch(Rectangle((SX, 0.8), 5, 2.6, fc=GREEN, ec="none"))
txt(SX + 6.5, 2.1, "reached the test set", 4.9, GREY, ha="left")
ax.add_patch(Rectangle((SX + 33, 0.8), 5, 2.6, fc=BLUE_L, ec=BLUE, lw=0.5, hatch="////"))
txt(SX + 39.5, 2.1, "did not", 4.9, GREY, ha="left")

fig.savefig(OUT / "fig_val_vs_test.pdf")
fig.savefig(OUT / "fig_val_vs_test.png", dpi=220)
print("wrote fig_val_vs_test", [(n, round(mean(g, 'val_gain_pp'), 1), round(mean(g, 'test_delta_pp'), 1)) for n, g in groups])
