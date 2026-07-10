"""Tests para la resolución del bracket de eliminatorias (src/bracket.py)."""
import pandas as pd
import pytest

from src.bracket import (
    final_standings,
    best_thirds,
    group_membership,
    resolve_bracket,
)


@pytest.fixture
def mini_fixture():
    """Fixture sintético: 2 grupos (A, B) + 1 cruce de eliminatorias."""
    return {
        "matches": [
            # Grupo A
            {"round": "Matchday 1", "group": "Group A", "num": 1, "team1": "Mexico",  "team2": "Korea",  "date": "2026-06-11", "time": "20:00 UTC+0", "ground": "X"},
            {"round": "Matchday 2", "group": "Group A", "num": 2, "team1": "Mexico",  "team2": "Czechia","date": "2026-06-14", "time": "20:00 UTC+0", "ground": "X"},
            {"round": "Matchday 3", "group": "Group A", "num": 3, "team1": "Korea",   "team2": "Czechia","date": "2026-06-17", "time": "20:00 UTC+0", "ground": "X"},
            # Grupo B
            {"round": "Matchday 1", "group": "Group B", "num": 4, "team1": "Brazil",  "team2": "Japan",  "date": "2026-06-12", "time": "20:00 UTC+0", "ground": "Y"},
            {"round": "Matchday 2", "group": "Group B", "num": 5, "team1": "Brazil",  "team2": "Sweden", "date": "2026-06-15", "time": "20:00 UTC+0", "ground": "Y"},
            {"round": "Matchday 3", "group": "Group B", "num": 6, "team1": "Japan",   "team2": "Sweden", "date": "2026-06-18", "time": "20:00 UTC+0", "ground": "Y"},
            # Cruce: 1A vs 2B
            {"round": "Round of 16", "num": 50, "team1": "1A", "team2": "2B", "date": "2026-06-28", "time": "20:00 UTC+0", "ground": "Z"},
        ]
    }


@pytest.fixture
def mini_results():
    """Resultados: Mexico gana A; Brazil 1º / Japan 2º de B."""
    return pd.DataFrame([
        {"home_team": "Mexico", "away_team": "Korea",   "home_score": 2, "away_score": 0},
        {"home_team": "Mexico", "away_team": "Czechia", "home_score": 1, "away_score": 0},
        {"home_team": "Korea",  "away_team": "Czechia", "home_score": 1, "away_score": 1},
        {"home_team": "Brazil", "away_team": "Japan",   "home_score": 1, "away_score": 0},
        {"home_team": "Brazil", "away_team": "Sweden",  "home_score": 3, "away_score": 0},
        {"home_team": "Japan",  "away_team": "Sweden",  "home_score": 2, "away_score": 1},
    ])


def test_group_membership(mini_fixture):
    mem = group_membership(mini_fixture)
    assert mem["Mexico"] == "A"
    assert mem["Brazil"] == "B"
    assert "1A" not in mem  # los placeholders de eliminatorias no son grupos


def test_final_standings_order(mini_fixture, mini_results):
    mem = group_membership(mini_fixture)
    st = final_standings(mini_results, mem)
    # Grupo A: Mexico 6pts (1º), Korea/Czechia detrás
    assert st["A"][0]["team"] == "Mexico"
    assert st["A"][0]["pts"] == 6
    # Grupo B: Brazil 6pts (1º), Japan 3pts (2º), Sweden 0 (3º)
    assert st["B"][0]["team"] == "Brazil"
    assert st["B"][1]["team"] == "Japan"
    assert st["B"][2]["team"] == "Sweden"


def test_resolve_bracket_positions(mini_fixture, mini_results):
    resolved = resolve_bracket(mini_fixture, mini_results)
    slot = resolved[50]
    assert slot["resolved"] is True
    assert slot["home"] == "Mexico"   # 1A
    assert slot["away"] == "Japan"    # 2B


def test_resolve_bracket_unplayed_stays_unresolved(mini_fixture):
    """Sin resultados, los cruces por posición no son determinables."""
    empty = pd.DataFrame(columns=["home_team", "away_team", "home_score", "away_score"])
    resolved = resolve_bracket(mini_fixture, empty)
    assert resolved[50]["resolved"] is False
    assert resolved[50]["home"] is None


def test_best_thirds_ranks_by_points_then_gd():
    standings = {
        "A": [{"team": "a1", "pos": 1}, {"team": "a2", "pos": 2},
              {"team": "A3", "pos": 3, "pts": 4, "gd": 1, "gf": 3}],
        "B": [{"team": "b1", "pos": 1}, {"team": "b2", "pos": 2},
              {"team": "B3", "pos": 3, "pts": 4, "gd": 3, "gf": 5}],
        "C": [{"team": "c1", "pos": 1}, {"team": "c2", "pos": 2},
              {"team": "C3", "pos": 3, "pts": 1, "gd": -2, "gf": 1}],
    }
    thirds = best_thirds(standings)
    # B3 (gd+3) por delante de A3 (gd+1); ambos clasifican, C3 también (top 8)
    assert thirds["B"] == "B3"
    assert thirds["A"] == "A3"
    assert "C" in thirds
