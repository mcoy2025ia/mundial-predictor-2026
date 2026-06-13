"""Tests para PoissonModel y EnsembleModel."""
import numpy as np
import pandas as pd
import pytest

from src.poisson_model import MAX_GOALS, PoissonModel


def _mini_df(n: int = 200, seed: int = 42) -> pd.DataFrame:
    """DataFrame mínimo con partidos sintéticos para tests."""
    rng = np.random.default_rng(seed)
    teams = ["France", "Brazil", "Germany", "Argentina", "Spain", "England"]
    rows = []
    for _ in range(n):
        h, a = rng.choice(teams, 2, replace=False)
        rows.append({
            "home_team": h, "away_team": a,
            "home_score": int(rng.poisson(1.3)),
            "away_score": int(rng.poisson(1.1)),
            "tournament_weight": float(rng.choice([1.0, 0.6, 0.2])),
        })
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def fitted_model() -> PoissonModel:
    df = _mini_df(300)
    return PoissonModel().fit(df)


# ---------------------------------------------------------------------------
# Ajuste
# ---------------------------------------------------------------------------

def test_fit_populates_attack_defense(fitted_model):
    assert len(fitted_model.attack_) > 0
    assert len(fitted_model.defense_) > 0


def test_attack_defense_normalized(fitted_model):
    att_mean = np.mean(list(fitted_model.attack_.values()))
    def_mean = np.mean(list(fitted_model.defense_.values()))
    assert abs(att_mean - 1.0) < 0.05, f"Attack mean={att_mean:.4f} != 1.0"
    assert abs(def_mean - 1.0) < 0.05, f"Defense mean={def_mean:.4f} != 1.0"


def test_mean_goals_positive(fitted_model):
    assert fitted_model.mean_goals_home > 0
    assert fitted_model.mean_goals_away > 0


# ---------------------------------------------------------------------------
# predict_goals
# ---------------------------------------------------------------------------

def test_lambdas_positive(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("France", "Brazil")
    assert lam_h > 0, "lambda_home debe ser positivo"
    assert lam_a > 0, "lambda_away debe ser positivo"


def test_lambdas_unknown_team_fallback(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("Narnia", "Mordor")
    assert lam_h > 0
    assert lam_a > 0


def test_neutral_vs_nonneutral_lambdas(fitted_model):
    lam_n_h, lam_n_a = fitted_model.predict_goals("France", "Brazil", is_neutral=True)
    lam_h_h, lam_h_a = fitted_model.predict_goals("France", "Brazil", is_neutral=False)
    # En partido no neutral, el local debería tener mayor lambda
    assert lam_h_h >= lam_n_h


# ---------------------------------------------------------------------------
# scoreline_matrix
# ---------------------------------------------------------------------------

def test_matrix_shape(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("France", "Brazil")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    assert mat.shape == (MAX_GOALS + 1, MAX_GOALS + 1)


def test_matrix_sums_to_one(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("France", "Brazil")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    assert abs(mat.sum() - 1.0) < 1e-6


def test_matrix_all_non_negative(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("Germany", "Argentina")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    assert np.all(mat >= 0)


# ---------------------------------------------------------------------------
# top_scorelines
# ---------------------------------------------------------------------------

def test_top_scorelines_count(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("Spain", "England")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    top5 = fitted_model.top_scorelines(mat, n=5)
    assert len(top5) == 5


def test_top_scorelines_sorted(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("Spain", "England")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    top5 = fitted_model.top_scorelines(mat, n=5)
    probs = [s["prob"] for s in top5]
    assert probs == sorted(probs, reverse=True)


def test_top_scorelines_probs_positive(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("Brazil", "Germany")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    for s in fitted_model.top_scorelines(mat, n=5):
        assert s["prob"] > 0


# ---------------------------------------------------------------------------
# aggregate_1x2
# ---------------------------------------------------------------------------

def test_1x2_sums_to_one(fitted_model):
    lam_h, lam_a = fitted_model.predict_goals("France", "Germany")
    mat = fitted_model.scoreline_matrix(lam_h, lam_a)
    p_h, p_d, p_a = fitted_model.aggregate_1x2(mat)
    assert abs(p_h + p_d + p_a - 1.0) < 1e-4


def test_1x2_in_valid_range(fitted_model):
    for home, away in [("France", "Brazil"), ("Germany", "Argentina"), ("Spain", "England")]:
        lam_h, lam_a = fitted_model.predict_goals(home, away)
        mat = fitted_model.scoreline_matrix(lam_h, lam_a)
        for p in fitted_model.aggregate_1x2(mat):
            assert 0.0 <= p <= 1.0


def test_stronger_team_higher_win_prob(fitted_model):
    """Equipo con mayor ELO diff → mayor win_prob."""
    lam_h_str, lam_a_str = fitted_model.predict_goals(
        "France", "Brazil", elo_diff=300.0
    )
    lam_h_wk, lam_a_wk = fitted_model.predict_goals(
        "France", "Brazil", elo_diff=-300.0
    )
    mat_str = fitted_model.scoreline_matrix(lam_h_str, lam_a_str)
    mat_wk = fitted_model.scoreline_matrix(lam_h_wk, lam_a_wk)
    p_h_str, _, _ = fitted_model.aggregate_1x2(mat_str)
    p_h_wk, _, _ = fitted_model.aggregate_1x2(mat_wk)
    assert p_h_str > p_h_wk


# ---------------------------------------------------------------------------
# Ensemble
# ---------------------------------------------------------------------------

def test_ensemble_probs_sum_to_one(fitted_model):
    from src.ensemble import EnsembleModel
    ens = EnsembleModel(weights={"elo": 0.5, "poisson": 0.5, "xgb": 0.0})
    ens.poisson_model = fitted_model
    ens._fitted = True
    p_h, p_d, p_a = ens.predict_proba_match(
        "France", "Brazil", elo_home=2050, elo_away=1980, is_neutral=True
    )
    assert abs(p_h + p_d + p_a - 1.0) < 1e-4


def test_ensemble_probs_in_valid_range(fitted_model):
    from src.ensemble import EnsembleModel
    ens = EnsembleModel(weights={"elo": 0.5, "poisson": 0.5, "xgb": 0.0})
    ens.poisson_model = fitted_model
    ens._fitted = True
    p_h, p_d, p_a = ens.predict_proba_match(
        "Germany", "Argentina", elo_home=1900, elo_away=2000, is_neutral=True
    )
    for p in (p_h, p_d, p_a):
        assert 0.0 <= p <= 1.0
