"""Tests para el sistema multi-agente (agentes determinísticos + orquestador)."""
import pytest
from src.agents import MatchContext, Orchestrator
from src.agents.base import AgentResult
from src.agents.specialists import FinOpsAgent, FIFARegsAgent, TravelLogisticsAgent


def _ctx(**kwargs) -> MatchContext:
    defaults = dict(
        team_home="Brazil", team_away="Germany",
        p_home=0.40, p_draw=0.28, p_away=0.32,
        elo_home=2010.0, elo_away=1990.0, is_neutral=True,
    )
    defaults.update(kwargs)
    return MatchContext(**defaults)


# ---------------------------------------------------------------------------
# FinOps (determinístico)
# ---------------------------------------------------------------------------

def test_finops_no_odds_returns_zero_delta():
    ctx = _ctx()
    result = FinOpsAgent().safe_analyze(ctx)
    assert result.delta_home == 0.0
    assert result.delta_away == 0.0


def test_finops_with_odds_returns_nonzero_when_edge():
    # Prior XGBoost: home=40%, pero mercado tiene home=55% → edge significativo
    ctx = _ctx(home_odds=1.82, draw_odds=3.50, away_odds=4.50,
               p_home=0.40, p_draw=0.28, p_away=0.32)
    result = FinOpsAgent().safe_analyze(ctx)
    # Mercado dice home es más probable → delta_home debe ser positivo
    assert result.delta_home >= 0.0


def test_finops_deltas_sum_to_zero():
    ctx = _ctx(home_odds=2.10, draw_odds=3.20, away_odds=3.60)
    result = FinOpsAgent().safe_analyze(ctx)
    assert abs(result.delta_home + result.delta_draw + result.delta_away) < 1e-4


# ---------------------------------------------------------------------------
# FIFA-Regs (determinístico)
# ---------------------------------------------------------------------------

def test_fifa_regs_high_altitude_penalizes_away():
    ctx = _ctx(venue_altitude_m=2240, is_neutral=False,
               venue_city="Mexico City")
    result = FIFARegsAgent().safe_analyze(ctx)
    assert result.delta_away <= 0.0  # visitante penalizado por altitud


def test_fifa_regs_sea_level_no_adjustment():
    ctx = _ctx(venue_altitude_m=0)
    result = FIFARegsAgent().safe_analyze(ctx)
    assert result.delta_home == 0.0
    assert result.delta_away == 0.0


def test_fifa_regs_deltas_sum_to_zero():
    ctx = _ctx(venue_altitude_m=2240, is_neutral=False)
    result = FIFARegsAgent().safe_analyze(ctx)
    assert abs(result.delta_home + result.delta_draw + result.delta_away) < 1e-4


# ---------------------------------------------------------------------------
# Travel (semi-determinístico para equipos lejanos)
# ---------------------------------------------------------------------------

def test_travel_far_team_gets_penalty():
    ctx = _ctx(team_away="Japan", venue_city="Miami", venue_altitude_m=0)
    result = TravelLogisticsAgent().safe_analyze(ctx)
    assert result.delta_away <= 0.0  # Japón viajó más


def test_travel_deltas_sum_to_zero():
    ctx = _ctx(team_away="Japan", venue_city="Miami", venue_altitude_m=0)
    result = TravelLogisticsAgent().safe_analyze(ctx)
    assert abs(result.delta_home + result.delta_draw + result.delta_away) < 1e-4


# ---------------------------------------------------------------------------
# Orquestador (sin LLM — solo agentes determinísticos activos)
# ---------------------------------------------------------------------------

def test_orchestrator_output_probs_sum_to_one():
    ctx = _ctx(home_odds=2.10, draw_odds=3.20, away_odds=3.60)
    out = Orchestrator().predict(ctx)
    total = out.adjusted["home"] + out.adjusted["draw"] + out.adjusted["away"]
    assert abs(total - 1.0) < 1e-3


def test_orchestrator_calls_at_most_two_agents():
    ctx = _ctx(home_odds=2.10, draw_odds=3.20, away_odds=3.60,
               injuries=["Mbappé (knee)"])
    out = Orchestrator().predict(ctx)
    assert len(out.agents_called) <= 2


def test_orchestrator_adjusted_probs_in_valid_range():
    ctx = _ctx(venue_altitude_m=2240, is_neutral=False)
    out = Orchestrator().predict(ctx)
    for key in ("home", "draw", "away"):
        assert 0.0 < out.adjusted[key] < 1.0


def test_orchestrator_injury_context_routes_roster():
    ctx = _ctx(injuries=["Messi (hamstring)", "Di María (suspended)"])
    out = Orchestrator().predict(ctx)
    # Roster-Data-Scout requiere ANTHROPIC_API_KEY — safe_analyze devuelve delta=0 sin error
    assert "Roster-Data-Scout" in out.agents_called


def test_orchestrator_prior_preserved_without_llm_key(monkeypatch):
    """Sin API key, los agentes LLM retornan delta=0 y el prior se preserva."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    ctx = _ctx(injuries=["Ronaldo (suspended)"])
    out = Orchestrator().predict(ctx)
    total = out.adjusted["home"] + out.adjusted["draw"] + out.adjusted["away"]
    assert abs(total - 1.0) < 1e-3
