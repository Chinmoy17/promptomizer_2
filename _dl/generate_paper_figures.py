"""Generate paper-ready figures from RESULTS.md / comparison_analysis.md
numbers (hardcoded here, matching those two files exactly -- the project's
established convention, see _dl/extract_confusion.py for precedent).

Outputs PNG (300dpi) + PDF (vector, for \\includegraphics) into
Paper_COLING/Artifacts/figures/.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent.parent / "Paper_COLING" / "Artifacts" / "figures"
OUT.mkdir(parents=True, exist_ok=True)

C_4OMINI = "#4C72B0"   # steel blue
C_41MINI = "#DD8452"   # muted orange
C_RECOV = "#2E7D32"    # green
C_REGR = "#C62828"     # red
C_GEPA = "#9E9E9E"     # neutral gray, de-emphasized (not the paper's own method)

plt.rcParams.update({
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "legend.fontsize": 9,
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
})


def save(fig, name: str) -> None:
    fig.savefig(OUT / f"{name}.png", bbox_inches="tight")
    fig.savefig(OUT / f"{name}.pdf", bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {name}.png / {name}.pdf")


# ---------------------------------------------------------------------------
# Figure 1: baseline -> final accuracy, dumbbell plot, all 5 benchmarks x 2 models
# ---------------------------------------------------------------------------
results = [
    ("AIME",             "GPT-4o-mini",  13.3, 10.0),
    ("AIME",             "GPT-4.1 Mini", 46.7, 53.3),
    ("PUPA (composite)", "GPT-4o-mini",  68.5, 79.9),
    ("PUPA (composite)", "GPT-4.1 Mini", 68.2, 80.7),
    ("IFBench",          "GPT-4o-mini",  47.6, 45.2),
    ("IFBench",          "GPT-4.1 Mini", 42.9, 66.7),
    ("Hearsay",          "GPT-4o-mini",  71.4, 69.4),
    ("Hearsay",          "GPT-4.1 Mini", 71.4, 73.5),
    ("MMLU (macro)",     "GPT-4o-mini",  75.1, 77.2),
    ("MMLU (macro)",     "GPT-4.1 Mini", 81.0, 83.3),
]

fig, ax = plt.subplots(figsize=(6.6, 5.0))
benchmarks = ["AIME", "PUPA (composite)", "IFBench", "Hearsay", "MMLU (macro)"]
y_positions = {}
y = 0
for b in benchmarks:
    for m in ("GPT-4.1 Mini", "GPT-4o-mini"):
        y_positions[(b, m)] = y
        y += 1
    y += 0.8

for bench, model, base, final in results:
    yy = y_positions[(bench, model)]
    color = C_41MINI if model == "GPT-4.1 Mini" else C_4OMINI
    line_color = C_RECOV if final >= base else C_REGR
    ax.plot([base, final], [yy, yy], color=line_color, linewidth=2.2, zorder=1,
            solid_capstyle="round")
    ax.scatter([base], [yy], color="white", edgecolor=color, linewidth=1.6,
               s=55, zorder=3)
    ax.scatter([final], [yy], color=color, edgecolor=color, linewidth=1.2,
               s=55, zorder=3)
    delta = final - base
    ax.annotate(f"{delta:+.1f}", (max(base, final) + 2.5, yy),
                va="center", fontsize=8, color=line_color, fontweight="bold")

group_centers = [sum(y_positions[(b, m)] for m in ("GPT-4.1 Mini", "GPT-4o-mini")) / 2
                 for b in benchmarks]
ax.set_yticks(group_centers)
ax.set_yticklabels(benchmarks, fontsize=10, fontweight="bold")
ax.tick_params(axis="y", length=0, pad=70)
for b in benchmarks:
    ax.text(-15, y_positions[(b, "GPT-4.1 Mini")], "GPT-4.1 Mini", fontsize=7.5,
            color=C_41MINI, va="center", ha="right")
    ax.text(-15, y_positions[(b, "GPT-4o-mini")], "GPT-4o-mini", fontsize=7.5,
            color=C_4OMINI, va="center", ha="right")
ax.set_xlim(-2, 108)
ax.set_xlabel("Accuracy / composite score (%)")
ax.set_title("Baseline $\\rightarrow$ Final, all five benchmarks\n(hollow = baseline, filled = final)")
ax.invert_yaxis()
legend_handles = [
    plt.Line2D([0], [0], color=C_RECOV, lw=2.2, label="Net improvement"),
    plt.Line2D([0], [0], color=C_REGR, lw=2.2, label="Net regression"),
]
ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.5, -0.08),
          ncol=2, frameon=False)
fig.tight_layout()
save(fig, "fig1_cross_benchmark_accuracy")


# ---------------------------------------------------------------------------
# Figure 2: recovered vs regressed (test), diverging bars, 5 benchmarks x 2 models
# MMLU is the sum across its 6 subjects (matches RESULTS.md's "Macro" framing).
# ---------------------------------------------------------------------------
confusion = [
    ("AIME -- GPT-4o-mini",        0,  1, -1),
    ("AIME -- GPT-4.1 Mini",    None, None,  2),  # item split not verifiable, see footnote
    ("PUPA -- GPT-4o-mini",        7,  3,  4),
    ("PUPA -- GPT-4.1 Mini",      10,  0, 10),
    ("IFBench -- GPT-4o-mini",     2,  3, -1),
    ("IFBench -- GPT-4.1 Mini",   12,  2, 10),
    ("Hearsay -- GPT-4o-mini",     8,  9, -1),
    ("Hearsay -- GPT-4.1 Mini",    7,  6,  1),
    ("MMLU (sum) -- GPT-4o-mini", 31, 23,  8),
    ("MMLU (sum) -- GPT-4.1 Mini", 17,  8,  9),
]

fig, ax = plt.subplots(figsize=(6.6, 5.2))
labels = [c[0] for c in confusion]
ys = list(range(len(labels)))[::-1]
NET_X = 36  # fixed column for every "net" annotation, regardless of bar length

for yy, (label, rec, reg, net) in zip(ys, confusion):
    if rec is None:
        ax.text(-25, yy, "item split not verifiable (see text)",
                va="center", ha="left", fontsize=7.5, color="#555555", style="italic")
        ax.text(NET_X, yy, f"net {net:+d}", va="center", ha="left", fontsize=8,
                fontweight="bold", color=C_RECOV)
        continue
    ax.barh(yy, rec, color=C_RECOV, height=0.6, zorder=2)
    if reg > 0:
        ax.barh(yy, -reg, color=C_REGR, height=0.6, zorder=2)
        ax.text(-reg - 1.0, yy, f"-{reg}", va="center", ha="right", fontsize=7.5, color=C_REGR)
    ax.text(rec + 1.0, yy, f"+{rec}", va="center", ha="left", fontsize=7.5, color=C_RECOV)
    ax.text(NET_X, yy, f"net {net:+d}", va="center", ha="left", fontsize=8,
            fontweight="bold", color=C_RECOV if net >= 0 else C_REGR)

ax.axvline(0, color="black", linewidth=0.8)
ax.axvline(NET_X - 2.2, color="#cccccc", linewidth=0.8, linestyle="--")
ax.set_yticks(ys)
ax.set_yticklabels(labels, fontsize=8.5)
ax.set_xlim(-26, 48)
ax.set_xlabel("Test items (count)")
ax.set_title("Recovered vs. regressed test items, baseline $\\rightarrow$ shipped prompt")
legend_handles = [
    plt.Rectangle((0, 0), 1, 1, color=C_RECOV, label="Recovered (wrong $\\rightarrow$ right)"),
    plt.Rectangle((0, 0), 1, 1, color=C_REGR, label="Regressed (right $\\rightarrow$ wrong)"),
]
ax.legend(handles=legend_handles, loc="upper center", bbox_to_anchor=(0.35, -0.08),
          ncol=1, frameon=False, fontsize=8)
fig.tight_layout()
save(fig, "fig2_recovered_regressed")


# ---------------------------------------------------------------------------
# Figure 3: GEPA vs ours, reflection/optimizer LM call budget (log scale)
# Only the 3 benchmarks that exist in both tables (comparison_analysis.md Table 6).
# ---------------------------------------------------------------------------
call_budget = {
    "AIME":    {"GEPA (GPT-4.1 Mini)": 24, "GEPA (Qwen3-8B)": 90, "Ours (GPT-4o-mini)": 3, "Ours (GPT-4.1 Mini)": 3},
    "PUPA":    {"GEPA (GPT-4.1 Mini)": 46, "GEPA (Qwen3-8B)": 38, "Ours (GPT-4o-mini)": 3, "Ours (GPT-4.1 Mini)": 3},
    "IFBench": {"GEPA (GPT-4.1 Mini)": 21, "GEPA (Qwen3-8B)": 17, "Ours (GPT-4o-mini)": 3, "Ours (GPT-4.1 Mini)": 3},
}
series = ["GEPA (GPT-4.1 Mini)", "GEPA (Qwen3-8B)", "Ours (GPT-4o-mini)", "Ours (GPT-4.1 Mini)"]
series_colors = [C_GEPA, "#BDBDBD", C_4OMINI, C_41MINI]

fig, ax = plt.subplots(figsize=(6.6, 3.8))
benches = list(call_budget.keys())
n_series = len(series)
width = 0.19
x = range(len(benches))
for i, (s, color) in enumerate(zip(series, series_colors)):
    vals = [call_budget[b][s] for b in benches]
    offs = [xx + (i - (n_series - 1) / 2) * width for xx in x]
    ax.bar(offs, vals, width=width, color=color, label=s, zorder=2)
    for xx, v in zip(offs, vals):
        ax.text(xx, v * 1.15, str(v), ha="center", fontsize=7.5)

ax.set_yscale("log")
ax.set_ylim(2, 150)
ax.set_xticks(list(x))
ax.set_xticklabels(benches)
ax.set_ylabel("Reflection/optimizer LM calls\n(log scale)")
ax.set_title("Optimizer-side call budget: GEPA vs. ours\n(not an efficiency claim -- see text)")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.2), ncol=2, frameon=False, fontsize=8)
fig.subplots_adjust(left=0.14)
fig.tight_layout()
save(fig, "fig3_call_budget_gepa_vs_ours")

print("done:", sorted(p.name for p in OUT.iterdir()))

