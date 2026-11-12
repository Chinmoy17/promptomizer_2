"""Mining / validation accuracy trajectories: baseline -> round 1 -> round 2 -> round 3 (17 optimized runs).

Run from the repo root:  python Docs/round_feedback_analysis/trajectories.py
Reads only results/ and Paper_COLING/Artifacts/val_test_gap.json. Rounds where the optimizer proposed no change
or the run stopped early keep the previous prompt, so its accuracy is carried forward.
"""
from __future__ import annotations

import json
import statistics as st
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
GAP = json.load(open(ROOT / "Paper_COLING/Artifacts/val_test_gap.json"))

BLUE, GREEN, AMBER, SLATE, RED = "#1F5F99", "#1F7A4A", "#C47A1E", "#55677A", "#C62828"
plt.rcParams.update({"font.family": "serif", "font.size": 8.5, "pdf.fonttype": 42, "savefig.dpi": 300,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4})

runs = []
for rec in GAP:
    if not rec["rounds"]:
        continue
    o = json.load(open(ROOT / rec["metrics_path"]))["optimization"]
    m, v = [100 * o["baseline_train"]["accuracy"]], [100 * o["baseline_val_acc"]]
    by = {r["round"]: r for r in rec["rounds"]}
    for t in (1, 2, 3):
        if t in by:
            m.append(100 * by[t]["mining_accuracy"]); v.append(100 * by[t]["validation_accuracy"])
        else:
            m.append(m[-1]); v.append(v[-1])
    runs.append(dict(name=rec["run"], mmlu=rec["run"].startswith("MMLU"), m=m, v=v))

n = len(runs)
mean = lambda k, i: st.mean(r[k][i] for r in runs)
sem = lambda xs: st.stdev(xs) / len(xs) ** 0.5

print(f"runs: {n}")
for lab, k in (("mining M", "m"), ("validation V", "v")):
    print(f"{lab}: mean accuracy by stage (baseline, r1, r2, r3) = " + ", ".join(f"{mean(k, i):.1f}" for i in range(4)))
steps = [("baseline to round 1", 0, 1), ("round 1 to round 2", 1, 2), ("round 2 to round 3", 2, 3)]
STEP = {}
for lab, k in (("M", "m"), ("V", "v")):
    for sl, a, b in steps:
        d = [r[k][b] - r[k][a] for r in runs]
        STEP[(lab, sl)] = d
        print(f"{lab} {sl}: mean {st.mean(d):+.2f} pp (SEM {sem(d):.2f}); up in {sum(x > 0 for x in d)}, flat {sum(x == 0 for x in d)}, down {sum(x < 0 for x in d)}")
tot = {k: [r[k][3] - r[k][0] for r in runs] for k in ("m", "v")}
print(f"baseline to round 3: M {st.mean(tot['m']):+.2f}, V {st.mean(tot['v']):+.2f}")
share = lambda lab: STEP[(lab, steps[0][0])] and st.mean(STEP[(lab, steps[0][0])]) / (st.mean(STEP[(lab, steps[0][0])]) + st.mean(STEP[(lab, steps[1][0])]) + st.mean(STEP[(lab, steps[2][0])]))
print(f"share of total mean gain made in round 1: M {share('M'):.0%}, V {share('V'):.0%}")
best_v = [max(r["v"][1:]) - r["v"][0] for r in runs]
print(f"best-validation-round gain on V (selection effect, optimistic): {st.mean(best_v):+.2f} pp")

# ------------------------------------------------------------------ figure
fig = plt.figure(figsize=(7.2, 3.3))
gs = fig.add_gridspec(1, 3, width_ratios=[1, 1, 0.9], wspace=0.32)
labels = ["baseline", "round 1", "round 2", "round 3"]
for pi, (k, ttl, shade) in enumerate((("m", "Mining set M", BLUE), ("v", "Validation set V", GREEN))):
    ax = fig.add_subplot(gs[0, pi])
    for r in runs:
        ax.plot(range(4), r[k], color=BLUE if not r["mmlu"] else SLATE, lw=0.7, alpha=0.45, zorder=2)
    mu = [mean(k, i) for i in range(4)]
    ax.plot(range(4), mu, color="black", lw=2.2, marker="o", ms=4.5, zorder=4)
    for i, y in enumerate(mu):
        ax.text(i, y + (4.5 if i else -7.5), f"{y:.0f}", ha="center", fontsize=8, fontweight="bold")
    ax.axvspan(1.5, 3.5, color=AMBER, alpha=0.08, zorder=0)
    ax.set_xticks(range(4)); ax.set_xticklabels(["base-\nline", "round\n1", "round\n2", "round\n3"], fontsize=8)
    ax.set_ylim(-3, 118); ax.set_xlim(-0.3, 3.3); ax.set_yticks(range(0, 101, 20))
    ax.set_title(ttl, fontsize=9, fontweight="bold", color=shade)
    if pi == 0:
        ax.set_ylabel("accuracy (%)")
        ax.text(2.5, 116, "effect report shown", ha="center", va="top", fontsize=7, color=AMBER)
        ax.text(0.5, 116, "no report", ha="center", va="top", fontsize=7, color=SLATE)
    else:
        ax.text(2.5, 116, "V visible to optimizer", ha="center", va="top", fontsize=7, color=AMBER)
        ax.text(0.5, 116, "V hidden", ha="center", va="top", fontsize=7, color=SLATE)

ax = fig.add_subplot(gs[0, 2])
w = 0.36
for si, (sl, a, b) in enumerate(steps):
    for j, (lab, col) in enumerate((("M", BLUE), ("V", GREEN))):
        d = STEP[(lab, sl)]
        x = si + (j - 0.5) * w
        ax.bar(x, st.mean(d), width=w * 0.92, color=col, zorder=2)
        ax.errorbar(x, st.mean(d), yerr=sem(d), color="black", lw=0.9, capsize=2, zorder=3)
        ax.text(x, st.mean(d) + (sem(d) + 0.5 if st.mean(d) >= 0 else -sem(d) - 0.5), f"{st.mean(d):+.1f}",
                ha="center", va="bottom" if st.mean(d) >= 0 else "top", fontsize=7.5)
ax.axhline(0, color="black", lw=0.7)
ax.set_xticks(range(3)); ax.set_xticklabels(["base to\nround 1", "round 1\nto 2", "round 2\nto 3"], fontsize=8)
ax.set_ylabel("mean change (pp)"); ax.set_ylim(-9, 22)
ax.set_title("Where the gain comes from", fontsize=9, fontweight="bold")
ax.legend(handles=[Line2D([0], [0], marker="s", color="w", markerfacecolor=BLUE, markersize=7, label="M"),
                   Line2D([0], [0], marker="s", color="w", markerfacecolor=GREEN, markersize=7, label="V")],
          frameon=False, loc="upper right", fontsize=8)
fig.legend(handles=[Line2D([0], [0], color=BLUE, lw=1.2, alpha=0.6, label="non-MMLU run"),
                    Line2D([0], [0], color=SLATE, lw=1.2, alpha=0.6, label="MMLU subject"),
                    Line2D([0], [0], color="black", lw=2.2, marker="o", ms=4, label="mean of 17 runs")],
           loc="lower center", ncol=3, frameon=False, fontsize=8, bbox_to_anchor=(0.36, -0.02))
fig.subplots_adjust(bottom=0.2, top=0.9, left=0.07, right=0.985)
fig.savefig(HERE / "fig5_trajectories.png", bbox_inches="tight")
fig.savefig(HERE / "fig5_trajectories.pdf", bbox_inches="tight")
print("wrote fig5_trajectories")
