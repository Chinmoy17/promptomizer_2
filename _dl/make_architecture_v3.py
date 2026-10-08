"""Reflective FDPO architecture figure (left-to-right, light blue / light green) -> Paper_COLING/figures/."""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon, Rectangle, Arc

OUT = Path(__file__).resolve().parent.parent / "Paper_COLING" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": ["Segoe UI", "Arial", "DejaVu Sans"],
    "mathtext.fontset": "custom", "mathtext.rm": "Segoe UI", "mathtext.it": "Segoe UI:italic",
    "mathtext.bf": "Segoe UI:bold", "pdf.fonttype": 42, "savefig.dpi": 300,
})
W, H = 7.4, 3.62
fig = plt.figure(figsize=(W, H))
ax = fig.add_axes([0, 0, 1, 1])
XMAX, YMAX = 148, 74
ax.set_xlim(0, XMAX)
ax.set_ylim(-1.5, YMAX)
ax.axis("off")
fig.canvas.draw()
R = fig.canvas.get_renderer()

BLUE = dict(fill="#EAF3FC", edge="#4A90C8", text="#1F5F99")
GREEN = dict(fill="#E8F6EE", edge="#4FA872", text="#1F7A4A")
DBLUE = dict(fill="#D6E8F8", edge="#4A90C8", text="#1F5F99")
DGREEN = dict(fill="#D3EFDF", edge="#4FA872", text="#1F7A4A")
SAND = dict(fill="#FDF1E3", edge="#D99A4E", text="#9A5B14")
LAV = dict(fill="#E8EEF8", edge="#6C86C0", text="#2C4A8A")
INK, GREY = "#22344A", "#55677A"


def text_w(t):
    bb = t.get_window_extent(R)
    inv = ax.transData.inverted()
    (x0, _), (x1, _) = inv.transform([(bb.x0, bb.y0), (bb.x1, bb.y1)])
    return x1 - x0


def put(x, y, s, fs, maxw=None, color=INK, weight="normal", ha="center", style="normal", z=6, ls=1.2, **kw):
    t = ax.text(x, y, s, fontsize=fs, color=color, fontweight=weight, ha=ha, va="center",
                style=style, zorder=z, linespacing=ls, **kw)
    if maxw:
        while text_w(t) > maxw and fs > 3.2:
            fs -= 0.1
            t.set_fontsize(fs)
    return t


def rbox(x0, x1, y0, y1, pal, lw=1.0, ls="-", r=1.6, z=1):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle=f"round,pad=0,rounding_size={r}",
                                fc=pal["fill"], ec=pal["edge"], lw=lw, ls=ls, zorder=z))


def arrow(p0, p1, color=INK, lw=1.1, ls="-", rad=0.0, ms=7):
    ax.annotate("", xy=p1, xytext=p0, zorder=7,
                arrowprops=dict(arrowstyle="-|>", color=color, lw=lw, ls=ls, shrinkA=0, shrinkB=0,
                                mutation_scale=ms, connectionstyle=f"arc3,rad={rad}"))


# ---- icons (all drawn in data units around (cx, cy), size ~ s) ------------------------------
def ic_doc(cx, cy, c, s=4.2):
    w, h = s * 0.78, s
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h, boxstyle="round,pad=0,rounding_size=0.5",
                                fc="white", ec=c, lw=0.9, zorder=8))
    for i, dy in enumerate((0.22, 0.0, -0.22)):
        ax.plot([cx - w * 0.3, cx + w * (0.3 if i < 2 else 0.1)], [cy + dy * s, cy + dy * s], color=c, lw=0.7, zorder=9)


def ic_db(cx, cy, c, s=4.2):
    w, h = s * 0.86, s
    ax.add_patch(Rectangle((cx - w / 2, cy - h * 0.34), w, h * 0.68, fc="white", ec="none", zorder=8))
    ax.plot([cx - w / 2] * 2, [cy - h * 0.34, cy + h * 0.34], color=c, lw=0.9, zorder=9)
    ax.plot([cx + w / 2] * 2, [cy - h * 0.34, cy + h * 0.34], color=c, lw=0.9, zorder=9)
    ax.add_patch(Ellipse((cx, cy + h * 0.34), w, h * 0.32, fc="white", ec=c, lw=0.9, zorder=9))
    ax.add_patch(Arc((cx, cy), w, h * 0.32 + h * 0.68, theta1=180, theta2=360, color=c, lw=0.9, zorder=9))
    ax.add_patch(Arc((cx, cy), w, h * 0.32, theta1=180, theta2=360, color=c, lw=0.7, zorder=9))


def ic_search(cx, cy, c, s=4.2):
    ax.add_patch(Circle((cx - s * 0.1, cy + s * 0.1), s * 0.3, fc="white", ec=c, lw=1.0, zorder=9))
    ax.plot([cx + s * 0.12, cx + s * 0.4], [cy - s * 0.12, cy - s * 0.4], color=c, lw=1.3, zorder=9,
            solid_capstyle="round")


def ic_llm(cx, cy, c, s=4.2):
    pts = [(cx - s * 0.32, cy - s * 0.22), (cx + s * 0.32, cy - s * 0.22), (cx, cy + s * 0.3)]
    for i in range(3):
        for j in range(i + 1, 3):
            ax.plot([pts[i][0], pts[j][0]], [pts[i][1], pts[j][1]], color=c, lw=0.8, zorder=8)
    for p in pts:
        ax.add_patch(Circle(p, s * 0.17, fc="white", ec=c, lw=0.9, zorder=9))


def ic_lock(cx, cy, c, s=4.2):
    ax.add_patch(Arc((cx, cy + s * 0.08), s * 0.46, s * 0.5, theta1=0, theta2=180, color=c, lw=1.0, zorder=8))
    ax.add_patch(FancyBboxPatch((cx - s * 0.34, cy - s * 0.4), s * 0.68, s * 0.5,
                                boxstyle="round,pad=0,rounding_size=0.4", fc=c, ec=c, lw=0.8, zorder=9))
    ax.add_patch(Circle((cx, cy - s * 0.15), s * 0.07, fc="white", ec="none", zorder=10))


def ic_trophy(cx, cy, c, s=4.2):
    ax.add_patch(Polygon([(cx - s * 0.3, cy + s * 0.38), (cx + s * 0.3, cy + s * 0.38),
                          (cx + s * 0.2, cy - s * 0.02), (cx - s * 0.2, cy - s * 0.02)],
                         fc="white", ec=c, lw=0.9, zorder=9))
    ax.plot([cx, cx], [cy - s * 0.02, cy - s * 0.24], color=c, lw=0.9, zorder=9)
    ax.plot([cx - s * 0.2, cx + s * 0.2], [cy - s * 0.3, cy - s * 0.3], color=c, lw=1.2, zorder=9)


def ic_bars(cx, cy, c, s=4.2):
    for dx, h in ((-0.26, 0.4), (0, 0.7), (0.26, 0.95)):
        ax.add_patch(Rectangle((cx + dx * s - s * 0.1, cy - s * 0.45), s * 0.2, h * s * 0.9, fc=c, ec="none", zorder=9))


def ic_loop(cx, cy, c, s=4.2):
    ax.add_patch(Arc((cx, cy), s * 0.7, s * 0.7, theta1=40, theta2=330, color=c, lw=1.1, zorder=9))
    arrow((cx + s * 0.25, cy + s * 0.3), (cx + s * 0.12, cy + s * 0.36), color=c, lw=0.9, ms=5)


def ic_check(cx, cy, s=3.0, c="#2E9B5F"):
    ax.add_patch(Circle((cx, cy), s * 0.5, fc=c, ec="none", zorder=9))
    ax.plot([cx - s * 0.22, cx - s * 0.04, cx + s * 0.26], [cy, cy - s * 0.2, cy + s * 0.2], color="white", lw=1.0,
            zorder=10, solid_capstyle="round")


def ic_cross(cx, cy, s=3.0, c="#D9534F"):
    ax.add_patch(Circle((cx, cy), s * 0.5, fc=c, ec="none", zorder=9))
    ax.plot([cx - s * 0.2, cx + s * 0.2], [cy - s * 0.2, cy + s * 0.2], color="white", lw=1.0, zorder=10)
    ax.plot([cx - s * 0.2, cx + s * 0.2], [cy + s * 0.2, cy - s * 0.2], color="white", lw=1.0, zorder=10)


def ic_dot(cx, cy, s=3.0, c="#9AA5B1"):
    ax.add_patch(Circle((cx, cy), s * 0.5, fc=c, ec="none", zorder=9))


# ---- building blocks ------------------------------------------------------------------------
def panel(x0, x1, y0, y1, n, title, pal, dashed=False, right_note=None):
    rbox(x0, x1, y0, y1, pal, lw=1.3, ls="--" if dashed else "-", r=2.4, z=0)
    cy = y1 - 4.2
    ax.add_patch(Circle((x0 + 4.0, cy), 2.5, fc=pal["edge"], ec="none", zorder=2))
    put(x0 + 4.0, cy, str(n), 6.6, color="white", weight="bold")
    put(x0 + 7.6, cy, title, 7.0, maxw=(x1 - x0) - 9, color=pal["text"], weight="bold", ha="left")
    if right_note:
        put(x1 - 2, cy, right_note, 6.0, color=pal["text"], ha="right", style="italic")


def card(x0, x1, y0, y1, pal, icon, head, sub="", icon_c=None, hfs=6.3, sfs=5.0, lw=1.0, icon_left=False):
    rbox(x0, x1, y0, y1, pal, lw=lw, z=1)
    cx, w = (x0 + x1) / 2, x1 - x0 - 2.4
    c = icon_c or pal["edge"]
    if icon_left:
        icon(cx_ := x0 + 4.2, (y0 + y1) / 2, c) if False else None
    if icon:
        icon(cx, y1 - 5.0, c)
    hy = y1 - 10.8 if icon else (y0 + y1) / 2 + 2
    put(cx, hy, head, hfs, maxw=w, weight="bold")
    if sub:
        put(cx, y0 + (y1 - y0 - (11.5 if icon else 5)) / 2 + 1.0, sub, sfs, maxw=w, color=GREY, ls=1.25)


def item(x0, x1, y0, y1, icon, head, sub, pal=DBLUE):
    rbox(x0, x1, y0, y1, pal, lw=1.0, z=1)
    cy = (y0 + y1) / 2
    icon(x0 + 4.6, cy, pal["edge"], 4.6)
    tx, w = x0 + 8.8, (x1 - x0) - 10.2
    put(tx, cy + 2.6, head, 6.2, maxw=w, weight="bold", ha="left")
    put(tx, cy - 2.6, sub, 5.0, maxw=w, color=GREY, ha="left", ls=1.2)


Y0, Y1 = 12, 72

# 1 Inputs ------------------------------------------------------------------------------------
panel(0.5, 36, Y0, Y1, 1, "Inputs", BLUE)
item(2.5, 23.5, 51, 65, ic_doc, "Seed prompt $p_0$", "five fixed sections")
item(2.5, 23.5, 33, 47, ic_db, "Mining set $M$", "failures shown\nto the optimizer")
item(2.5, 23.5, 15, 29, ic_db, "Validation set $V$", "selects best round")
rbox(25.2, 34.3, 15, 65, dict(fill="#CFE3F5", edge="#1F5F99"), lw=1.5)
ic_lock(29.75, 56, "#1F5F99", 6.0)
put(29.75, 47.0, "Sealed", 6.3, maxw=7.6, weight="bold")
put(29.75, 42.8, "test set $T$", 6.3, maxw=7.6, weight="bold")
put(29.75, 31.0, "used only\nfor baseline\nand final", 5.0, maxw=7.6, color=GREY, ls=1.3)

# 2 Baseline ----------------------------------------------------------------------------------
panel(38.5, 58, Y0, Y1, 2, "Baseline", GREEN)
card(40.5, 56, 41, 62, DGREEN, ic_search, "Solver LLM", "scores $p_0$\non $M$ and $V$")
card(40.5, 56, 17, 37, DGREEN, ic_bars, "Baseline", "scores\n($M$, $V$)")
arrow((48.25, 41), (48.25, 37), color=GREEN["edge"])

# 3 Loop container ----------------------------------------------------------------------------
panel(60.5, 112, Y0, Y1, 3, "Iterative optimization loop", DBLUE, right_note="$t = 1 \\ldots 3$")
card(62.5, 80, 41, 62, SAND, ic_llm, "Optimizer LLM", "writes a new\nprompt $p_t$", icon_c=SAND["edge"], lw=1.5)
card(83, 99, 41, 62, DGREEN, ic_search, "Solver LLM", "scores $p_t$\non $M$ and $V$")
card(101.5, 110, 41, 62, LAV, ic_bars, "Validation", "saved each\nround", hfs=5.8, sfs=4.7)
arrow((80, 51.5), (83, 51.5))
arrow((99, 51.5), (101.5, 51.5))
# reflection
rbox(70, 101, 17, 36, dict(fill="#FFF8EF", edge="#D99A4E"), lw=1.1)
put(85.5, 32.2, "Item-level recovery / regression", 6.2, maxw=28, weight="bold", color=SAND["text"])
for x, icn, lab in ((75.5, ic_check, "recovered"), (86.5, ic_cross, "regressed"), (96.5, ic_dot, "same")):
    icn(x - 3.2 if lab != "same" else x - 2.4, 26.6, 3.0)
    put(x - 0.6 if lab != "same" else x - 0.2, 26.6, lab, 5.2, color=GREY, ha="left" if True else "center")
put(85.5, 21.2, "on $M$ and $V$, shown before the next rewrite", 4.9, maxw=28, color=GREY, style="italic")
arrow((91, 41), (91, 36), color="#B07A2C")
arrow((76, 36), (70.8, 41), color="#B07A2C", rad=-0.3)
# loop-back bracket
xs0, xs1, yb = 71.2, 105.7, 64.6
ax.plot([xs1, xs1, xs0], [62, yb, yb], color=INK, lw=0.9, zorder=7)
arrow((xs0, yb), (xs0, 62.2), lw=0.9, ms=6)
t = put((xs0 + xs1) / 2, yb, "repeat; every round is committed", 5.0, color=GREY, style="italic", z=9)
t.set_bbox(dict(fc=DBLUE["fill"], ec="none", pad=1.3))
put(85.5, 14.4, "validation flips also feed the next rewrite", 4.8, maxw=40, color=GREY, style="italic")

# 4 Select ------------------------------------------------------------------------------------
panel(114.5, 130, Y0, Y1, 4, "Select", GREEN)
card(116.5, 128, 41, 62, DGREEN, ic_trophy, "Best round", "highest\nvalidation acc.")
card(116.5, 128, 17, 37, DGREEN, ic_doc, "Final prompt", "$p^*$ (ties: mining\naccuracy)")
arrow((122.25, 41), (122.25, 37), color=GREEN["edge"])

# 5 Sealed test -------------------------------------------------------------------------------
panel(132.5, 147.3, Y0, Y1, 5, "Test", GREEN, dashed=True)
card(134.5, 145.3, 41, 62, DGREEN, ic_lock, "Test set $T$", "scored\ntwice only", icon_c="#1F5F99", hfs=6.0, sfs=4.9)
card(134.5, 145.3, 17, 37, DGREEN, ic_bars, "Test scores", "$p_0$ and $p^*$", hfs=6.0, sfs=4.9)
arrow((139.9, 41), (139.9, 37), color=GREEN["edge"])

# main flow ----------------------------------------------------------------------------------
for a, b in ((36, 38.5), (58, 60.5), (112, 114.5), (130, 132.5)):
    arrow((a, 38.5 + 12.5 if False else 51.5), (b, 51.5), lw=1.4)

# sealed route --------------------------------------------------------------------------------
ax.plot([29.75, 29.75, 139.9], [15, 9.4, 9.4], color="#1F5F99", lw=1.0, ls=(0, (4, 2.2)), zorder=4)
ax.plot([139.9, 139.9], [9.4, 11.0], color="#1F5F99", lw=1.0, ls=(0, (4, 2.2)), zorder=4)
arrow((139.9, 10.0), (139.9, 12), color="#1F5F99", lw=1.0)
put(85, 6.6, "$T$ is measured with $p_0$ and $p^*$ only; it never influences choosing, editing, or stopping",
    5.4, color="#1F5F99", style="italic")

# legend --------------------------------------------------------------------------------------
lx = 4.0
for icn, lab, adv in ((ic_db, "Dataset / split", 20), (ic_llm, "LLM / model", 18), (ic_search, "Evaluation", 16.5),
                      (ic_loop, "Iteration / loop", 20), (ic_doc, "Prompt / text", 18.5), (ic_lock, "Sealed / protected", 21)):
    icn(lx, 2.4, "#5C7C99", 3.4)
    put(lx + 3.0, 2.4, lab, 5.2, color=GREY, ha="left")
    lx += adv
ic_check(lx + 1, 2.4, 2.6)
ic_cross(lx + 4.4, 2.4, 2.6)
put(lx + 7.2, 2.4, "Recovered / regressed", 5.2, color=GREY, ha="left")

fig.savefig(OUT / "fig_architecture.pdf", pad_inches=0)
fig.savefig(OUT / "fig_architecture.png", pad_inches=0, dpi=220)
print("wrote fig_architecture")
