"""Illustration of recovered / regressed / net / churn for Section 3.2 -> Paper_COLING/figures/fig_metric.*"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

OUT = Path(__file__).resolve().parent.parent / "Paper_COLING" / "figures"
plt.rcParams.update({"font.family": ["Segoe UI", "Arial", "DejaVu Sans"], "mathtext.fontset": "custom",
                     "mathtext.rm": "Segoe UI", "mathtext.it": "Segoe UI:italic", "mathtext.bf": "Segoe UI:bold",
                     "pdf.fonttype": 42, "savefig.dpi": 300})
fig = plt.figure(figsize=(3.2, 2.55))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 108)
ax.set_ylim(0, 85)
ax.axis("off")

INK, GREY = "#22344A", "#55677A"
OK_F, OK_E = "#D6E8F8", "#4A90C8"
BAD_F, BAD_E = "#FFFFFF", "#9AA5B1"
REC_F, REC_E = "#CFEBDA", "#2E9B5F"
REG_F, REG_E = "#FBDAD7", "#D9534F"

# (correct under p, correct under q) for ten items
items = [(1, 1), (1, 1), (0, 1), (0, 0), (1, 0), (1, 1), (0, 1), (0, 0), (1, 0), (0, 1)]
S, GAP, X0 = 7.0, 1.3, 23.0
YP, YQ = 62, 41


def square(x, y, ok, fill, edge):
    ax.add_patch(FancyBboxPatch((x, y), S, S, boxstyle="round,pad=0,rounding_size=1.2", fc=fill, ec=edge, lw=1.0, zorder=2))
    ax.text(x + S / 2, y + S / 2 - 0.2, "\u2713" if ok else "\u2717", ha="center", va="center", fontsize=6.5,
            color=edge if ok else "#8794A1", fontweight="bold", zorder=3)


ax.text(X0, 78.5, "ten test items", fontsize=5.4, color=GREY, ha="left", va="center", style="italic")
ax.text(1, YP + S / 2, "before\nprompt $p$", fontsize=5.8, color=INK, ha="left", va="center", fontweight="bold", linespacing=1.15)
ax.text(1, YQ + S / 2, "after\nprompt $q$", fontsize=5.8, color=INK, ha="left", va="center", fontweight="bold", linespacing=1.15)

for k, (a, b) in enumerate(items):
    x = X0 + k * (S + GAP)
    square(x, YP, a, *(OK_F, OK_E) if a else (BAD_F, BAD_E))
    if a == 0 and b == 1:
        fill, edge = REC_F, REC_E
    elif a == 1 and b == 0:
        fill, edge = REG_F, REG_E
    else:
        fill, edge = (OK_F, OK_E) if b else (BAD_F, BAD_E)
    square(x, YQ, b, fill, edge)
    if a != b:
        c = REC_E if b else REG_E
        ax.annotate("", xy=(x + S / 2, YQ + S + 0.6), xytext=(x + S / 2, YP - 0.6), zorder=4,
                    arrowprops=dict(arrowstyle="-|>", color=c, lw=1.0, shrinkA=0, shrinkB=0, mutation_scale=5))


def card(x0, x1, y0, y1, fill, edge, lines):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0,rounding_size=1.6", fc=fill, ec=edge, lw=1.0, zorder=1))
    for (txt, fs, w, dy, col) in lines:
        ax.text((x0 + x1) / 2, (y0 + y1) / 2 + dy, txt, fontsize=fs, ha="center", va="center", fontweight=w, color=col, zorder=3)


card(1, 53, 17, 34, REC_F, REC_E, [("$R$ = recovered = 3", 6.0, "bold", 3.2, INK),
                                    ("wrong under $p$, right under $q$", 4.9, "normal", -3.4, GREY)])
card(55, 107, 17, 34, REG_F, REG_E, [("$G$ = regressed = 2", 6.0, "bold", 3.2, INK),
                                      ("right under $p$, wrong under $q$", 4.9, "normal", -3.4, GREY)])
card(1, 107, 1, 14.5, "#EAF3FC", OK_E, [("net $N = R - G = +1$  (accuracy 50% \u2192 60%)      churn $C = R + G = 5$", 5.6, "bold", 0, INK)])

fig.savefig(OUT / "fig_metric.pdf", pad_inches=0)
fig.savefig(OUT / "fig_metric.png", pad_inches=0, dpi=220)
print("wrote fig_metric")
