"""
Walk-forward validation con métrica RPS (Ranked Probability Score).

Folds: train<2006→test 2006, …, train<2022→test 2022
Compara cuatro modelos: ELO-only | Poisson | XGBoost calibrado | Ensemble (ELO+Poisson+XGB)

Uso: python scripts/walk_forward_validation.py
"""
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import add_outcome, filter_world_cups, load_results, save_wc_clean
from src.ensemble import DEFAULT_WEIGHTS
from src.features import HOME_ADVANTAGE_ELO, build_feature_matrix, compute_elo_ratings, expected_score
from src.model import FEATURE_COLS, LABEL_MAP, WEIGHT_COL, build_xgb_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("walk_forward")

WC_TEST_YEARS = [2006, 2010, 2014, 2018, 2022]


def rps_single(y_true_label: int, proba: np.ndarray) -> float:
    k = len(proba)
    obs = np.zeros(k)
    obs[y_true_label] = 1.0
    cum_pred = np.cumsum(proba)
    cum_obs = np.cumsum(obs)
    return float(np.sum((cum_pred[:-1] - cum_obs[:-1]) ** 2) / (k - 1))


def elo_only_proba(elo_home: float, elo_away: float, is_neutral: int) -> np.ndarray:
    """ELO-only baseline con draw fraction dinámica."""
    adj = 0.0 if is_neutral else HOME_ADVANTAGE_ELO
    p_home_raw = expected_score(elo_home + adj, elo_away)
    draw_frac = 0.28 * (1 - abs(p_home_raw - 0.5) * 1.6)
    draw_frac = max(0.08, min(draw_frac, 0.36))
    p_home = p_home_raw * (1 - draw_frac)
    p_away = (1 - p_home_raw) * (1 - draw_frac)
    total = p_home + draw_frac + p_away
    return np.array([p_home, draw_frac, p_away]) / total


def run_walk_forward(df_features: pd.DataFrame, df_all: pd.DataFrame) -> dict:
    results = {}
    all_rps: dict[str, list] = {"elo": [], "poisson": [], "xgb": [], "ensemble": []}

    for test_year in WC_TEST_YEARS:
        train_df = df_features[df_features["year"] < test_year].copy()
        test_mask = (df_features["year"] == test_year)
        if "tournament_weight" in df_features.columns:
            test_mask &= (df_features["tournament_weight"] == 1.0)
        test_df = df_features[test_mask].copy()

        if len(train_df) < 50 or len(test_df) == 0:
            logger.warning("Fold %d: datos insuficientes (train=%d, test=%d)",
                           test_year, len(train_df), len(test_df))
            continue

        # ── XGBoost ──────────────────────────────────────────────────────────
        from sklearn.calibration import CalibratedClassifierCV
        from sklearn.model_selection import TimeSeriesSplit

        X_train = train_df[FEATURE_COLS]
        y_train = train_df["outcome"].map(LABEL_MAP)
        sw = train_df[WEIGHT_COL].to_numpy(float) if WEIGHT_COL in train_df.columns else None
        tss = TimeSeriesSplit(n_splits=3)
        xgb_model = CalibratedClassifierCV(build_xgb_pipeline(), cv=tss, method="sigmoid")
        fit_params = {"xgb__sample_weight": sw} if sw is not None else {}
        xgb_model.fit(X_train, y_train, **fit_params)

        X_test = test_df[FEATURE_COLS]
        y_test = test_df["outcome"].map(LABEL_MAP).to_numpy()
        proba_xgb = xgb_model.predict_proba(X_test)

        # ── Poisson ──────────────────────────────────────────────────────────
        from src.poisson_model import PoissonModel

        poisson_model = PoissonModel()
        # Entrenar Poisson solo con partidos anteriores al WC de test
        df_train_raw = df_all[df_all["date"].dt.year < test_year].copy()
        poisson_model.fit(df_train_raw, weight_col=None)  # sin tournament_weight en raw

        proba_poisson = []
        for _, row in test_df.iterrows():
            try:
                lam_h, lam_a = poisson_model.predict_goals(
                    row["home_team"], row["away_team"],
                    is_neutral=bool(row.get("is_neutral", True)),
                    elo_diff=float(row.get("elo_diff", 0.0)),
                )
                mat = poisson_model.scoreline_matrix(lam_h, lam_a)
                p_h, p_d, p_a = poisson_model.aggregate_1x2(mat)
                proba_poisson.append(np.array([p_h, p_d, p_a]))
            except Exception:
                proba_poisson.append(np.array([1 / 3, 1 / 3, 1 / 3]))

        # ── ELO y Ensemble ───────────────────────────────────────────────────
        fold_rps: dict[str, list] = {"elo": [], "poisson": [], "xgb": [], "ensemble": []}

        for i in range(len(y_test)):
            row = test_df.iloc[i]
            p_elo = elo_only_proba(
                float(row["elo_home"]), float(row["elo_away"]), int(row["is_neutral"])
            )
            p_poi = proba_poisson[i]
            p_xgb = proba_xgb[i]

            p_ens = (
                DEFAULT_WEIGHTS["elo"] * p_elo
                + DEFAULT_WEIGHTS["poisson"] * p_poi
                + DEFAULT_WEIGHTS["xgb"] * p_xgb
            )
            p_ens /= p_ens.sum()

            fold_rps["elo"].append(rps_single(y_test[i], p_elo))
            fold_rps["poisson"].append(rps_single(y_test[i], p_poi))
            fold_rps["xgb"].append(rps_single(y_test[i], p_xgb))
            fold_rps["ensemble"].append(rps_single(y_test[i], p_ens))

        mean_r = {k: float(np.mean(v)) for k, v in fold_rps.items()}
        for k in all_rps:
            all_rps[k].extend(fold_rps[k])

        best = min(mean_r, key=mean_r.get)
        results[str(test_year)] = {
            "n_train": len(train_df),
            "n_test": len(test_df),
            **{f"rps_{k}": round(v, 4) for k, v in mean_r.items()},
            "best_model": best,
        }
        logger.info(
            "WC %d | ELO=%.4f Poisson=%.4f XGB=%.4f Ensemble=%.4f → MEJOR: %s",
            test_year, mean_r["elo"], mean_r["poisson"],
            mean_r["xgb"], mean_r["ensemble"], best.upper(),
        )

    overall = {k: float(np.mean(v)) if v else 0.0 for k, v in all_rps.items()}
    best_overall = min(overall, key=overall.get)
    results["overall"] = {
        **{f"rps_{k}": round(v, 4) for k, v in overall.items()},
        "best_model": best_overall,
        "n_predictions": len(all_rps["elo"]),
    }
    logger.info(
        "OVERALL | ELO=%.4f Poisson=%.4f XGB=%.4f Ensemble=%.4f → MEJOR: %s",
        overall["elo"], overall["poisson"], overall["xgb"], overall["ensemble"],
        best_overall.upper(),
    )
    return results


def main() -> None:
    df_all = load_results()
    df_wc = add_outcome(filter_world_cups(df_all))
    df_wc_played = df_wc[df_wc["home_score"].notna()].copy()
    save_wc_clean(df_wc_played)
    compute_elo_ratings(df_all)

    df_features = build_feature_matrix(df_all, df_wc_played, use_all_matches=True)
    logger.info("Feature matrix: %d filas", len(df_features))

    results = run_walk_forward(df_features, df_all)

    out_path = ROOT / "data" / "processed" / "walk_forward_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("Resultados guardados en %s", out_path)

    print("\n=== Walk-Forward Validation (5 Mundiales, 64 partidos c/u) ===")
    print(f"{'Año':>6} {'ELO':>8} {'Poisson':>9} {'XGB':>8} {'Ensemble':>10} {'Mejor':>10}")
    print("-" * 60)
    for year in [str(y) for y in WC_TEST_YEARS]:
        if year not in results:
            continue
        r = results[year]
        print(f"{year:>6} {r['rps_elo']:>8.4f} {r['rps_poisson']:>9.4f} "
              f"{r['rps_xgb']:>8.4f} {r['rps_ensemble']:>10.4f} {r['best_model']:>10}")
    r = results.get("overall", {})
    print("-" * 60)
    print(f"{'TOTAL':>6} {r.get('rps_elo',0):>8.4f} {r.get('rps_poisson',0):>9.4f} "
          f"{r.get('rps_xgb',0):>8.4f} {r.get('rps_ensemble',0):>10.4f} "
          f"{r.get('best_model','?'):>10}  (n={r.get('n_predictions',0)})")


if __name__ == "__main__":
    main()
