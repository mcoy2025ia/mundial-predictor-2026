"""Modelo de Poisson bivariado para predicción de goles en fútbol internacional.

Estima lambdas esperados (goles por equipo) usando fuerzas de ataque/defensa
calculadas por regresión Poisson sobre el histórico ponderado por torneo.

Uso:
    from src.poisson_model import PoissonModel
    model = PoissonModel()
    model.fit(df_wc)
    lam_h, lam_a = model.predict_goals("France", "Brazil")
    matrix = model.scoreline_matrix(lam_h, lam_a)
    top5 = model.top_scorelines(matrix, n=5)
    p1x2 = model.aggregate_1x2(matrix)
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from scipy.stats import poisson

logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
MODELS_DIR = ROOT / "models"

# Máximo de goles considerados en la matriz (7×7 cubre >99% de los partidos reales)
MAX_GOALS = 7

# Goles promedio en el torneo (aprox histórico WC)
_MEAN_GOALS_DEFAULT = 1.35


class PoissonModel:
    """Modelo de Poisson para predicción de marcadores de fútbol.

    Atributos estimados tras fit():
        attack_[team]:  fuerza ofensiva normalizada (>1 = sobre la media)
        defense_[team]: fuerza defensiva normalizada (>1 = peor defensa)
        mean_goals_home, mean_goals_away: medias globales del dataset
    """

    def __init__(self) -> None:
        self.attack_: dict[str, float] = {}
        self.defense_: dict[str, float] = {}
        self.mean_goals_home: float = _MEAN_GOALS_DEFAULT
        self.mean_goals_away: float = _MEAN_GOALS_DEFAULT * 0.85
        self._fitted = False

    # ------------------------------------------------------------------
    # Ajuste
    # ------------------------------------------------------------------

    def fit(
        self,
        df: pd.DataFrame,
        weight_col: Optional[str] = "tournament_weight",
        n_iter: int = 100,
    ) -> "PoissonModel":
        """Estima fuerzas de ataque y defensa por el método iterativo de Dixon-Robinson.

        Algoritmo:
          1. Inicializa attack[t] = defense[t] = 1.0 para todos.
          2. Itera: actualiza attack usando goles reales vs defensa ajena;
             actualiza defense usando goles concedidos vs ataque ajeno.
          3. Normaliza para que el promedio sea 1.0.

        Args:
            df: DataFrame con columnas home_team, away_team, home_score, away_score.
            weight_col: columna de peso por torneo (None = sin ponderación).
            n_iter: iteraciones de actualización (converge rápido, ~20-50 es suficiente).
        """
        df = df[df["home_score"].notna() & df["away_score"].notna()].copy()
        df["home_score"] = df["home_score"].astype(float)
        df["away_score"] = df["away_score"].astype(float)

        weights = df[weight_col].to_numpy(float) if weight_col and weight_col in df.columns else np.ones(len(df))

        teams = sorted(set(df["home_team"]) | set(df["away_team"]))
        attack = {t: 1.0 for t in teams}
        defense = {t: 1.0 for t in teams}

        # Medias globales ponderadas
        w_sum = weights.sum()
        self.mean_goals_home = float(np.average(df["home_score"], weights=weights))
        self.mean_goals_away = float(np.average(df["away_score"], weights=weights))

        home_teams = df["home_team"].to_numpy()
        away_teams = df["away_team"].to_numpy()
        home_goals = df["home_score"].to_numpy()
        away_goals = df["away_score"].to_numpy()

        for _ in range(n_iter):
            # Actualizar attack
            new_attack = {}
            for t in teams:
                # Partidos como local
                mask_h = home_teams == t
                if mask_h.any():
                    num_h = np.sum(weights[mask_h] * home_goals[mask_h])
                    den_h = np.sum(weights[mask_h] * self.mean_goals_home *
                                   np.array([defense[away_teams[i]] for i in np.where(mask_h)[0]]))
                    contrib_h = num_h / den_h if den_h > 0 else 1.0
                else:
                    contrib_h = 1.0

                # Partidos como visitante
                mask_a = away_teams == t
                if mask_a.any():
                    num_a = np.sum(weights[mask_a] * away_goals[mask_a])
                    den_a = np.sum(weights[mask_a] * self.mean_goals_away *
                                   np.array([defense[home_teams[i]] for i in np.where(mask_a)[0]]))
                    contrib_a = num_a / den_a if den_a > 0 else 1.0
                else:
                    contrib_a = 1.0

                new_attack[t] = (contrib_h + contrib_a) / 2

            # Actualizar defense
            new_defense = {}
            for t in teams:
                mask_h = home_teams == t
                if mask_h.any():
                    num_h = np.sum(weights[mask_h] * away_goals[mask_h])
                    den_h = np.sum(weights[mask_h] * self.mean_goals_away *
                                   np.array([new_attack[away_teams[i]] for i in np.where(mask_h)[0]]))
                    contrib_h = num_h / den_h if den_h > 0 else 1.0
                else:
                    contrib_h = 1.0

                mask_a = away_teams == t
                if mask_a.any():
                    num_a = np.sum(weights[mask_a] * home_goals[mask_a])
                    den_a = np.sum(weights[mask_a] * self.mean_goals_home *
                                   np.array([new_attack[home_teams[i]] for i in np.where(mask_a)[0]]))
                    contrib_a = num_a / den_a if den_a > 0 else 1.0
                else:
                    contrib_a = 1.0

                new_defense[t] = (contrib_h + contrib_a) / 2

            attack = new_attack
            defense = new_defense

            # Normalizar (media = 1.0)
            att_mean = np.mean(list(attack.values()))
            def_mean = np.mean(list(defense.values()))
            if att_mean > 0:
                attack = {t: v / att_mean for t, v in attack.items()}
            if def_mean > 0:
                defense = {t: v / def_mean for t, v in defense.items()}

        self.attack_ = attack
        self.defense_ = defense
        self._fitted = True
        logger.info(
            "PoissonModel ajustado: %d equipos, mean_home=%.3f, mean_away=%.3f",
            len(teams), self.mean_goals_home, self.mean_goals_away,
        )
        return self

    # ------------------------------------------------------------------
    # Predicción
    # ------------------------------------------------------------------

    def predict_goals(
        self,
        home_team: str,
        away_team: str,
        is_neutral: bool = True,
        elo_diff: float = 0.0,
    ) -> tuple[float, float]:
        """Predice los goles esperados (lambda) para cada equipo.

        Args:
            is_neutral: si True, ambos equipos usan mean_goals_home como base
                        (sede neutral); si False, el local tiene ventaja de goles.
            elo_diff:  ajuste opcional por diferencia de ELO (±signo amplifica lambda).
        """
        if not self._fitted:
            raise RuntimeError("Llamar a fit() antes de predict_goals()")

        att_h = self.attack_.get(home_team, 1.0)
        def_h = self.defense_.get(home_team, 1.0)
        att_a = self.attack_.get(away_team, 1.0)
        def_a = self.defense_.get(away_team, 1.0)

        # En sede neutral, ambos equipos parten de la misma media de goles
        base_h = self.mean_goals_home if not is_neutral else (self.mean_goals_home + self.mean_goals_away) / 2
        base_a = self.mean_goals_away if not is_neutral else (self.mean_goals_home + self.mean_goals_away) / 2

        lam_h = base_h * att_h * def_a
        lam_a = base_a * att_a * def_h

        # Pequeño ajuste por ELO: equipo más fuerte ataca un poco más
        if abs(elo_diff) > 50:
            elo_factor = np.tanh(elo_diff / 800)  # [-0.5, +0.5] aprox para diff razonables
            lam_h *= (1 + 0.15 * elo_factor)
            lam_a *= (1 - 0.10 * elo_factor)

        return max(lam_h, 0.1), max(lam_a, 0.1)

    def scoreline_matrix(self, lam_home: float, lam_away: float) -> np.ndarray:
        """Genera la matriz de probabilidades de marcadores exactos.

        Returns:
            matrix[i,j] = P(home scores i goals, away scores j goals)
            Forma: (MAX_GOALS+1) × (MAX_GOALS+1)
        """
        probs_h = np.array([poisson.pmf(k, lam_home) for k in range(MAX_GOALS + 1)])
        probs_a = np.array([poisson.pmf(k, lam_away) for k in range(MAX_GOALS + 1)])
        # Normalizar para que la matriz sume 1 (truncamos la cola)
        matrix = np.outer(probs_h, probs_a)
        return matrix / matrix.sum()

    def top_scorelines(
        self,
        matrix: np.ndarray,
        n: int = 5,
    ) -> list[dict]:
        """Retorna los n marcadores más probables.

        Returns:
            Lista de dicts: [{"home": int, "away": int, "prob": float}, ...]
        """
        flat = [(matrix[i, j], i, j) for i in range(matrix.shape[0]) for j in range(matrix.shape[1])]
        flat.sort(reverse=True)
        return [{"home": i, "away": j, "prob": round(float(p), 4)} for p, i, j in flat[:n]]

    def aggregate_1x2(self, matrix: np.ndarray) -> tuple[float, float, float]:
        """Agrega la matriz a probabilidades 1X2 (home win, draw, away win).

        Returns:
            (p_home_win, p_draw, p_away_win) — suman 1.0
        """
        n = matrix.shape[0]
        p_home = float(sum(matrix[i, j] for i in range(n) for j in range(n) if i > j))
        p_draw = float(sum(matrix[i, i] for i in range(n)))
        p_away = float(sum(matrix[i, j] for i in range(n) for j in range(n) if i < j))
        total = p_home + p_draw + p_away
        if total > 0:
            p_home, p_draw, p_away = p_home / total, p_draw / total, p_away / total
        return round(p_home, 4), round(p_draw, 4), round(p_away, 4)

    # ------------------------------------------------------------------
    # Serialización
    # ------------------------------------------------------------------

    def save(self, path: Path = MODELS_DIR / "poisson_model.pkl") -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info("PoissonModel guardado en %s", path)

    @classmethod
    def load(cls, path: Path = MODELS_DIR / "poisson_model.pkl") -> "PoissonModel":
        return joblib.load(path)


# ------------------------------------------------------------------
# Evaluación
# ------------------------------------------------------------------

def evaluate_poisson(model: PoissonModel, df_test: pd.DataFrame) -> dict:
    """Evalúa el modelo Poisson con RPS y log-loss en el conjunto de test.

    Compara la predicción 1X2 del Poisson contra los resultados reales.
    """
    from src.model import LABEL_MAP, rps_score
    from sklearn.metrics import accuracy_score, log_loss

    y_true = []
    y_proba = []

    for _, row in df_test.iterrows():
        if pd.isna(row.get("home_score")) or pd.isna(row.get("away_score")):
            continue
        try:
            lam_h, lam_a = model.predict_goals(
                row["home_team"], row["away_team"],
                is_neutral=bool(row.get("neutral", True)),
                elo_diff=float(row.get("elo_diff", 0.0)),
            )
        except Exception:
            continue

        matrix = model.scoreline_matrix(lam_h, lam_a)
        p_h, p_d, p_a = model.aggregate_1x2(matrix)

        outcome = row.get("outcome")
        if outcome not in LABEL_MAP:
            continue
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
