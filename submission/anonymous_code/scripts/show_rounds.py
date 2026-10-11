"""Inspect a simple_fdpo run: per-round failing examples (before/after),
what each round recovered/regressed, the temperatures used, and the final
optimized prompt.

Usage:
    uv run python -m scripts.show_rounds <run_dir>
    uv run python -m scripts.show_rounds            # auto-picks the newest run

Reads metrics.json (+ prompt_current.md) from the run directory. Optionally
maps failing example IDs back to their questions if the dataset jsonl is
available under Dataset/.
"""

from __future__ import annotations

import glob
import json
import os
import sys


def _newest_run() -> str | None:
    runs = glob.glob("results/*/*_simple_fdpo_*")
    runs = [r for r in runs if os.path.isdir(r)]
    return max(runs, key=os.path.getmtime) if runs else None


def _load_questions(dataset: str) -> dict[str, str]:
    """id -> question, best-effort from Dataset/<dir>/{train,test}.jsonl."""
    from fdpo.data.loaders import DATASET_DIRS
    d = DATASET_DIRS.get(dataset, dataset)
    out: dict[str, str] = {}
    for split in ("train", "test"):
        path = f"Dataset/{d}/{split}.jsonl"
        if not os.path.exists(path):
            continue
        for line in open(path, encoding="utf-8"):
            ex = json.loads(line)
            out[ex["id"]] = ex.get("question", "")
    return out


def _short(qid: str, questions: dict[str, str], width: int = 90) -> str:
    q = questions.get(qid, "").replace("\n", " ").strip()
    return f"{qid}" + (f"  |  {q[:width]}" if q else "")


def main(argv: list[str]) -> int:
    run_dir = argv[0] if argv else _newest_run()
    if not run_dir or not os.path.isdir(run_dir):
        print("no run dir found; pass one explicitly")
        return 1
    m = json.load(open(os.path.join(run_dir, "metrics.json"), encoding="utf-8"))
    print(f"RUN: {run_dir}\n")

    dataset = m.get("dataset", "")
    questions = _load_questions(dataset)

    print(f"method            : {m.get('method')}")
    print(f"dataset           : {dataset}")
    print(f"seed              : {m.get('seed')}")
    print(f"prompt source     : {m.get('optimization', {}).get('prompt_source', m.get('markdown_source', '?'))}")
    seed_t = m.get("seed_test", {}).get("accuracy")
    final_t = m.get("final_test", {}).get("accuracy")
    print(f"TEST  baseline    : {seed_t:.3f}" if seed_t is not None else "TEST baseline: ?")
    print(f"TEST  final       : {final_t:.3f}" if final_t is not None else "TEST final: ?")
    if seed_t is not None and final_t is not None:
        print(f"TEST  delta       : {final_t - seed_t:+.3f}")

    opt = m.get("optimization", {})
    print(f"\nsolver_temperature   : {opt.get('solver_temperature', '?')}")
    print(f"optimizer_temperature: {opt.get('optimizer_temperature', '?')}")
    print(f"tau / max_rounds     : {opt.get('tau')} / {opt.get('simple_max_rounds')}")

    bt = opt.get("baseline_train", {})
    print(f"\nTRAIN baseline    : acc {bt.get('accuracy')}  "
          f"({bt.get('n_correct')} right / {bt.get('n_wrong')} wrong)")
    base_fail = opt.get("baseline_failing_ids", [])
    print(f"BASELINE failing ({len(base_fail)}):")
    for qid in base_fail:
        print(f"   - {_short(qid, questions)}")

    print("\n==================== PER-ROUND ====================")
    for r in opt.get("rounds_log", []):
        print(f"\n--- Round {r.get('round')}  [{r.get('status')}] ---")
        print(f"    failures: {r.get('n_failures_before')} -> {r.get('n_failures_after')}"
              f"   (train acc after: {r.get('train_acc_after')})")
        print(f"    sections changed: {r.get('sections_changed')}")
        rec = r.get("recovered_this_round", [])
        reg = r.get("regressed_this_round", [])
        if rec:
            print(f"    RECOVERED this round ({len(rec)}):")
            for qid in rec:
                print(f"       + {_short(qid, questions)}")
        if reg:
            print(f"    REGRESSED this round ({len(reg)}):")
            for qid in reg:
                print(f"       - {_short(qid, questions)}")
        if not rec and not reg:
            print("    (no examples flipped vs. the round's starting point)")

    tc = opt.get("test_confusion", {})
    if tc:
        print("\n==================== TEST CONFUSION (baseline vs final) ====================")
        print(f"    recovered: {len(tc.get('recoveries', []))}  "
              f"regressed: {len(tc.get('regressions', []))}  "
              f"net: {tc.get('net_gain')}")

    pc = os.path.join(run_dir, "prompt_current.md")
    if os.path.exists(pc):
        print("\n==================== FINAL ACTIVE PROMPT (prompt_current.md) ====================")
        print(open(pc, encoding="utf-8").read())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
