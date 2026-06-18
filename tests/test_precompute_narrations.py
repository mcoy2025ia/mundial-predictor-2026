"""Tests for precomputed narration payloads."""
from scripts.precompute_narrations import _build_user_payload


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
