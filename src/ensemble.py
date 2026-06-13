"""Ensemble calibrado: ELO-only + Poisson + XGBoost.

Pesos configurables; por defecto reflejan el resultado del walk-forward:
  - ELO y Poisson tienen señal robusta multi-torneo
  - XGB gana terreno en torneos recientes (mayor volumen de datos)

Uso:
    from src.ensemble import EnsembleModel
    ens = EnsembleModel(weights={"elo": 0.35, "poisson": 0.35, "xgb": 0.30})
    ens.fit(df_train, df_all=df_all)  # ajusta Poisson; XGB ya viene pre-entrenado
    proba = ens.predict_proba_match("France", "Brazil", elo_home=2050, elo_away=2080)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"
logger = logging.getLogger(__name__)

# Pesos por defecto — ajustados tras gate A2:
# XGB no supera al ELO-only en walk-forward global; Poisson añade señal independiente.
DEFAULT_WEIGHTS = {"elo": 0.35, "poisson": 0.35, "xgb": 0.30}


def _elo_proba(
    elo_home: float,
    elo_away: float,
    is_neutral: bool,
    home_advantage_elo: float = 100.0,
    draw_base: float = 0.28,
) -> tuple[float, float, float]:
    """Convierte diferencia de ELO a probabilidades 1X2.

    Modelo simple pero robusto: expectativa ELO → ajuste por empate histórico.
    """
    adj = 0.0 if is_neutral else home_advantage_elo
    exp_home = 1 / (1 + 10 ** ((elo_away - elo_home - adj) / 400))
    # El empate se modela como fracción que crece cuando los equipos están igualados
    draw_frac = draw_base * (1 - abs(exp_home - 0.5) * 1.6)
    draw_frac = max(0.08, min(draw_frac, 0.36))
    p_home = exp_home * (1 - draw_frac)
    p_away = (1 - exp_home) * (1 - draw_frac)
    total = p_home + draw_frac + p_away
    return round(p_home / total, 4), round(draw_frac / total, 4), round(p_away / total, 4)


def _blend(probs_list: list[tuple[float, float, float]], weights: list[float]) -> tuple[float, float, float]:
    """Mezcla ponderada de probabilidades 1X2 con renormalización."""
    w_sum = sum(weights)
    p_h = sum(p[0] * w for p, w in zip(probs_list, weights)) / w_sum
    p_d = sum(p[1] * w for p, w in zip(probs_list, weights)) / w_sum
    p_a = sum(p[2] * w for p, w in zip(probs_list, weights)) / w_sum
    total = p_h + p_d + p_a
    return round(p_h / total, 4), round(p_d / total, 4), round(p_a / total, 4)


class EnsembleModel:
    """Ensemble calibrado para predicción de partidos de fútbol internacional."""

    def __init__(self, weights: Optional[dict] = None) -> None:
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.poisson_model = None
        self.xgb_model = None
        self._fitted = False

    def fit(self, df_train, df_all=None, xgb_model=None) -> "EnsembleModel":
        """Ajusta el Poisson sobre df_train; carga o recibe el XGB ya entrenado."""
        from src.poisson_model import PoissonModel

        self.poisson_model = PoissonModel()
        self.poisson_model.fit(df_train, weight_col="tournament_weight")
        self.poisson_model.save()

        if xgb_model is not None:
            self.xgb_model = xgb_model
        else:
            from src.model import load_model
            try:
                self.xgb_model = load_model()
            except Exception as e:
                logger.warning("XGB no disponible (%s) — ensemble usará solo ELO+Poisson", e)
                self.weights = {"elo": 0.50, "poisson": 0.50, "xgb": 0.0}

        self._fitted = True
        logger.info("EnsembleModel ajustado. Pesos: %s", self.weights)
        return self

    def predict_proba_match(
        self,
        home_team: str,
        away_team: str,
        elo_home: float,
        elo_away: float,
        is_neutral: bool = True,
        xgb_features: Optional[np.ndarray] = None,
    ) -> tuple[float, float, float]:
        """Predicción de un partido: (p_home, p_draw, p_away).

        Args:
            xgb_features: vector de FEATURE_COLS para el XGB (None → usa peso 0 para XGB).
        """
        probs_list = []
        w_list = []

        # ELO
        p_elo = _elo_proba(elo_home, elo_away, is_neutral)
        probs_list.append(p_elo)
        w_list.append(self.weights.get("elo", 0.35))

        # Poisson
        if self.poisson_model is not None and self.weights.get("poisson", 0) > 0:
            elo_diff = elo_home - elo_away
            try:
                lam_h, lam_a = self.poisson_model.predict_goals(
                    home_team, away_team, is_neutral=is_neutral, elo_diff=elo_diff
                )
                matrix = self.poisson_model.scoreline_matrix(lam_h, lam_a)
                p_poi = self.poisson_model.aggregate_1x2(matrix)
                probs_list.append(p_poi)
                w_list.append(self.weights.get("poisson", 0.35))
            except Exception as e:
                logger.debug("Poisson falló para %s vs %s: %s", home_team, away_team, e)

        # XGB
        xgb_w = self.weights.get("xgb", 0.30)
        if self.xgb_model is not None and xgb_features is not None and xgb_w > 0:
            try:
                p_xgb = self.xgb_model.predict_proba(xgb_features.reshape(1, -1))[0]
                probs_list.append((float(p_xgb[0]), float(p_xgb[1]), float(p_xgb[2])))
                w_list.append(xgb_w)
            except Exception as e:
                logger.debug("XGB falló: %s", e)

        return _blend(probs_list, w_list)

    def save(self, path: Path = MODELS_DIR / "ensemble.pkl") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("EnsembleModel guardado en %s", path)

    @classmethod
    def load(cls, path: Path = MODELS_DIR / "ensemble.pkl") -> "EnsembleModel":
        return joblib.load(path)


def evaluate_ensemble(
    ensemble: EnsembleModel,
    df_test,
    df_features_test,
) -> dict:
    """Evalúa el ensemble en el test set con RPS, log-loss y accuracy."""
    from src.model import FEATURE_COLS, LABEL_MAP, rps_score
    from sklearn.metrics import accuracy_score, log_loss

    y_true, y_proba = [], []

    for idx, row in df_test.iterrows():
        outcome = row.get("outcome")
        if outcome not in LABEL_MAP:
            continue

        feat_row = df_features_test.loc[idx] if idx in df_features_test.index else None
        xgb_feats = feat_row[FEATURE_COLS].to_numpy(float) if feat_row is not None else None

        p_h, p_d, p_a = ensemble.predict_proba_match(
            home_team=row["home_team"],
            away_team=row["away_team"],
            elo_home=float(row.get("elo_home", 1500)),
            elo_away=float(row.get("elo_away", 1500)),
            is_neutral=bool(row.get("is_neutral", True)),
            xgb_features=xgb_feats,
        )
        y_true.append(LABEL_MAP[outcome])
        y_proba.append([p_h, p_d, p_a])

    if not y_true:
        return {}

    y_true_arr = np.array(y_true)
    y_proba_arr = np.array(y_proba)
    y_pred = np.argmax(y_proba_arr, axis=1)

    return {
        "accuracy": round(float(accuracy_score(y_true_arr, y_pred)), 4),
        "log_loss": round(float(log_loss(y_true_arr, y_proba_arr)), 4),
        "rps": round(float(rps_score(y_true_arr, y_proba_arr)), 4),
        "n_test": len(y_true),
    }
