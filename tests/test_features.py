import pandas as pd
import numpy as np
import pytest

from src.features import (
    INITIAL_ELO,
    compute_elo_ratings,
    compute_h2h,
    compute_rolling_goals,
    compute_wc_experience,
    expected_score,
    update_elo,
)


# --- ELO ---

def test_expected_score_equal_ratings():
    assert expected_score(1500, 1500) == pytest.approx(0.5)


def test_expected_score_higher_rating_wins():
    assert expected_score(1600, 1500) > 0.5


def test_update_elo_increases_on_win():
    assert update_elo(1500, 0.5, 1.0) > 1500


def test_update_elo_decreases_on_loss():
    assert update_elo(1500, 0.5, 0.0) < 1500


def _make_results():
    return pd.DataFrame({
        "date": pd.to_datetime(["2020-01-01", "2020-06-01"]),
        "home_team": ["A", "B"],
        "away_team": ["B", "A"],
        "home_score": [2.0, 1.0],
        "away_score": [0.0, 2.0],
        "neutral": [False, False],
    })


def test_compute_elo_starts_at_initial():
    result, _ = compute_elo_ratings(_make_results())
    assert result.iloc[0]["elo_home"] == INITIAL_ELO
    assert result.iloc[0]["elo_away"] == INITIAL_ELO


def test_compute_elo_diff_column_exists():
    result, _ = compute_elo_ratings(_make_results())
    assert "elo_diff" in result.columns


def test_compute_elo_returns_ratings_dict():
    _, ratings = compute_elo_ratings(_make_results())
    assert isinstance(ratings, dict)
    assert "A" in ratings and "B" in ratings


def test_compute_elo_skips_nan_scores():
    df = _make_results().copy()
    df.loc[0, "home_score"] = float("nan")
    result, _ = compute_elo_ratings(df)
    assert result.iloc[0]["elo_home"] == INITIAL_ELO
    assert result.iloc[1]["elo_home"] == INITIAL_ELO  # A no actualizado por el NaN


# --- Rolling goals ---

def _make_all_and_wc():
    df_all = pd.DataFrame({
        "date": pd.to_datetime(["2010-01-01", "2010-03-01", "2014-06-01"]),
        "home_team": ["A", "A", "A"],
        "away_team": ["B", "C", "B"],
        "home_score": [2.0, 3.0, 1.0],
        "away_score": [1.0, 0.0, 0.0],
        "neutral": [False, False, True],
    })
    df_wc = df_all.iloc[[2]].copy()
    df_wc["outcome"] = "home_win"
    df_wc["year"] = 2014
    return df_all, df_wc


def test_rolling_goals_columns_added():
    df_all, df_wc = _make_all_and_wc()
    result = compute_rolling_goals(df_all, df_wc, n=5)
    assert "home_goals_scored_avg5" in result.columns
    assert "away_goals_scored_avg5" in result.columns
    assert "home_goals_conceded_avg5" in result.columns
    assert "away_goals_conceded_avg5" in result.columns


def test_rolling_goals_no_leakage():
    df_all, df_wc = _make_all_and_wc()
    result = compute_rolling_goals(df_all, df_wc, n=5)
    # Team A played 2 matches before the WC match: scored 2 and 3
    avg = result.iloc[0]["home_goals_scored_avg5"]
    assert avg == pytest.approx(2.5, abs=0.1)


def test_rolling_goals_no_nulls():
    df_all, df_wc = _make_all_and_wc()
    result = compute_rolling_goals(df_all, df_wc, n=5)
    assert result[["home_goals_scored_avg5", "away_goals_scored_avg5"]].isnull().sum().sum() == 0


# --- H2H ---

def _make_wc_h2h():
    return pd.DataFrame({
        "date": pd.to_datetime(["2010-06-01", "2014-06-01", "2018-06-01"]),
        "home_team": ["A", "A", "B"],
        "away_team": ["B", "B", "A"],
        "home_score": [2.0, 1.0, 1.0],
        "away_score": [0.0, 2.0, 0.0],
        "outcome": ["home_win", "away_win", "home_win"],
        "neutral": [True, True, True],
        "year": [2010, 2014, 2018],
    })


def test_h2h_first_match_default():
    df = _make_wc_h2h()
    result = compute_h2h(df)
    assert result.iloc[0]["h2h_home_win_pct"] == pytest.approx(0.5)


def test_h2h_updates_correctly():
    df = _make_wc_h2h()
    result = compute_h2h(df)
    # Segundo partido A vs B: A ganó 1 de 1 previo → 1.0
    assert result.iloc[1]["h2h_home_win_pct"] == pytest.approx(1.0)
    # Tercer partido B vs A: B ganó 1 (match 2, away_win) de 2 previos → 0.5
    assert result.iloc[2]["h2h_home_win_pct"] == pytest.approx(0.5)


# --- WC experience ---

def _make_wc_exp():
    return pd.DataFrame({
        "date": pd.to_datetime(["2014-06-01", "2014-06-05", "2018-06-01"]),
        "home_team": ["A", "B", "A"],
        "away_team": ["B", "C", "C"],
        "home_score": [1.0, 2.0, 1.0],
        "away_score": [0.0, 1.0, 0.0],
        "outcome": ["home_win", "home_win", "home_win"],
        "neutral": [True, True, True],
        "year": [2014, 2014, 2018],
    })


def test_wc_experience_first_match_zero():
    df = _make_wc_exp()
    result = compute_wc_experience(df)
    assert result.iloc[0]["wc_experience_diff"] == 0


def test_wc_experience_accumulates():
    df = _make_wc_exp()
    result = compute_wc_experience(df)
    # Tercer partido A(exp=1) vs C(exp=1) → diff=0
    assert result.iloc[2]["wc_experience_diff"] == 0
