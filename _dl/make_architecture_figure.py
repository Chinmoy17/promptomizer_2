"""Compact, wide architecture figure for Reflective FDPO -> Paper_COLING/figures/.
Same content as the Mermaid spec (4 layers), laid out to fit a two-column-wide
figure*. Replace with the hand-drawn draw.io export when ready; keep the
filename fig_architecture.pdf and paper.tex needs no change.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "Paper_COLING" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({"font.family": "serif", "savefig.dpi": 300})
fig, ax = plt.subplots(figsize=(6.3, 4.3))
ax.set_xlim(0, 100)
ax.set_ylim(0, 70)
ax.axis("off")

COL = {"data": ("#dbeafe", "#2563eb"), "llm": ("#fde68a", "#b45309"),
       "store": ("#dcfce7", "#15803d"), "final": ("#fecaca", "#b91c1c")}
BAND = {"b1": ("#eff6ff", "#2563eb"), "b2": ("#f8fafc", "#64748b"),
        "b3": ("#fffbeb", "#b45309"), "b4": ("#fef2f2", "#b91c1c")}


def band(y0, y1, key, title):
    f, e = BAND[key]
    ax.add_patch(FancyBboxPatch((2, y0), 78, y1 - y0, boxstyle="round,pad=0,rounding_size=1.2",
                                fc=f, ec=e, lw=0.9, zorder=0))
    ax.text(3.6, y1 - 1.9, title, fontsize=5.8, fontweight="bold", color=e, va="center", zorder=1)


def box(x0, x1, y0, y1, text, kind, bold=False, fs=6.0):
    f, e = COL[kind]
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=0.9",
                                fc=f, ec=e, lw=1.6 if bold else 0.9, zorder=2))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, text, ha="center", va="center", fontsize=fs,
            fontweight="bold" if bold else "normal", zorder=3, linespacing=1.15)


def arrow(p0, p1, color="#333333", lw=0.9, style="-|>", ls="-"):
    ax.annotate("", xy=p1, xytext=p0, zorder=4,
                arrowprops=dict(arrowstyle=style, color=color, lw=lw, ls=ls,
                                shrinkA=0, shrinkB=0, mutation_scale=7))


def label(x, y, t, color="#333333", ha="left", fs=5.5, rot=0):
    ax.text(x, y, t, fontsize=fs, color=color, ha=ha, va="center", rotation=rot,
            style="italic", zorder=5)


# ---- bands -----------------------------------------------------------------
band(56, 70, "b1", "1  INPUTS")
band(39, 52, "b2", "2  BASELINE")
band(17, 35, "b3", "3  REFLECTIVE ROUND LOOP  (rounds 1 to 3)")
band(0, 13, "b4", "4  SELECT AND REPORT")

# ---- band 1 ----------------------------------------------------------------
box(4, 24, 57.8, 66, "Seed prompt $p_0$\n(five fixed sections)", "data")
box(28, 51, 57.8, 66, "Mining set $M$\nfailures shown to\nthe optimizer", "data")
box(55, 78, 57.8, 66, "Validation set $V$\nselects best round;\nflips shown to optimizer", "data", fs=5.6)

# ---- band 2 ----------------------------------------------------------------
box(4, 27, 40.8, 48, "Solver LLM scores\nthe seed prompt $p_0$\non $M$ and $V$", "llm")
box(31, 53, 40.8, 48, "Round 0 saved\n$(p_0, s_0, v_0)$", "store")
box(56, 78, 40.8, 48, "Baseline test score\nof $p_0$ on $T$\n(measured, not used)", "final", fs=5.6)
arrow((27, 44.4), (31, 44.4))

# ---- band 3 ----------------------------------------------------------------
xs = [(4.5, 19.5), (22.5, 37.5), (40.5, 55.5), (58.5, 73.5)]
box(*xs[0], 21.8, 31, "Reflect\nwhat did the last\nedit recover and\nregress on $M$, $V$?", "store", fs=5.4)
box(*xs[1], 21.8, 31, "Optimizer LLM\nwrites a new\nprompt $p_t$", "llm", bold=True, fs=5.8)
box(*xs[2], 21.8, 31, "Solver LLM\nscores $p_t$\non $M$ and $V$", "llm")
box(*xs[3], 21.8, 31, "Save round $t$\nalways kept,\nno gate", "store")
for a, b in zip(xs[:-1], xs[1:]):
    arrow((a[1], 26.4), (b[0], 26.4))
ax.plot([xs[3][0] + 7, xs[3][0] + 7], [21.8, 19.4], color="#333333", lw=0.9, zorder=4)
ax.plot([xs[3][0] + 7, xs[0][0] + 7], [19.4, 19.4], color="#333333", lw=0.9, zorder=4)
arrow((xs[0][0] + 7, 19.4), (xs[0][0] + 7, 21.8))
label(38.5, 18.2, "loop back for rounds 2 and 3", ha="center")
label(78.5, 33.4, "t = 1: no reflection yet", ha="right", fs=5.0)

# ---- band 4 ----------------------------------------------------------------
box(4, 27, 1.8, 9.2, "Pick best round $t^*$\nby validation accuracy", "store", fs=5.8)
box(32, 56, 1.8, 9.2, "Evaluate shipped prompt\n$p^*$ on $T$ (final use)", "final", bold=True, fs=5.8)
box(61, 78, 1.8, 9.2, "Final result\nbaseline vs. shipped,\nrecovered / regressed", "final", fs=5.2)
arrow((27, 5.5), (32, 5.5))
arrow((56, 5.5), (61, 5.5))

# ---- sealed test set + inter-band arrows -----------------------------------
box(83, 98.5, 57.8, 66, "Sealed\ntest set $T$", "final", bold=True)
arrow((40, 56), (40, 52))
label(41.5, 54, "seed prompt, $M$, $V$")
arrow((40, 39), (40, 35))
label(41.5, 37, "round-0 scores; start round 1")
arrow((16, 17), (16, 13))
label(17.5, 15, "after round 3: all saved rounds")
# T is only ever measured: once with p0 (band 2), once with p* (band 4)
ax.plot([90.7, 90.7], [57.8, 15.0], color="#b91c1c", lw=1.6, zorder=4)
arrow((90.7, 44.4), (78, 44.4), color="#b91c1c", lw=1.6)
ax.plot([90.7, 44], [15.0, 15.0], color="#b91c1c", lw=1.6, zorder=4)
arrow((44, 15.0), (44, 9.2), color="#b91c1c", lw=1.6)
label(92.4, 30, "measured only: never used to choose, edit, or stop", color="#b91c1c", ha="center", rot=90, fs=5.0)
label(66, 13.6, "second and last use", color="#b91c1c", ha="center")

fig.savefig(OUT / "fig_architecture.pdf", bbox_inches="tight")
fig.savefig(OUT / "fig_architecture.png", bbox_inches="tight")
print("wrote fig_architecture")
