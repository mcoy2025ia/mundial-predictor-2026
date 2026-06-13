"""Tests para CostGuard — límites de gasto LLM."""
import json
import tempfile
from pathlib import Path

import pytest

from src.cost_guard import BudgetExceeded, CostGuard


def _guard(
    daily=10.0,
    monthly=100.0,
    max_calls=3,
    ledger: Path = None,
) -> CostGuard:
    if ledger is None:
        ledger = Path(tempfile.mktemp(suffix=".jsonl"))
    cfg = {
        "llm": {
            "daily_limit_usd": daily,
            "monthly_limit_usd": monthly,
            "max_calls_per_run": max_calls,
            "cost_per_1k_tokens": {"test-model": 1.0},
            "ledger_path": str(ledger),
        }
    }
    g = CostGuard(config=cfg)
    g.ledger_path = ledger
    return g


# ---------------------------------------------------------------------------
# estimate_cost
# ---------------------------------------------------------------------------

def test_estimate_cost_basic():
    g = _guard()
    cost = g.estimate_cost("test-model", 1000)
    assert abs(cost - 1.0) < 1e-6


def test_estimate_cost_unknown_model_uses_default():
    g = _guard()
    cost = g.estimate_cost("unknown-model", 1000)
    assert cost > 0


# ---------------------------------------------------------------------------
# check_and_record — camino feliz
# ---------------------------------------------------------------------------

def test_check_and_record_writes_ledger():
    with tempfile.TemporaryDirectory() as tmpdir:
        ledger = Path(tmpdir) / "ledger.jsonl"
        g = _guard(ledger=ledger)
        g.check_and_record("test-model", 100, agent_name="TestAgent", match="A vs B")
        assert ledger.exists()
        entries = [json.loads(l) for l in ledger.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["agent"] == "TestAgent"
        assert entries[0]["tokens"] == 100


def test_run_calls_increments():
    g = _guard(max_calls=5)
    assert g.run_calls_remaining() == 5
    g.check_and_record("test-model", 1)
    assert g.run_calls_remaining() == 4


# ---------------------------------------------------------------------------
# Límite de llamadas por run
# ---------------------------------------------------------------------------

def test_max_calls_per_run_raises():
    g = _guard(max_calls=2)
    g.check_and_record("test-model", 1)
    g.check_and_record("test-model", 1)
    with pytest.raises(BudgetExceeded, match="max_calls_per_run"):
        g.check_and_record("test-model", 1)


# ---------------------------------------------------------------------------
# Límite diario
# ---------------------------------------------------------------------------

def test_daily_limit_raises():
    g = _guard(daily=0.001, max_calls=100)
    # El primer check ya debería superar el límite de $0.001 (1000 tokens @ $1/1k = $1)
    with pytest.raises(BudgetExceeded, match="Daily"):
        g.check_and_record("test-model", 1000)


def test_daily_limit_ok_when_under():
    g = _guard(daily=10.0, max_calls=100)
    # 1 token × $1/1k = $0.001, bien por debajo de $10
    g.check_and_record("test-model", 1)


# ---------------------------------------------------------------------------
# Límite mensual
# ---------------------------------------------------------------------------

def test_monthly_limit_raises():
    g = _guard(daily=1000.0, monthly=0.001, max_calls=100)
    with pytest.raises(BudgetExceeded, match="Monthly"):
        g.check_and_record("test-model", 1000)


# ---------------------------------------------------------------------------
# Ledger vacío / inexistente
# ---------------------------------------------------------------------------

def test_daily_spent_no_ledger():
    g = _guard(ledger=Path("/tmp/nonexistent_guard_ledger_xyz.jsonl"))
    assert g.daily_spent() == 0.0


def test_monthly_spent_no_ledger():
    g = _guard(ledger=Path("/tmp/nonexistent_guard_ledger_xyz.jsonl"))
    assert g.monthly_spent() == 0.0
