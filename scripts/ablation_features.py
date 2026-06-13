"""
Ablation test: ¿los días de descanso mejoran el RPS del XGB?

Compara XGB calibrado con:
  - FEATURE_COLS base (10 features actuales)
  - FEATURE_COLS + home_days_rest + away_days_rest

La feature entra en FEATURE_COLS solo si mejora el RPS global en walk-forward.

Uso: python scripts/ablation_features.py
"""
import logging
import sys
from pathlib import Path
from typing import List

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.model_selection import TimeSeriesSplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import add_outcome, filter_world_cups, load_results, save_wc_clean
from src.features import build_feature_matrix, compute_elo_ratings
from src.model import FEATURE_COLS, LABEL_MAP, WEIGHT_COL, build_xgb_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("ablation")

WC_TEST_YEARS = [2006, 2010, 2014, 2018, 2022]

CANDIDATE_COLS = ["home_days_rest", "away_days_rest"]


def rps_single(y_true_label: int, proba: np.ndarray) -> float:
    k = len(proba)
    obs = np.zeros(k)
    obs[y_true_label] = 1.0
    cum_pred = np.cumsum(proba)
    cum_obs = np.cumsum(obs)
    return float(np.sum((cum_pred[:-1] - cum_obs[:-1]) ** 2) / (k - 1))


def run_fold(df_features: pd.DataFrame, test_year: int, feature_cols: List[str]) -> float:
    """Entrena XGB calibrado en un fold y retorna RPS medio sobre WC de test_year."""
    train_df = df_features[df_features["year"] < test_year].copy()
    test_mask = (df_features["year"] == test_year)
    if "tournament_weight" in df_features.columns:
        test_mask &= (df_features["tournament_weight"] == 1.0)
    test_df = df_features[test_mask].copy()

    if len(train_df) < 50 or len(test_df) == 0:
        return float("nan")

    X_train = train_df[feature_cols]
    y_train = train_df["outcome"].map(LABEL_MAP)
    sw = train_df[WEIGHT_COL].to_numpy(float) if WEIGHT_COL in train_df.columns else None

    tss = TimeSeriesSplit(n_splits=3)
    model = CalibratedClassifierCV(build_xgb_pipeline(), cv=tss, method="sigmoid")
    fit_params = {"xgb__sample_weight": sw} if sw is not None else {}
    model.fit(X_train, y_train, **fit_params)

    X_test = test_df[feature_cols]
    y_test = test_df["outcome"].map(LABEL_MAP).to_numpy()
    proba = model.predict_proba(X_test)

    return float(np.mean([rps_single(int(y_test[i]), proba[i]) for i in range(len(y_test))]))


def main() -> None:
    df_all = load_results()
    df_wc = add_outcome(filter_world_cups(df_all))
    df_wc_played = df_wc[df_wc["home_score"].notna()].copy()
    save_wc_clean(df_wc_played)
    compute_elo_ratings(df_all)

    df_features = build_feature_matrix(df_all, df_wc_played, use_all_matches=True)
    logger.info("Feature matrix: %d filas, columnas=%s", len(df_features), list(df_features.columns))

    # Verificar que las columnas candidatas existen
    missing = [c for c in CANDIDATE_COLS if c not in df_features.columns]
    if missing:
        logger.error("Columnas candidatas no encontradas: %s", missing)
        sys.exit(1)

    base_cols = FEATURE_COLS
    augmented_cols = FEATURE_COLS + CANDIDATE_COLS

    print(f"\n=== Ablation: días de descanso (home_days_rest, away_days_rest) ===")
    print(f"{'Año':>6} {'Base RPS':>10} {'Aug RPS':>10} {'Delta':>8} {'Ganador':>10}")
    print("-" * 55)

    base_all, aug_all = [], []
    for year in WC_TEST_YEARS:
        rps_base = run_fold(df_features, year, base_cols)
        rps_aug = run_fold(df_features, year, augmented_cols)
        delta = rps_aug - rps_base
        winner = "AUG" if rps_aug < rps_base else ("BASE" if rps_base < rps_aug else "EMPATE")
        if not np.isnan(rps_base):
            base_all.append(rps_base)
        if not np.isnan(rps_aug):
            aug_all.append(rps_aug)
        print(f"{year:>6} {rps_base:>10.4f} {rps_aug:>10.4f} {delta:>+8.4f} {winner:>10}")

    print("-" * 55)
    overall_base = float(np.mean(base_all)) if base_all else float("nan")
    overall_aug = float(np.mean(aug_all)) if aug_all else float("nan")
    overall_delta = overall_aug - overall_base
    overall_winner = "AUG" if overall_aug < overall_base else "BASE"
    print(f"{'TOTAL':>6} {overall_base:>10.4f} {overall_aug:>10.4f} {overall_delta:>+8.4f} {overall_winner:>10}")

    print()
    if overall_aug < overall_base:
        print("✓ RESULTADO: las features de descanso MEJORAN el RPS global.")
        print("  → Actualizar FEATURE_COLS en src/model.py para incluirlas.")
    else:
        print("✗ RESULTADO: las features de descanso NO mejoran el RPS global.")
        print("  → Mantener FEATURE_COLS actual sin cambios.")

    print(f"\nBaseline FEATURE_COLS ({len(base_cols)} features): {base_cols}")
    print(f"Augmented    ({len(augmented_cols)} features): {augmented_cols}")


if __name__ == "__main__":
    main()
