import pandas as pd
import pytest

from src.simulator import (
    build_fixed_results,
    build_shootout_stats,
    shootout_win_prob,
    simulate_group,
)


@pytest.fixture
def df_shootouts():
    return pd.DataFrame({
        "date": pd.date_range("2000-01-01", periods=4),
        "home_team": ["Argentina", "Argentina", "England", "Brazil"],
        "away_team": ["England", "Brazil", "Colombia", "England"],
        "winner": ["Argentina", "Argentina", "Colombia", "Brazil"],
        "first_shooter": [None] * 4,
    })


def test_build_shootout_stats(df_shootouts):
    stats = build_shootout_stats(df_shootouts)
    assert stats["Argentina"] == {"wins": 2, "total": 2}
    assert stats["England"] == {"wins": 0, "total": 3}
    assert stats["Colombia"] == {"wins": 1, "total": 1}


def test_shootout_win_prob_favors_better_record(df_shootouts):
    stats = build_shootout_stats(df_shootouts)
    p = shootout_win_prob("Argentina", "England", stats)
    assert p > 0.5  # Argentina 2/2 vs England 0/3
    # simetría
    assert shootout_win_prob("England", "Argentina", stats) == pytest.approx(1 - p)


def test_shootout_win_prob_defaults_to_half(df_shootouts):
    stats = build_shootout_stats(df_shootouts)
    assert shootout_win_prob("Japan", "Morocco", stats) == 0.5
    assert shootout_win_prob("A", "B", None) == 0.5
    assert shootout_win_prob("A", "B", {}) == 0.5


def test_build_fixed_results_group_stage_only():
    matches = [
        {"group": "Group K", "team1": "Colombia", "team2": "Portugal", "score1": 2, "score2": 1},
        {"group": "Group K", "team1": "DR Congo", "team2": "Uzbekistan", "score1": 1, "score2": 1},
        {"group": "Group K", "team1": "Colombia", "team2": "Uzbekistan", "score1": None, "score2": None},
        {"round": "Round of 32", "team1": "Spain", "team2": "Chile", "score1": 3, "score2": 0},
    ]
    fixed = build_fixed_results(matches)
    assert fixed[frozenset(("Colombia", "Portugal"))] == "Colombia"
    assert fixed[frozenset(("DR Congo", "Uzbekistan"))] is None  # empate
    assert frozenset(("Colombia", "Uzbekistan")) not in fixed  # sin jugar
    assert frozenset(("Spain", "Chile")) not in fixed  # knockout no se fija


def test_simulate_group_respects_fixed_results():
    teams = ["A", "B", "C", "D"]
    # los 6 partidos fijados → no se necesita modelo
    fixed = {
        frozenset(("A", "B")): "A",
        frozenset(("A", "C")): "A",
        frozenset(("A", "D")): None,
        frozenset(("B", "C")): "B",
        frozenset(("B", "D")): "B",
        frozenset(("C", "D")): "C",
    }
    elos = {t: 1500.0 for t in teams}
    points, standing = simulate_group(
        teams, model=None, elo_ratings=elos, df_features=pd.DataFrame(),
        fixed_results=fixed,
    )
    assert points["A"] == 7 and points["B"] == 6 and points["C"] == 3 and points["D"] == 1
    assert standing[0] == "A" and standing[-1] == "D"
