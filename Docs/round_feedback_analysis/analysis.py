"""Round-level feedback analysis (read-only on results/ and Paper_COLING/Artifacts).

Question: what do the effect reports shown from round 2 on do to the mining (M) and validation (V) sets?
Run from the repo root:  python Docs/round_feedback_analysis/analysis.py
Writes figures next to this file and prints every number quoted in Docs/round_feedback_analysis/findings.md.
"""
from __future__ import annotations

import glob
import itertools
import json
import math
import random
import statistics as st
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
GAP = json.load(open(ROOT / "Paper_COLING/Artifacts/val_test_gap.json"))

GREEN, RED, BLUE, AMBER, SLATE = "#2E7D32", "#C62828", "#1F5F99", "#C47A1E", "#55677A"
plt.rcParams.update({"font.family": "serif", "font.size": 9, "pdf.fonttype": 42, "savefig.dpi": 300,
                     "axes.spines.top": False, "axes.spines.right": False,
                     "axes.grid": True, "grid.alpha": 0.25, "grid.linewidth": 0.4})


def metrics(rec):
    return json.load(open(ROOT / rec["metrics_path"]))["optimization"]


def fisher(a, b, c, d):
    n = a + b + c + d
    r1, c1 = a + b, a + c

    def pm(x):
        return math.comb(r1, x) * math.comb(n - r1, c1 - x) / math.comb(n, c1)

    obs = pm(a)
    return sum(pm(x) for x in range(max(0, c1 - (n - r1)), min(r1, c1) + 1) if pm(x) <= obs + 1e-12)


def perm(a, b):
    obs = abs(st.mean(a) - st.mean(b))
    allv, n, c, t = a + b, len(a), 0, 0
    for idx in itertools.combinations(range(len(allv)), n):
        s = [allv[i] for i in idx]
        o = [allv[i] for i in range(len(allv)) if i not in idx]
        t += 1
        c += abs(st.mean(s) - st.mean(o)) >= obs - 1e-12
    return c / t


# ---------------------------------------------------------------- T1: pooled per round
rows = []
for rec in GAP:
    if not rec["rounds"]:
        continue
    o = metrics(rec)
    nm, nv = o["val_split"]["n_mining"], o["val_split"]["n_validation"]
    acc_m, acc_v = o["baseline_train"]["accuracy"], o["baseline_val_acc"]
    for r in rec["rounds"]:
        wm = round(nm * (1 - acc_m))
        wv = round(nv * (1 - acc_v))
        rows.append(dict(run=rec["run"], mmlu=rec["run"].startswith("MMLU"), r=r["round"], nm=nm, nv=nv,
                         wm=wm, rm=nm - wm, wv=wv, rv=nv - wv,
                         mr=r["mining_recovered"], mg=r["mining_regressed"],
                         vr=r["validation_recovered"], vg=r["validation_regressed"],
                         sec=len(r["sections_changed"])))
        acc_m, acc_v = r["mining_accuracy"], r["validation_accuracy"]


def pool(sel):
    g = lambda k: sum(x[k] for x in sel)
    return dict(n=len(sel), mr=g("mr"), mg=g("mg"), vr=g("vr"), vg=g("vg"), wm=g("wm"), rm=g("rm"), wv=g("wv"),
                rv=g("rv"), sec=st.mean(x["sec"] for x in sel))


P = {"round 1": pool([x for x in rows if x["r"] == 1]),
     "round 2": pool([x for x in rows if x["r"] == 2]),
     "round 3": pool([x for x in rows if x["r"] == 3]),
     "rounds 2-3": pool([x for x in rows if x["r"] >= 2])}
print("## T1 pooled per round (17 optimized runs)")
print("| slice | rounds | M rec/reg | M net | V rec/reg | V net | sections edited |")
for k, p in P.items():
    print(f"| {k} | {p['n']} | {p['mr']}/{p['mg']} | {p['mr']-p['mg']:+d} | {p['vr']}/{p['vg']} | {p['vr']-p['vg']:+d} | {p['sec']:.2f} |")
for lab, f in (("non-MMLU", lambda x: not x["mmlu"]), ("MMLU", lambda x: x["mmlu"])):
    for k, g in (("round 1", lambda x: x["r"] == 1), ("rounds 2-3", lambda x: x["r"] >= 2)):
        p = pool([x for x in rows if f(x) and g(x)])
        print(f"  {lab} {k}: rounds={p['n']} M {p['mr']}/{p['mg']} net {p['mr']-p['mg']:+d}; V {p['vr']}/{p['vg']} net {p['vr']-p['vg']:+d}")

print("\n## T2 headroom-adjusted rates")
for k in ("round 1", "rounds 2-3"):
    p = P[k]
    print(f"{k}: M recover {p['mr']}/{p['wm']}={p['mr']/p['wm']:.3f}  M regress {p['mg']}/{p['rm']}={p['mg']/p['rm']:.3f} | "
          f"V recover {p['vr']}/{p['wv']}={p['vr']/p['wv']:.3f}  V regress {p['vg']}/{p['rv']}={p['vg']/p['rv']:.3f}")
byrun = {}
for x in rows:
    byrun.setdefault(x["run"], {"r1": [], "r23": []})["r1" if x["r"] == 1 else "r23"].append(x)
dm = [st.mean(y["mr"] - y["mg"] for y in v["r23"]) - (v["r1"][0]["mr"] - v["r1"][0]["mg"]) for v in byrun.values() if v["r1"] and v["r23"]]
dv = [st.mean(y["vr"] - y["vg"] for y in v["r23"]) - (v["r1"][0]["vr"] - v["r1"][0]["vg"]) for v in byrun.values() if v["r1"] and v["r23"]]
random.seed(0)


def signflip(d, n=20000):
    obs, c = abs(st.mean(d)), 0
    for _ in range(n):
        c += abs(st.mean([x * random.choice((-1, 1)) for x in d])) >= obs - 1e-12
    return c / n


print(f"paired runs={len(dm)}  mean M net (r2-3 minus r1) {st.mean(dm):+.2f}, lower in {sum(x<0 for x in dm)}/{len(dm)} runs, sign-flip p={signflip(dm):.3f}")
print(f"                    mean V net (r2-3 minus r1) {st.mean(dv):+.2f}, lower in {sum(x<0 for x in dv)}/{len(dv)} runs, sign-flip p={signflip(dv):.3f}")


# ---------------------------------------------------------------- T3: item-ID mechanics
def committed(o):
    return [r for r in o["rounds_log"] if r.get("status") == "committed" and "recovered_this_round" in r]


def mech(runs_o):
    rep_h = rep_n = oth_h = oth_n = rev = new = 0
    per_run = []
    for o in runs_o:
        L = committed(o)
        rv_run = nw_run = 0
        for prev, cur in zip(L, L[1:]):
            if cur["round"] != prev["round"] + 1:
                continue
            regp, recp = set(prev["regressed_this_round"]), set(prev["recovered_this_round"])
            wrong_prev = set(prev["failing_ids_after"])
            rec_c, reg_c = set(cur["recovered_this_round"]), set(cur["regressed_this_round"])
            rep_h += len(regp & rec_c); rep_n += len(regp)
            ow = wrong_prev - regp
            oth_h += len(ow & rec_c); oth_n += len(ow)
            rv = len((rec_c & regp) | (reg_c & recp))
            nw = len(rec_c | reg_c) - rv
            rev += rv; new += nw; rv_run += rv; nw_run += nw
        per_run.append((rv_run, nw_run))
    return dict(rep_h=rep_h, rep_n=rep_n, oth_h=oth_h, oth_n=oth_n, rev=rev, new=new, per_run=per_run)


main_o = [metrics(r) for r in GAP if r["rounds"]]
M_main = mech(main_o)
ARM = {a: [json.load(open(p))["optimization"] for p in sorted(glob.glob(str(ROOT / f"results/ablation_hearsay_4omini_{a}/*/metrics.json")))]
       for a in ("report", "noreport")}
M_arm = {a: mech(v) for a, v in ARM.items()}

print("\n## T3 mechanics of rounds 2-3 (consecutive committed rounds, mining item IDs)")
print(f"main runs: just-regressed items recovered next round {M_main['rep_h']}/{M_main['rep_n']}={M_main['rep_h']/M_main['rep_n']:.3f}; "
      f"other still-wrong items recovered {M_main['oth_h']}/{M_main['oth_n']}={M_main['oth_h']/M_main['oth_n']:.3f}; "
      f"Fisher p={fisher(M_main['rep_h'], M_main['rep_n']-M_main['rep_h'], M_main['oth_h'], M_main['oth_n']-M_main['oth_h']):.1e}; "
      f"flips reversing prior flip {M_main['rev']}/{M_main['rev']+M_main['new']}={M_main['rev']/(M_main['rev']+M_main['new']):.3f}")
for a, m in M_arm.items():
    print(f"ablation {a}: just-regressed recovered {m['rep_h']}/{m['rep_n']}={m['rep_h']/m['rep_n']:.3f}; other-wrong recovered "
          f"{m['oth_h']}/{m['oth_n']}={m['oth_h']/m['oth_n']:.3f}; reversal flips {m['rev']}, new flips {m['new']}")
r, n = M_arm["report"], M_arm["noreport"]
print(f"Fisher repair-of-regressed report vs noreport p={fisher(r['rep_h'], r['rep_n']-r['rep_h'], n['rep_h'], n['rep_n']-n['rep_h']):.3f}")
print(f"Fisher regression-to-mean control inside noreport (flagged vs other) p={fisher(n['rep_h'], n['rep_n']-n['rep_h'], n['oth_h'], n['oth_n']-n['oth_h']):.3f}")
a_new = [x[1] for x in r["per_run"]]; b_new = [x[1] for x in n["per_run"]]
a_rev = [x[0] for x in r["per_run"]]; b_rev = [x[0] for x in n["per_run"]]
print(f"per-run NEW (non-reversal) mining flips rounds 2-3: report {a_new} mean {st.mean(a_new):.1f} vs noreport {b_new} mean {st.mean(b_new):.1f}  perm p={perm(a_new, b_new):.3f}")
print(f"per-run REVERSAL mining flips rounds 2-3:           report {a_rev} mean {st.mean(a_rev):.1f} vs noreport {b_rev} mean {st.mean(b_rev):.1f}  perm p={perm(a_rev, b_rev):.3f}")

# ---------------------------------------------------------------- T4: ablation per-run, mining + validation
print("\n## T4 ablation per-run means over rounds 2-3 (5 runs per arm)")
AR = {}
for a, v in ARM.items():
    out = []
    for o in v:
        L = [x for x in committed(o) if x["round"] >= 2]
        out.append(dict(mr=st.mean(len(x["recovered_this_round"]) for x in L), mg=st.mean(len(x["regressed_this_round"]) for x in L),
                        vr=st.mean(x["val_recovered_this_round"] for x in L), vg=st.mean(x["val_regressed_this_round"] for x in L)))
    AR[a] = out
for lab, fn in (("M regressions", lambda x: x["mg"]), ("V regressions", lambda x: x["vg"]),
                ("M+V regressions", lambda x: x["mg"] + x["vg"]), ("M+V churn", lambda x: x["mr"] + x["mg"] + x["vr"] + x["vg"]),
                ("M+V net", lambda x: x["mr"] - x["mg"] + x["vr"] - x["vg"])):
    a = [fn(x) for x in AR["report"]]; b = [fn(x) for x in AR["noreport"]]
    print(f"{lab}: report {st.mean(a):.2f} vs noreport {st.mean(b):.2f}  perm p={perm(a, b):.3f}")

# ---------------------------------------------------------------- T5: shipped-round buckets
print("\n## T5 shipped-round buckets")
B = {"shipped round 1": lambda r: r["shipped"] and r["shipped_round"] == 1,
     "shipped round 2-3 (best-of)": lambda r: r["shipped"] and r["selection"] == "best_of_rounds" and (r["shipped_round"] or 0) >= 2,
     "shipped last round": lambda r: r["shipped"] and r["selection"] == "last_round"}
BK = {}
for lab, f in B.items():
    s = [r for r in GAP if f(r) and r["val_measured"]]
    BK[lab] = [(100 * (r["val_best"] - r["val_base"]), r["test_delta_pp"], r["run"]) for r in s]
    d1 = st.mean(x[0] for x in BK[lab]); d2 = st.mean(x[1] for x in BK[lab])
    print(f"{lab}: n={len(s)} mean dV {d1:+.1f} mean dT {d2:+.1f} gap {d1-d2:+.1f}")

# ---------------------------------------------------------------- T6: instability
print("\n## T6 instability")
tot = dis = rep_f = 0
for o in main_o:
    cnt = {}
    for x in committed(o):
        for i in x["recovered_this_round"] + x["regressed_this_round"]:
            cnt[i] = cnt.get(i, 0) + 1
    tot += sum(cnt.values()); dis += len(cnt); rep_f += sum(v for v in cnt.values() if v >= 2)
print(f"main runs: {tot} mining flips over {dis} distinct items; {rep_f} ({rep_f/tot:.1%}) are on items that flipped at least twice")
L1 = sum(1 for x in rows if x["r"] == 1); Lall = len(rows)
print(f"committed rounds: {Lall}; round 1: {L1} ({L1/Lall:.0%}); rounds 2-3: {Lall-L1} ({(Lall-L1)/Lall:.0%})")

# ================================================================= figures
# F1: pooled recovered/regressed per round
fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.6), sharey=True)
for ax, (tag, kr, kg, ttl) in zip(axes, (("M", "mr", "mg", "Mining set M (feedback target)"), ("V", "vr", "vg", "Validation set V (selection + feedback from round 2)"))):
    for i, k in enumerate(("round 1", "round 2", "round 3")):
        p = P[k]
        ax.bar(i, p[kr], color=GREEN, width=0.6, zorder=2)
        ax.bar(i, -p[kg], color=RED, width=0.6, zorder=2)
        ax.scatter([i], [p[kr] - p[kg]], marker="D", s=26, color="black", zorder=3)
        ax.text(i, p[kr] + 1.2, f"+{p[kr]}", ha="center", fontsize=8, color=GREEN)
        ax.text(i, -p[kg] - 1.2, f"-{p[kg]}", ha="center", va="top", fontsize=8, color=RED)
    ax.axhline(0, color="black", lw=0.7)
    ax.set_xticks(range(3))
    ax.set_xticklabels([f"{n}\n{c}\nnet {P[k][kr]-P[k][kg]:+d}" for n, c, k in (("round 1", "(no report)", "round 1"), ("round 2", "(report)", "round 2"), ("round 3", "(report)", "round 3"))], fontsize=8)
    ax.set_title(ttl, fontsize=8)
    ax.set_xlim(-0.6, 2.6)
axes[0].set_ylabel("items, pooled over runs"); axes[0].set_ylim(-44, 70)
fig.legend(handles=[Line2D([0], [0], marker="s", color="w", markerfacecolor=GREEN, markersize=7, label="Recovered"),
                    Line2D([0], [0], marker="s", color="w", markerfacecolor=RED, markersize=7, label="Regressed"),
                    Line2D([0], [0], marker="D", color="w", markerfacecolor="black", markersize=5, label="Net")],
           loc="upper center", ncol=3, frameon=False, bbox_to_anchor=(0.5, 1.04))
fig.tight_layout(rect=(0, 0, 1, 0.93))
fig.savefig(HERE / "fig1_rounds_pooled.png", bbox_inches="tight"); fig.savefig(HERE / "fig1_rounds_pooled.pdf", bbox_inches="tight"); plt.close(fig)

# F2: headroom-adjusted rates
fig, ax = plt.subplots(figsize=(4.6, 2.6))
groups = [("M recover\n(of failing)", "mr", "wm"), ("M regress\n(of correct)", "mg", "rm"),
          ("V recover\n(of failing)", "vr", "wv"), ("V regress\n(of correct)", "vg", "rv")]
for gi, (lab, num, den) in enumerate(groups):
    for j, (k, col) in enumerate((("round 1", BLUE), ("rounds 2-3", AMBER))):
        v = 100 * P[k][num] / P[k][den]
        ax.bar(gi + (j - 0.5) * 0.36, v, width=0.34, color=col, zorder=2)
        ax.text(gi + (j - 0.5) * 0.36, v + 0.8, f"{v:.0f}%", ha="center", fontsize=7.5)
ax.set_xticks(range(4)); ax.set_xticklabels([g[0] for g in groups], fontsize=7.5)
ax.set_ylabel("share of items (%)"); ax.set_ylim(0, 48)
ax.legend(handles=[Line2D([0], [0], marker="s", color="w", markerfacecolor=BLUE, markersize=7, label="round 1 (no report)"),
                   Line2D([0], [0], marker="s", color="w", markerfacecolor=AMBER, markersize=7, label="rounds 2-3 (report)")],
          frameon=False, loc="upper right", fontsize=7.5)
fig.tight_layout()
fig.savefig(HERE / "fig2_headroom_rates.png", bbox_inches="tight"); fig.savefig(HERE / "fig2_headroom_rates.pdf", bbox_inches="tight"); plt.close(fig)

# F3: ablation (a) per-run churn, (b) reversal vs new flips
fig, axes = plt.subplots(1, 2, figsize=(6.6, 2.7), gridspec_kw={"width_ratios": [1.05, 1]})
ax = axes[0]
for i, (a, col, lab) in enumerate((("noreport", SLATE, "no report"), ("report", BLUE, "with report"))):
    vals = [x["mr"] + x["mg"] + x["vr"] + x["vg"] for x in AR[a]]
    xs = [i + (k - 2) * 0.05 for k in range(5)]
    ax.scatter(xs, vals, color=col, s=24, zorder=3)
    ax.hlines(st.mean(vals), i - 0.22, i + 0.22, color="black", lw=1.6, zorder=4)
    ax.text(i + 0.26, st.mean(vals), f"{st.mean(vals):.1f}", va="center", fontsize=8)
ax.set_xticks([0, 1]); ax.set_xticklabels(["no report", "with report"]); ax.set_xlim(-0.5, 1.7)
ax.set_ylabel("changed items per round\n(M + V, run means)"); ax.set_ylim(0, 19)
ax.set_title("LegalBench-Hearsay, 4o-mini; 5 runs per arm, p = 0.024", fontsize=8)
ax = axes[1]
for i, (a, lab) in enumerate((("noreport", "no report"), ("report", "with report"))):
    m = M_arm[a]
    ax.bar(i, m["rev"], color=SLATE, width=0.5, zorder=2, label="undoes previous flip" if i == 0 else None)
    ax.bar(i, m["new"], bottom=m["rev"], color=AMBER, width=0.5, zorder=2, label="new flip" if i == 0 else None)
    ax.text(i, m["rev"] / 2, str(m["rev"]), ha="center", va="center", color="white", fontsize=8)
    ax.text(i, m["rev"] + m["new"] / 2, str(m["new"]), ha="center", va="center", color="white", fontsize=8)
ax.set_xticks([0, 1]); ax.set_xticklabels(["no report", "with report"]); ax.set_ylabel("mining flips, rounds 2-3\n(sum of 5 runs)")
ax.legend(frameon=False, fontsize=7.5, loc="upper right"); ax.set_ylim(0, 62)
fig.tight_layout()
fig.savefig(HERE / "fig3_ablation_mechanics.png", bbox_inches="tight"); fig.savefig(HERE / "fig3_ablation_mechanics.pdf", bbox_inches="tight"); plt.close(fig)

# F4: shipped-round buckets, validation gain vs test gain
fig, ax = plt.subplots(figsize=(5.2, 2.8))
for i, (lab, pts) in enumerate(BK.items()):
    for j, (v, t, _) in enumerate(pts):
        x = i + (j - (len(pts) - 1) / 2) * 0.09
        ax.plot([x, x], [v, t], color="#9AA5B1", lw=1.0, zorder=1)
        ax.scatter([x], [v], facecolor="white", edgecolor=BLUE, s=26, zorder=3, linewidths=1.2)
        ax.scatter([x], [t], color=GREEN if t >= 0 else RED, s=26, zorder=3)
    mv, mt = st.mean(p[0] for p in pts), st.mean(p[1] for p in pts)
    ax.hlines([mv], i - 0.3, i + 0.3, color=BLUE, lw=2.0, zorder=4); ax.hlines([mt], i - 0.3, i + 0.3, color="black", lw=2.0, zorder=4)
    ax.text(i + 0.33, mv, f"{mv:+.1f}", fontsize=7.5, va="center", color=BLUE)
    ax.text(i + 0.33, mt, f"{mt:+.1f}", fontsize=7.5, va="center")
ax.axhline(0, color="black", lw=0.6)
ax.set_xticks(range(3)); ax.set_xticklabels([f"{k.replace('shipped ', 'shipped\n')}\n(n={len(v)})" for k, v in BK.items()], fontsize=7.5)
ax.set_xlim(-0.5, 2.8); ax.set_ylabel("accuracy change (pp)")
ax.legend(handles=[Line2D([0], [0], marker="o", color="w", markerfacecolor="white", markeredgecolor=BLUE, markersize=6, label="validation"),
                   Line2D([0], [0], marker="o", color="w", markerfacecolor=GREEN, markersize=6, label="test"),
                   Line2D([0], [0], color="black", lw=2, label="mean test"), Line2D([0], [0], color=BLUE, lw=2, label="mean validation")],
          frameon=False, fontsize=7, loc="upper right", ncol=2)
fig.tight_layout()
fig.savefig(HERE / "fig4_shipped_round_gap.png", bbox_inches="tight"); fig.savefig(HERE / "fig4_shipped_round_gap.pdf", bbox_inches="tight"); plt.close(fig)
print("\nfigures written to", HERE)
