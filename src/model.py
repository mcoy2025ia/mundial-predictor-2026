"""Entrenamiento, evaluación y serialización de modelos."""
import json
import logging
from pathlib import Path
from typing import Tuple, Union

import joblib
import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, log_loss
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


def temporal_split(df: pd.DataFrame, test_year: int = 2022) -> Tuple[pd.DataFrame, pd.DataFrame]:
    train = df[df["year"] < test_year].copy()
    test = df[df["year"] == test_year].copy()
    logger.info("Train: %d filas | Test (%d): %d filas", len(train), test_year, len(test))
    return train, test


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


def train(
    df_train: pd.DataFrame,
    model_type: str = "xgb_calibrated",
) -> Union[CalibratedClassifierCV, Pipeline]:
    """Entrena un modelo. model_type: 'baseline' | 'xgb' | 'xgb_calibrated'."""
    X = df_train[FEATURE_COLS]
    y = df_train["outcome"].map(LABEL_MAP)

    if model_type == "baseline":
        model = build_baseline()
    elif model_type == "xgb":
        model = build_xgb_pipeline()
    else:
        model = CalibratedClassifierCV(build_xgb_pipeline(), cv=5, method="isotonic")

    model.fit(X, y)
    logger.info("Modelo '%s' entrenado sobre %d filas", model_type, len(df_train))
    return model


def evaluate(model, df_test: pd.DataFrame, model_name: str = "model") -> dict:
    """Evalúa el modelo y retorna diccionario de métricas."""
    X = df_test[FEATURE_COLS]
    y_true = df_test["outcome"].map(LABEL_MAP)
    y_pred = model.predict(X)
    y_proba = model.predict_proba(X)

    # Brier score por clase (media de las tres clases)
    brier_scores = []
    for i, label in LABEL_NAMES.items():
        y_bin = (y_true == i).astype(int)
        brier_scores.append(brier_score_loss(y_bin, y_proba[:, i]))

    metrics = {
        model_name: {
            "accuracy": round(accuracy_score(y_true, y_pred), 4),
            "log_loss": round(log_loss(y_true, y_proba), 4),
            "brier_mean": round(float(np.mean(brier_scores)), 4),
            "n_train": None,
            "n_test": len(df_test),
        }
    }
    logger.info("%s — acc=%.3f | log_loss=%.3f | brier=%.4f",
                model_name,
                metrics[model_name]["accuracy"],
                metrics[model_name]["log_loss"],
                metrics[model_name]["brier_mean"])
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
