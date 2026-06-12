"""
Pipeline end-to-end: datos raw -> features -> modelos -> metricas.
Regenera todos los artefactos derivados con nombres de equipo normalizados.

Uso: python scripts/run_pipeline.py
"""
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import add_outcome, filter_world_cups, load_results, save_wc_clean
from src.features import build_feature_matrix, compute_elo_ratings, save_current_elo, save_features
from src.model import (
    MODELS_DIR,
    confusion_matrix_dict,
    evaluate,
    save_metrics,
    save_model,
    temporal_split,
    train,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


def main() -> None:
    # 1. Carga + limpieza (nombres historicos normalizados en load_results)
    df_all = load_results()
    df_wc = add_outcome(filter_world_cups(df_all))
    df_wc_played = df_wc[df_wc["home_score"].notna()].copy()
    save_wc_clean(df_wc_played)

    # 2. ELO sobre todos los partidos internacionales
    _, ratings = compute_elo_ratings(df_all)
    save_current_elo(ratings)

    # 3. Feature matrix (solo partidos de Mundial ya jugados)
    df_features = build_feature_matrix(df_all, df_wc_played)
    save_features(df_features)

    # 4. Entrenamiento + evaluacion
    # Split temporal: train < 2018 | calib = 2018 (holdout para calibración) | test = 2022
    train_df, calib_df, test_df = temporal_split(df_features, test_year=2022, calib_year=2018)

    metrics = {}
    for name, mtype, fname in [
        ("logistic_regression", "baseline", None),
        ("xgb_v1", "xgb", "xgb_v1.pkl"),
        ("xgb_calibrated", "xgb_calibrated", "xgb_calibrated.pkl"),
    ]:
        # xgb_calibrated usa holdout temporal para calibración (sin KFold aleatorio)
        calib_arg = calib_df if mtype == "xgb_calibrated" else None
        model = train(train_df, model_type=mtype, df_calib=calib_arg)
        m = evaluate(model, test_df, model_name=name)
        m[name]["n_train"] = len(train_df)
        m[name]["n_calib"] = len(calib_df) if calib_arg is not None else 0
        metrics.update(m)
        if fname:
            save_model(model, MODELS_DIR / fname)
        if name == "xgb_calibrated":
            metrics[name]["confusion_matrix"] = confusion_matrix_dict(model, test_df)

    save_metrics(metrics)
    logger.info("Pipeline completo. Artefactos regenerados en data/processed y models/")


if __name__ == "__main__":
    main()
