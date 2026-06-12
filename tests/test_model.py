import numpy as np
import pandas as pd
import pytest

from src.model import (
    FEATURE_COLS, LABEL_MAP, LABEL_NAMES,
    build_baseline, build_xgb_pipeline,
    temporal_split, train, evaluate,
)


def _make_features(n_per_year: int = 20):
    rng = np.random.default_rng(42)
    rows = []
    for year in [2014, 2018, 2022]:
        for _ in range(n_per_year):
            rows.append({
                "year": year,
                "elo_diff": rng.normal(0, 100),
                "elo_home": 1500.0,
                "elo_away": 1500.0,
                "home_goals_scored_avg5": rng.uniform(0.5, 3.0),
                "home_goals_conceded_avg5": rng.uniform(0.5, 2.0),
                "away_goals_scored_avg5": rng.uniform(0.5, 3.0),
                "away_goals_conceded_avg5": rng.uniform(0.5, 2.0),
                "h2h_home_win_pct": 0.5,
                "is_neutral": 1,
                "wc_experience_diff": 0,
                "outcome": rng.choice(list(LABEL_MAP.keys())),
            })
    return pd.DataFrame(rows)


# --- Split temporal ---

def test_temporal_split_no_leakage():
    df = _make_features()
    train, test = temporal_split(df, test_year=2022)
    assert train["year"].max() < 2022
    assert (test["year"] == 2022).all()


def test_temporal_split_sizes():
    df = _make_features()
    train, test = temporal_split(df, test_year=2022)
    assert len(train) + len(test) == len(df)


# --- Label map ---

def test_label_map_covers_all_outcomes():
    assert set(LABEL_MAP.keys()) == {"home_win", "draw", "away_win"}
    assert set(LABEL_MAP.values()) == {0, 1, 2}


def test_label_names_is_inverse():
    for k, v in LABEL_MAP.items():
        assert LABEL_NAMES[v] == k


# --- Pipelines ---

def test_baseline_pipeline_fits_and_predicts():
    df = _make_features()
    train_df, test_df = temporal_split(df, test_year=2022)
    model = build_baseline()
    model.fit(train_df[FEATURE_COLS], train_df["outcome"].map(LABEL_MAP))
    preds = model.predict(test_df[FEATURE_COLS])
    assert len(preds) == len(test_df)
    assert set(preds).issubset({0, 1, 2})


def test_xgb_pipeline_predict_proba_sums_to_one():
    df = _make_features()
    train_df, test_df = temporal_split(df, test_year=2022)
    model = build_xgb_pipeline()
    model.fit(train_df[FEATURE_COLS], train_df["outcome"].map(LABEL_MAP))
    probas = model.predict_proba(test_df[FEATURE_COLS])
    assert probas.shape == (len(test_df), 3)
    np.testing.assert_allclose(probas.sum(axis=1), 1.0, atol=1e-5)


# --- evaluate() ---

def test_evaluate_returns_required_keys():
    df = _make_features()
    train_df, test_df = temporal_split(df, test_year=2022)
    model = train(train_df, model_type="baseline")
    metrics = evaluate(model, test_df, model_name="test_model")
    assert "test_model" in metrics
    m = metrics["test_model"]
    assert "accuracy" in m
    assert "log_loss" in m
    assert "brier_mean" in m


def test_evaluate_accuracy_in_range():
    df = _make_features()
    train_df, test_df = temporal_split(df, test_year=2022)
    model = train(train_df, model_type="baseline")
    metrics = evaluate(model, test_df, model_name="test_model")
    acc = metrics["test_model"]["accuracy"]
    assert 0.0 <= acc <= 1.0
