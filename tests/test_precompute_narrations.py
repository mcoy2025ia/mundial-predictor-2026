"""Tests for precomputed narration payloads."""
from scripts.precompute_narrations import (
    _build_group_narrative_payload,
    _build_user_payload,
    _kickoff_date,
    _model_for_group_narrative,
)


def test_build_user_payload_includes_competitive_context():
    match = {
        "home_team": "Colombia",
        "away_team": "Portugal",
        "group": "K",
        "round": "Matchday 13",
        "venue": "Houston",
        "kickoff": "2026-06-23T20:00:00",
        "p_home": 0.41,
        "p_draw": 0.27,
        "p_away": 0.32,
        "agent_notes": {"FIFA-Regs-Strategist": "home_pressure=needs_result"},
        "group_context": {
            "group_name": "Group K",
            "matchday": 2,
            "home_points": 1,
            "away_points": 3,
            "home_games_played": 1,
            "away_games_played": 1,
            "group_standings": "1.Portugal 3pts 2.Colombia 1pts",
            "simultaneous_group_matches": "",
            "third_place_context": "best_third_cutline=H:Team 3pts GD+0 GF2",
        },
    }
    teams = {
        "Colombia": {"elo": 1750, "wc_matches": 25, "goals_scored": 1.4},
        "Portugal": {"elo": 1850, "wc_matches": 35, "goals_scored": 1.6},
    }

    payload = _build_user_payload(match, teams, "bogotano", [])

    assert payload["competitive_context"]["matchday"] == 2
    assert payload["competitive_context"]["home_points"] == 1
    assert "best_third_cutline=" in payload["competitive_context"]["third_place_context"]


def test_build_group_narrative_payload_keeps_group_context():
    matches = [
        {
            "home_team": "Colombia",
            "away_team": "DR Congo",
            "group": "Group K",
            "round": "Matchday 13",
            "venue": "Miami",
            "kickoff": "2026-06-23T18:00:00",
            "p_home": 0.48,
            "p_draw": 0.27,
            "p_away": 0.25,
            "is_neutral": True,
            "model": "ensemble_live",
            "agent_notes": {"GroupScenario-Reasoner": "home_pressure=win_desired"},
            "group_context": {
                "group_name": "Group K",
                "matchday": 2,
                "group_standings": "1.Portugal 3pts 2.Colombia 1pts",
                "simultaneous_group_matches": "",
                "third_place_context": "best_third_cutline=H:Team 3pts GD+0 GF2",
            },
        }
    ]
    standings = [
        {"team": "Portugal", "pts": 3, "P": 1, "W": 1, "D": 0, "L": 0, "GF": 2, "GA": 0, "GD": 2},
        {"team": "Colombia", "pts": 1, "P": 1, "W": 0, "D": 1, "L": 0, "GF": 1, "GA": 1, "GD": 0},
    ]

    payload = _build_group_narrative_payload("Group K", "2026-06-23", matches, standings)

    assert payload["agent"] == "GroupNarrative-Preview"
    assert payload["group"] == "K"
    assert payload["matchday"] == 2
    assert payload["matches"][0]["prob_home"] == 48.0
    assert payload["matches"][0]["kickoff_bogota"] == "2026-06-23 13:00"
    assert payload["actual_standings"][0]["team"] == "Portugal"
    assert payload["missing_data_policy"].startswith("If emotional momentum")


def test_group_narrative_uses_reasoner_for_matchday_three():
    payload = {
        "matchday": 3,
        "competitive_context": {
            "third_place_context": "",
            "simultaneous_group_matches": "Colombia vs Portugal; DR Congo vs Uzbekistan",
        },
    }

    assert _model_for_group_narrative(payload) == "deepseek-reasoner"


def test_group_narrative_uses_chat_for_simple_matchday_two():
    payload = {"matchday": 2, "competitive_context": {}}

    assert _model_for_group_narrative(payload) == "deepseek-chat"


def test_group_narrative_date_uses_bogota_day():
    match = {"kickoff": "2026-06-19T01:00:00+00:00"}

    assert _kickoff_date(match) == "2026-06-18"
