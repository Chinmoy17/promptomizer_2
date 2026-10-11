"""Regression gate: pool FIFO, pass/fail arithmetic, cold start, recovery."""

import random

from fdpo.clients.mock_client import MockModelClient
from fdpo.core.gate import CorrectPool, evaluate_candidate
from fdpo.data.loaders import Example

OLD = {"full_prompt": "old prompt"}
NEW = {"full_prompt": "new prompt"}


def mc_example(i, gold="A"):
    return Example(id=f"ex{i}", question=f"q{i}?\n\nA. x\nB. y", gold=gold)


def scripted_solver(answers):
    """Solver that pops answers in call order."""
    return MockModelClient(role="solver", responses=[f"Answer: {a}" for a in answers])


def test_pool_fifo_and_dedup():
    pool = CorrectPool(cap=3)
    for i in range(5):
        pool.add(mc_example(i))
    pool.add(mc_example(4))  # duplicate ignored
    assert len(pool) == 3
    sampled = pool.sample(10, random.Random(0))
    assert {e.id for e in sampled} == {"ex2", "ex3", "ex4"}  # oldest evicted


def test_gate_pass_when_no_regression():
    batch = [mc_example(i) for i in range(4)]
    # order: old eval (4 calls) then new eval (4 calls); no failures passed
    solver = scripted_solver(["A", "A", "A", "A", "A", "A", "A", "A"])
    r = evaluate_candidate(solver, "arc", OLD, NEW, batch, [], rho=0.02,
                           min_pool=2)
    assert r.passed and r.acc_old == 1.0 and r.acc_new == 1.0 and r.broke == 0


def test_gate_fail_on_regression_beyond_rho():
    batch = [mc_example(i) for i in range(4)]
    # old: 4/4 correct; new: 2/4 correct -> drop 0.5 > rho
    solver = scripted_solver(["A", "A", "A", "A", "A", "A", "B", "B"])
    r = evaluate_candidate(solver, "arc", OLD, NEW, batch, [], rho=0.02,
                           min_pool=2)
    assert not r.passed
    assert r.acc_old == 1.0 and r.acc_new == 0.5
    assert r.broke == 2


def test_gate_tolerates_drop_within_rho():
    batch = [mc_example(i) for i in range(4)]
    # old: 3/4; new: 3/4 -> no drop
    solver = scripted_solver(["A", "A", "A", "B", "A", "A", "B", "A"])
    r = evaluate_candidate(solver, "arc", OLD, NEW, batch, [], rho=0.02,
                           min_pool=2)
    assert r.passed
    assert r.broke == 1  # ex2 was correct under old, wrong under new


def test_cold_start_auto_pass_with_recovery():
    failures = [mc_example(100), mc_example(101)]
    # only recovery calls happen (2); new prompt fixes 1 of 2
    solver = scripted_solver(["A", "B"])
    r = evaluate_candidate(solver, "arc", OLD, NEW, [], failures, rho=0.02,
                           min_pool=5)
    assert r.passed and r.batch_size == 0
    assert r.n_failures == 2 and r.recovered_failures == 1
