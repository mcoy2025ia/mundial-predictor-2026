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
from src.features import build_feature_matrix, compute_elo_ratings, get_tournament_weight, save_current_elo, save_features
from src.poisson_model import PoissonModel, evaluate_poisson
from src.model import (
    MODELS_DIR,
    confusion_matrix_dict,
    evaluate,
    save_metrics,
    save_model,
    temporal_split,
    train,
)
from src.pipeline_logger import run_context

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("pipeline")


def main() -> None:
    _artifacts = [
        ROOT / "data" / "processed" / "wc_clean.csv",
        ROOT / "data" / "processed" / "elo_current.json",
        ROOT / "data" / "processed" / "features.parquet",
        ROOT / "models" / "xgb_calibrated.pkl",
        ROOT / "models" / "poisson_model.pkl",
        ROOT / "data" / "processed" / "metrics.json",
    ]
    with run_context("full_pipeline", artifacts=_artifacts) as _ctx:
        _run(_ctx)


def _run(_ctx: dict) -> None:
    # 1. Carga + limpieza (nombres historicos normalizados en load_results)
    df_all = load_results()
    df_wc = add_outcome(filter_world_cups(df_all))
    df_wc_played = df_wc[df_wc["home_score"].notna()].copy()
    save_wc_clean(df_wc_played)

    # 2. ELO sobre todos los partidos internacionales
    _, ratings = compute_elo_ratings(df_all)
    save_current_elo(ratings)

    # 3. Feature matrix — todos los internacionales con peso por torneo
    df_features = build_feature_matrix(df_all, df_wc_played, use_all_matches=True)
    save_features(df_features)

    # 4. Entrenamiento + evaluacion
    # Split temporal: train < 2018 | calib = 2018 | test = partidos de WC 2022
    # El test siempre se evalúa solo sobre partidos de WC (comparación justa con baseline).
    train_df, calib_df, test_df_all = temporal_split(df_features, test_year=2022, calib_year=2018)
    test_df = test_df_all[test_df_all["tournament_weight"] == 1.0].copy()  # solo WC 2022
    logger.info("Test WC 2022: %d partidos (de %d totales en 2022)", len(test_df), len(test_df_all))

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

    # 5. Poisson model — entrenado sobre df_all con pesos de torneo
    df_all_tw = df_all.copy()
    if "tournament" in df_all_tw.columns:
        df_all_tw["tournament_weight"] = df_all_tw["tournament"].apply(get_tournament_weight)
    poisson = PoissonModel()
    poisson.fit(df_all_tw, weight_col="tournament_weight")
    poisson.save()
    # evaluate_poisson necesita datos raw; df_wc_played ya tiene home_score y outcome
    df_test_raw = df_wc_played[df_wc_played["date"].dt.year == 2022].copy()
    df_test_raw["elo_diff"] = 0.0  # simplificado; Poisson usa elo_diff como señal auxiliar
    df_test_raw["is_neutral"] = df_test_raw.get("neutral", True).fillna(True)
    poisson_metrics = evaluate_poisson(poisson, df_test_raw)
    poisson_metrics["model"] = "poisson"
    logger.info("Poisson — acc=%.3f | log_loss=%.3f | rps=%.4f (n=%d)",
                poisson_metrics.get("accuracy", 0), poisson_metrics.get("log_loss", 0),
                poisson_metrics.get("rps", 0), poisson_metrics.get("n_test", 0))

    # Registrar métricas en el contexto del logger
    xgb_m = metrics.get("xgb_calibrated", {})
    _ctx["metrics"] = {
        "xgb_rps": xgb_m.get("rps", 0),
        "xgb_accuracy": xgb_m.get("accuracy", 0),
        "xgb_log_loss": xgb_m.get("log_loss", 0),
        "poisson_rps": poisson_metrics.get("rps", 0),
        "n_train": xgb_m.get("n_train", 0),
        "n_test": xgb_m.get("n_test", 0),
    }
    _ctx["meta"] = {"n_all_matches": len(df_all), "n_wc_matches": len(df_wc_played)}
    logger.info("Pipeline completo. Artefactos regenerados en data/processed y models/")


if __name__ == "__main__":
    main()
