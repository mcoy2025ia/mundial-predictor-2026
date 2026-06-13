"""Entrenamiento, evaluación y serialización de modelos."""
import json
import logging
from pathlib import Path
from typing import Optional, Tuple, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
from sklearn.model_selection import TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier

ROOT = Path(__file__).parent.parent
DATA_PROCESSED = ROOT / "data" / "processed"
MODELS_DIR = ROOT / "models"

logger = logging.getLogger(__name__)

LABEL_MAP = {"home_win": 0, "draw": 1, "away_win": 2}
LABEL_NAMES = {v: k for k, v in LABEL_MAP.items()}

FEATURE_COLS = [
    "elo_diff", "elo_home", "elo_away",
    "home_goals_scored_avg5", "home_goals_conceded_avg5",
    "away_goals_scored_avg5", "away_goals_conceded_avg5",
    "h2h_home_win_pct", "is_neutral", "wc_experience_diff",
]
WEIGHT_COL = "tournament_weight"


def temporal_split(
    df: pd.DataFrame,
    test_year: int = 2022,
    calib_year: int = 2018,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Retorna (train, calib, test) con corte temporal estricto.

    train  < calib_year   → entrena el XGB base
    calib == calib_year   → calibra las probabilidades (holdout temporal)
    test  == test_year    → evaluación final, nunca vista
    """
    train = df[df["year"] < calib_year].copy()
    calib = df[df["year"] == calib_year].copy()
    test = df[df["year"] == test_year].copy()
    logger.info(
        "Train: %d filas | Calib (%d): %d filas | Test (%d): %d filas",
        len(train), calib_year, len(calib), test_year, len(test),
    )
    return train, calib, test


def build_baseline() -> Pipeline:
    """Regresión logística como baseline."""
    return Pipeline([
        ("scaler", StandardScaler()),
        ("lr", LogisticRegression(max_iter=1000, random_state=42)),
    ])


def build_xgb_pipeline() -> Pipeline:
    # Hiperparámetros tuneados en Día 4: regularización fuerte para dataset pequeño (~900 filas)
    xgb = XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=150,
        max_depth=3,
        learning_rate=0.03,
        subsample=0.7,
        colsample_bytree=0.8,
        reg_alpha=2.0,
        reg_lambda=3.0,
        random_state=42,
        eval_metric="mlogloss",
        verbosity=0,
    )
    return Pipeline([("scaler", StandardScaler()), ("xgb", xgb)])


def _sample_weights(df: pd.DataFrame) -> Optional[np.ndarray]:
    """Retorna sample_weight desde tournament_weight si existe, sino None."""
    if WEIGHT_COL in df.columns:
        return df[WEIGHT_COL].to_numpy(dtype=float)
    return None


def train(
    df_train: pd.DataFrame,
    model_type: str = "xgb_calibrated",
    df_calib: Optional[pd.DataFrame] = None,
) -> Union[CalibratedClassifierCV, Pipeline]:
    """Entrena un modelo. model_type: 'baseline' | 'xgb' | 'xgb_calibrated'.

    Para 'xgb_calibrated':
    - Si df_calib está presente, entrena el XGB en df_train y calibra con
      holdout temporal (method='sigmoid', sin KFold sobre la serie).
    - Si df_calib es None, usa prefit=False con cv=5 como fallback.
    """
    X = df_train[FEATURE_COLS]
    y = df_train["outcome"].map(LABEL_MAP)
    sw = _sample_weights(df_train)

    if model_type == "baseline":
        model = build_baseline()
        fit_params = {"lr__sample_weight": sw} if sw is not None else {}
        model.fit(X, y, **fit_params)
    elif model_type == "xgb":
        model = build_xgb_pipeline()
        fit_params = {"xgb__sample_weight": sw} if sw is not None else {}
        model.fit(X, y, **fit_params)
    else:
        if df_calib is not None and len(df_calib) > 0:
            df_full = pd.concat([df_train, df_calib]).sort_values("year").reset_index(drop=True)
            X_full = df_full[FEATURE_COLS]
            y_full = df_full["outcome"].map(LABEL_MAP)
            sw_full = _sample_weights(df_full)
            tss = TimeSeriesSplit(n_splits=3)
            model = CalibratedClassifierCV(build_xgb_pipeline(), cv=tss, method="sigmoid")
            fit_params = {"xgb__sample_weight": sw_full} if sw_full is not None else {}
            model.fit(X_full, y_full, **fit_params)
            logger.info(
                "Calibración temporal (TimeSeriesSplit n=3, sigmoid) sobre %d filas "
                "(train %d + calib %d)",
                len(df_full), len(df_train), len(df_calib),
            )
        else:
            tss = TimeSeriesSplit(n_splits=5)
            model = CalibratedClassifierCV(build_xgb_pipeline(), cv=tss, method="sigmoid")
            fit_params = {"xgb__sample_weight": sw} if sw is not None else {}
            model.fit(X, y, **fit_params)
            logger.info("Calibración con TimeSeriesSplit n=5 (sin df_calib disponible)")

    logger.info("Modelo '%s' entrenado sobre %d filas", model_type, len(df_train))
    return model


def rps_score(y_true_labels: np.ndarray, y_proba: np.ndarray) -> float:
    """Ranked Probability Score promedio para predicciones 3-clase.

    Métrica propia para 1X2: respeta el orden de los outcomes (home < draw < away).
    Menor es mejor; RPS=0 implica predicción perfecta.
    """
    n, k = y_proba.shape
    total = 0.0
    for i in range(n):
        obs = np.zeros(k)
        obs[int(y_true_labels[i])] = 1.0
        cum_pred = np.cumsum(y_proba[i])
        cum_obs = np.cumsum(obs)
        total += np.sum((cum_pred[:-1] - cum_obs[:-1]) ** 2) / (k - 1)
    return float(total / n)


def evaluate(model, df_test: pd.DataFrame, model_name: str = "model") -> dict:
    """Evalúa el modelo y retorna diccionario de métricas (acc, log_loss, brier, RPS)."""
    X = df_test[FEATURE_COLS]
    y_true = df_test["outcome"].map(LABEL_MAP)
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)

    brier_scores = []
    for i in LABEL_NAMES:
        y_bin = (y_true == i).astype(int)
        brier_scores.append(brier_score_loss(y_bin, y_proba[:, i]))

    rps = rps_score(y_true.to_numpy(), y_proba)

    metrics = {
        model_name: {
            "accuracy": round(accuracy_score(y_true, y_pred), 4),
            "log_loss": round(log_loss(y_true, y_proba), 4),
            "brier_mean": round(float(np.mean(brier_scores)), 4),
            "rps": round(rps, 4),
            "n_train": None,
            "n_test": len(df_test),
        }
    }
    logger.info("%s — acc=%.3f | log_loss=%.3f | brier=%.4f | rps=%.4f",
                model_name,
                metrics[model_name]["accuracy"],
                metrics[model_name]["log_loss"],
                metrics[model_name]["brier_mean"],
                metrics[model_name]["rps"])
    return metrics


def confusion_matrix_dict(model, df_test: pd.DataFrame) -> dict:
    """Retorna la matriz de confusión como dict {real: {pred: count}}."""
    from sklearn.metrics import confusion_matrix
    X = df_test[FEATURE_COLS]
    y_true = df_test["outcome"].map(LABEL_MAP)
    y_pred = model.predict(X)
    labels = [0, 1, 2]
    cm = confusion_matrix(y_true, y_pred, labels=labels)
    result = {}
    for i, true_label in enumerate(labels):
        result[LABEL_NAMES[true_label]] = {
            LABEL_NAMES[pred_label]: int(cm[i, j])
            for j, pred_label in enumerate(labels)
        }
    return result


def save_model(model, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    logger.info("Modelo guardado en %s", path)


def save_metrics(metrics: dict, path: Path = DATA_PROCESSED / "metrics.json") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if path.exists():
        with open(path) as f:
            existing = json.load(f)
    existing.update(metrics)
    with open(path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info("Métricas guardadas en %s", path)


def load_model(path: Path = MODELS_DIR / "xgb_calibrated.pkl"):
    return joblib.load(path)
