"""Validation gain vs sealed-test change as a paired-dot (dumbbell) chart -> Paper_COLING/figures/fig_val_vs_test.*"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "Paper_COLING" / "figures"
plt.rcParams.update({"font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "pdf.fonttype": 42, "savefig.dpi": 300})

BLUE, BLUE_L = "#3E86C5", "#D6E8F8"
GREEN, GREEN_L = "#2E9B5F", "#D3EFDF"
RED, RED_L = "#D9534F", "#FBE3E1"
INK, GREY = "#22344A", "#6B7C8E"

rows = [r for r in json.loads((ROOT / "Paper_COLING/Artifacts/val_test_gap.json").read_text("utf-8")) if r["shipped"]]

SUBJ = {"college_mathematics": "math", "computer_security": "security", "econometrics": "econ",
        "high_school_biology": "biology", "philosophy": "philosophy", "professional_law": "law"}
BENCH = {"AIME": "AIME", "PUPA": "PUPA", "IFBench": "IFBench", "Hearsay": "Hearsay"}


def label(run):
    name, model = run.split(" / ")
    m = "4o" if model == "4o-mini" else "4.1"
    if name.startswith("MMLU-"):
        return f"MMLU {SUBJ[name[5:]]} \u00b7 {m}"
    return f"{BENCH[name]} \u00b7 {m}"


def entry(r):
    return dict(lab=label(r["run"]), v=r["val_gain_pp"], t=r["test_delta_pp"], mmlu=r["run"].startswith("MMLU"))


items = [entry(r) for r in rows]
non = sorted([i for i in items if not i["mmlu"]], key=lambda d: -d["v"])
mm = sorted([i for i in items if i["mmlu"]], key=lambda d: -d["v"])


def mean(group, k):
    return sum(g[k] for g in group) / len(group)


layout = [("group", f"Non-MMLU runs ({len(non)})")] + [("run", g) for g in non] + \
         [("mean", dict(lab="mean", v=mean(non, "v"), t=mean(non, "t")))] + \
         [("group", f"MMLU subjects ({len(mm)})")] + [("run", g) for g in mm] + \
         [("mean", dict(lab="mean", v=mean(mm, "v"), t=mean(mm, "t")))]

n = len(layout)
fig, ax = plt.subplots(figsize=(3.15, 4.0))
ax.set_xlim(-8, 29)
ax.set_ylim(n - 0.4, -1.4)
ax.axvline(0, color=GREY, lw=0.7, zorder=1)
for x in (-5, 5, 10, 15, 20, 25):
    ax.axvline(x, color="#E3EAF1", lw=0.5, zorder=0)

for y, (kind, g) in enumerate(layout):
    if kind == "group":
        ax.text(-7.8, y, g, fontsize=6.0, fontweight="bold", color=BLUE, va="center", ha="left")
        ax.plot([-8, 29], [y + 0.42, y + 0.42], color=BLUE_L, lw=0.8, zorder=0)
        continue
    fell = kind == "run" and g["v"] > 0 and g["t"] < 0
    if fell:
        ax.add_patch(Rectangle((-8, y - 0.5), 37, 1.0, fc=RED_L, ec="none", zorder=0))
    tcol = GREEN if g["t"] >= 0 else RED
    if kind == "run":
        ax.plot([g["v"], g["t"]], [y, y], color="#B7C6D6", lw=1.3, zorder=2, solid_capstyle="round")
        ax.scatter([g["v"]], [y], s=15, color=BLUE, zorder=3, edgecolor="white", linewidth=0.4)
        ax.scatter([g["t"]], [y], s=15, color=tcol, zorder=3, edgecolor="white", linewidth=0.4)
    else:
        ax.plot([g["v"], g["t"]], [y, y], color="#B7C6D6", lw=1.3, zorder=2)
        ax.scatter([g["v"]], [y], s=34, marker="D", color=BLUE, zorder=3, edgecolor="white", linewidth=0.5)
        ax.scatter([g["t"]], [y], s=34, marker="D", color=GREEN, zorder=3, edgecolor="white", linewidth=0.5)
        ax.text(29, y, f"val {g['v']:+.1f}   test {g['t']:+.1f}", fontsize=5.4, color=INK, fontweight="bold",
                ha="right", va="bottom", zorder=4)

ax.set_yticks([y for y, (k, _) in enumerate(layout) if k != "group"])
ax.set_yticklabels([g["lab"] if k == "run" else "mean" for k, g in layout if k != "group"], fontsize=5.4, color=INK)
for lbl, (k, _) in zip(ax.get_yticklabels(), [x for x in layout if x[0] != "group"]):
    if k == "mean":
        lbl.set_fontweight("bold")
ax.tick_params(axis="y", length=0, pad=2)
ax.tick_params(axis="x", labelsize=5.8, colors=GREY, length=2)
ax.set_xlabel("percentage points (seed to shipped prompt)", fontsize=6.2, color=INK, labelpad=2)
for s in ("top", "right", "left"):
    ax.spines[s].set_visible(False)
ax.spines["bottom"].set_color(GREY)

handles = [Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=4.5, label="validation gain"),
           Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=4.5, label="test change, up"),
           Line2D([0], [0], marker="o", color="w", markerfacecolor=RED, markersize=4.5, label="test change, down"),
           Rectangle((0, 0), 1, 1, fc=RED_L, ec="none", label="validation up, test down")]
fig.legend(handles=handles, loc="upper center", ncol=2, frameon=False, fontsize=5.6, handletextpad=0.3,
           columnspacing=1.0, bbox_to_anchor=(0.55, 1.0))
fig.subplots_adjust(left=0.27, right=0.985, top=0.9, bottom=0.075)
fig.savefig(OUT / "fig_val_vs_test.pdf")
fig.savefig(OUT / "fig_val_vs_test.png", dpi=220)
print("wrote fig_val_vs_test")
