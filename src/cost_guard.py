"""LLM spend tracking and guardrails.

Reads limits from configs/budget.yaml and enforces them via a JSONL ledger
at logs/llm_costs.jsonl.  All agent calls go through `CostGuard.check_and_record`.

If a limit is exceeded, `BudgetExceeded` is raised so the Orchestrator can
fall back to the deterministic Ensemble without LLM delta adjustments.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

ROOT = Path(__file__).parent.parent
CONFIG_PATH = ROOT / "configs" / "budget.yaml"
logger = logging.getLogger(__name__)


class BudgetExceeded(Exception):
    """Raised when a cost limit would be breached by the next LLM call."""


def _load_config() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH) as f:
            return yaml.safe_load(f) or {}
    return {}


class CostGuard:
    """Thread-safe (within a single process) LLM spend tracker."""

    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or _load_config()
        llm = cfg.get("llm", {})
        self.daily_limit = float(llm.get("daily_limit_usd", 2.0))
        self.monthly_limit = float(llm.get("monthly_limit_usd", 50.0))
        self.max_calls_per_run = int(llm.get("max_calls_per_run", 5))
        cost_map = llm.get("cost_per_1k_tokens", {})
        self.cost_per_1k: dict[str, float] = {k: float(v) for k, v in cost_map.items()}
        ledger_rel = llm.get("ledger_path", "logs/llm_costs.jsonl")
        self.ledger_path = ROOT / ledger_rel
        self._run_calls = 0  # reset on process start

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def estimate_cost(self, model: str, n_tokens: int) -> float:
        """Estimate USD cost for `n_tokens` with `model`."""
        rate = self.cost_per_1k.get(model, 0.003)
        return rate * n_tokens / 1_000

    def check_and_record(
        self,
        model: str,
        n_tokens: int,
        agent_name: str = "",
        match: str = "",
    ) -> None:
        """Check budget limits, then append entry to ledger.

        Raises BudgetExceeded if any limit would be violated.
        """
        cost = self.estimate_cost(model, n_tokens)
        self._check_limits(cost)
        self._append_ledger(model, n_tokens, cost, agent_name, match)
        self._run_calls += 1

    def run_calls_remaining(self) -> int:
        return max(0, self.max_calls_per_run - self._run_calls)

    def daily_spent(self) -> float:
        return self._sum_ledger(period="day")

    def monthly_spent(self) -> float:
        return self._sum_ledger(period="month")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _check_limits(self, cost: float) -> None:
        if self._run_calls >= self.max_calls_per_run:
            raise BudgetExceeded(
                f"max_calls_per_run={self.max_calls_per_run} reached this run"
            )
        daily = self.daily_spent()
        if daily + cost > self.daily_limit:
            raise BudgetExceeded(
                f"Daily limit ${self.daily_limit:.2f} would be exceeded "
                f"(spent=${daily:.4f}, call=${cost:.4f})"
            )
        monthly = self.monthly_spent()
        if monthly + cost > self.monthly_limit:
            raise BudgetExceeded(
                f"Monthly limit ${self.monthly_limit:.2f} would be exceeded "
                f"(spent=${monthly:.4f}, call=${cost:.4f})"
            )

    def _append_ledger(
        self, model: str, n_tokens: int, cost: float, agent_name: str, match: str
    ) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "model": model,
            "tokens": n_tokens,
            "cost_usd": round(cost, 6),
            "agent": agent_name,
            "match": match,
        }
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        logger.debug("CostGuard: recorded $%.6f for %s (%s)", cost, agent_name, match)

    def _sum_ledger(self, period: str) -> float:
        """Sum costs from the ledger for 'day' or 'month'."""
        if not self.ledger_path.exists():
            return 0.0
        now = datetime.now(timezone.utc)
        total = 0.0
        try:
            with open(self.ledger_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                        ts = datetime.fromisoformat(entry["ts"])
                        if period == "day" and (
                            ts.year != now.year or ts.month != now.month or ts.day != now.day
                        ):
                            continue
                        if period == "month" and (
                            ts.year != now.year or ts.month != now.month
                        ):
                            continue
                        total += float(entry.get("cost_usd", 0.0))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
        except OSError:
            pass
        return total


# Process-level singleton — import and use directly
_guard: Optional[CostGuard] = None


def get_guard() -> CostGuard:
    global _guard
    if _guard is None:
        _guard = CostGuard()
    return _guard
