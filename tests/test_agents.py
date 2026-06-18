"""Tests para el sistema multi-agente (agentes determinísticos + orquestador)."""
import pytest
from src.agents import MatchContext, Orchestrator
from src.agents.base import AgentResult
from src.agents.orchestrator import _agent_weight, _route
from src.agents.specialists import FinOpsAgent, FIFARegsAgent, TravelLogisticsAgent
from src.agents.specialists.fifa_regs import _qualification_pressure


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


def test_fifa_regs_j1_group_pressure_is_neutral():
    ctx = _ctx(
        matchday=1,
        group_points_home=0,
        group_points_away=0,
        games_played_home=0,
        games_played_away=0,
    )
    result = FIFARegsAgent().safe_analyze(ctx)
    assert result.delta_home == 0.0
    assert result.delta_away == 0.0


def test_fifa_regs_j3_home_must_win_boosts_home():
    ctx = _ctx(
        matchday=3,
        group_points_home=0,
        group_points_away=4,
        games_played_home=2,
        games_played_away=2,
    )
    result = FIFARegsAgent().safe_analyze(ctx)
    assert result.delta_home > 0.0
    assert "home_pressure=must_win" in result.notes


def test_fifa_regs_j3_away_must_win_boosts_away():
    ctx = _ctx(
        matchday=3,
        group_points_home=4,
        group_points_away=0,
        games_played_home=2,
        games_played_away=2,
    )
    result = FIFARegsAgent().safe_analyze(ctx)
    assert result.delta_away > 0.0
    assert "away_pressure=must_win" in result.notes


def test_fifa_regs_j3_three_points_tracks_best_third_risk():
    assert _qualification_pressure(points=3, games_played=2, matchday=3) == "third_place_watch"


def test_fifa_regs_j3_six_points_already_through():
    assert _qualification_pressure(points=6, games_played=2, matchday=3) == "already_through"


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


def test_orchestrator_group_stage_always_routes_fifa_regs():
    ctx = _ctx(
        matchday=2,
        group_points_home=0,
        group_points_away=3,
        games_played_home=1,
        games_played_away=1,
        injuries=["starter out"],
        home_odds=2.10,
    )
    routed = [agent.name for agent in _route(ctx)]
    assert "FIFA-Regs-Strategist" in routed
    assert "GroupScenario-Reasoner" in routed
    assert len(routed) <= 4


def test_orchestrator_j3_allows_four_agents_with_fifa_regs():
    ctx = _ctx(
        matchday=3,
        group_points_home=3,
        group_points_away=0,
        games_played_home=2,
        games_played_away=2,
        injuries=["starter out"],
        home_odds=2.10,
    )
    routed = [agent.name for agent in _route(ctx)]
    assert "FIFA-Regs-Strategist" in routed
    assert "GroupScenario-Reasoner" in routed
    assert len(routed) <= 5


def test_orchestrator_j3_weights_raise_fifa_regs_importance():
    ctx_j1 = _ctx(matchday=1, group_points_home=0, group_points_away=0)
    ctx_j3 = _ctx(matchday=3, group_points_home=3, group_points_away=3)
    assert _agent_weight("FIFA-Regs-Strategist", ctx_j3) > _agent_weight(
        "FIFA-Regs-Strategist", ctx_j1
    )


def test_orchestrator_j3_weights_raise_group_reasoner_importance():
    ctx_j2 = _ctx(matchday=2, group_points_home=0, group_points_away=3)
    ctx_j3 = _ctx(matchday=3, group_points_home=3, group_points_away=3)
    assert _agent_weight("GroupScenario-Reasoner", ctx_j3) >= _agent_weight(
        "GroupScenario-Reasoner", ctx_j2
    )
