"""Budget guard + ledger arithmetic (no API calls)."""

import pytest

from fdpo.clients.mock_client import MockModelClient
from fdpo.utils.budget import (
    BudgetExceededError,
    BudgetGuard,
    TokenLedger,
    price_for,
)


def test_price_prefix_matching():
    assert price_for("gpt-4o-mini") == (0.15, 0.60)
    assert price_for("gpt-4o-mini-2024-07-18") == (0.15, 0.60)  # not gpt-4o's price
    assert price_for("gpt-4o") == (2.50, 10.00)
    assert price_for("gpt-4o-2024-08-06") == (2.50, 10.00)
    assert price_for("meta-llama/Meta-Llama-3-8B-Instruct") == (0.10, 0.10)
    assert price_for("Qwen/Qwen3-8B") == (0.10, 0.10)
    assert price_for("unknown-model") == (0.0, 0.0)
    assert price_for("unknown-model", fallback=(1.0, 2.0)) == (1.0, 2.0)


def test_ledger_arithmetic():
    ledger = TokenLedger()
    cost = ledger.record("solver", "gpt-4o-mini", 1_000_000, 1_000_000, "eval")
    assert cost == pytest.approx(0.15 + 0.60)
    ledger.record("judge", "gpt-4o", 2_000_000, 100_000, "judge")
    assert ledger.spent_usd == pytest.approx(0.75 + 5.0 + 1.0)
    assert ledger.n_calls == 2
    by_role = ledger.by_role()
    assert by_role["solver"]["calls"] == 1
    assert by_role["judge"]["cost_usd"] == pytest.approx(6.0)


def test_ledger_csv(tmp_path):
    ledger = TokenLedger(csv_path=tmp_path / "ledger.csv")
    ledger.record("solver", "gpt-4o-mini", 100, 50, "eval")
    ledger.record("solver", "gpt-4o-mini", 200, 80, "eval")
    lines = (tmp_path / "ledger.csv").read_text().strip().splitlines()
    assert len(lines) == 3  # header + 2 rows
    assert lines[0].startswith("role,model")


def test_guard_raises_at_cap():
    ledger = TokenLedger()
    guard = BudgetGuard(cap_usd=0.001, ledger=ledger)
    guard.check()  # nothing spent yet
    ledger.record("solver", "gpt-4o", 1_000_000, 0, "eval")  # $2.50
    with pytest.raises(BudgetExceededError):
        guard.check()


def test_guard_disabled_when_cap_nonpositive():
    ledger = TokenLedger()
    ledger.record("solver", "gpt-4o", 10_000_000, 10_000_000, "eval")
    BudgetGuard(cap_usd=0.0, ledger=ledger).check()
    BudgetGuard(cap_usd=-1.0, ledger=ledger).check()


def test_client_reports_to_ledger_and_guard_fires():
    ledger = TokenLedger(fallback_price=(1000.0, 1000.0))  # make mock tokens pricey
    guard = BudgetGuard(cap_usd=0.0001, ledger=ledger)
    client = MockModelClient(role="solver", responses=["hello world response"],
                             ledger=ledger, guard=guard)
    with pytest.raises(BudgetExceededError):
        client.complete([{"role": "user", "content": "hi there, long prompt text"}])
    assert ledger.n_calls == 1  # the call itself was recorded before the raise
