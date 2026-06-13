"""Cálculo de features: ELO, forma reciente, H2H, experiencia en Mundiales."""
import json
import logging
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_PROCESSED = ROOT / "data" / "processed"

logger = logging.getLogger(__name__)

INITIAL_ELO = 1500.0
HOME_ADVANTAGE_ELO = 100.0  # puntos extra al local cuando is_neutral=False

# K-factor por tipo de torneo (mayor importancia → mayor actualización)
K_BY_TOURNAMENT: Dict[str, float] = {
    "FIFA World Cup": 60.0,
    "UEFA Euro": 55.0,
    "Copa América": 55.0,
    "African Cup of Nations": 50.0,
    "AFC Asian Cup": 50.0,
    "Gold Cup": 45.0,
    "CONCACAF Nations League": 40.0,
    "UEFA Nations League": 40.0,
    "FIFA World Cup qualification": 40.0,
    "UEFA Euro qualification": 35.0,
    "African Cup of Nations qualification": 35.0,
    "Copa América qualification": 35.0,
    "AFC Asian Cup qualification": 35.0,
    "CONCACAF Nations League qualification": 30.0,
    "Friendly": 20.0,
}
_DEFAULT_K = 30.0


def _k_factor(tournament: str) -> float:
    return K_BY_TOURNAMENT.get(tournament, _DEFAULT_K)


def _goal_margin_multiplier(goal_diff: int) -> float:
    """Escala el K por margen de victoria: log(1 + |GD|) normalizado a 1.0 para GD=1."""
    return np.log1p(abs(goal_diff)) / np.log1p(1)


# ---------------------------------------------------------------------------
# ELO
# ---------------------------------------------------------------------------

def expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(rating: float, expected: float, actual: float, k: float = 32.0) -> float:
    """Actualiza el ELO de un equipo (API pública para tests y uso externo)."""
    return rating + k * (actual - expected)


def compute_elo_ratings(df_all: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """ELO mejorado: K por torneo, multiplicador por margen de goles, home advantage.

    - K varía por importancia del torneo (60 para WC, 20 para amistosos).
    - El update se escala por log(1+|GD|) para que las goleadas cuenten más.
    - Cuando neutral=False, se suma HOME_ADVANTAGE_ELO al expected del local
      antes de calcular el update (el modelo aprende que local gana más).
    """
    df = df_all.sort_values("date").reset_index(drop=True)
    ratings: Dict[str, float] = {}

    elo_home_pre = np.empty(len(df))
    elo_away_pre = np.empty(len(df))

    has_neutral = "neutral" in df.columns
    has_tournament = "tournament" in df.columns

    for i, row in enumerate(df.itertuples(index=False)):
        home, away = row.home_team, row.away_team
        r_home = ratings.get(home, INITIAL_ELO)
        r_away = ratings.get(away, INITIAL_ELO)

        elo_home_pre[i] = r_home
        elo_away_pre[i] = r_away

        hs, as_ = row.home_score, row.away_score
        if pd.isna(hs) or pd.isna(as_):
            continue

        # Home advantage en el expected score (solo partidos no neutrales)
        is_neutral = bool(getattr(row, "neutral", True)) if has_neutral else True
        r_home_adj = r_home + (HOME_ADVANTAGE_ELO if not is_neutral else 0.0)
        exp_home = expected_score(r_home_adj, r_away)

        if hs > as_:
            actual_home, actual_away = 1.0, 0.0
        elif hs == as_:
            actual_home = actual_away = 0.5
        else:
            actual_home, actual_away = 0.0, 1.0

        k = _k_factor(getattr(row, "tournament", "")) if has_tournament else _DEFAULT_K
        margin_mult = _goal_margin_multiplier(int(hs) - int(as_))
        k_scaled = k * margin_mult

        ratings[home] = r_home + k_scaled * (actual_home - exp_home)
        ratings[away] = r_away + k_scaled * (actual_away - (1 - exp_home))

    df = df.copy()
    df["elo_home"] = elo_home_pre
    df["elo_away"] = elo_away_pre
    df["elo_diff"] = df["elo_home"] - df["elo_away"]
    return df, ratings


def save_current_elo(ratings: Dict[str, float], path: Path = DATA_PROCESSED / "elo_current.json") -> None:
    """Guarda ratings ELO finales ordenados por ranking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    ranked = dict(sorted(ratings.items(), key=lambda x: x[1], reverse=True))
    with open(path, "w") as f:
        json.dump(ranked, f, indent=2)
    logger.info("elo_current.json guardado: %d equipos en %s", len(ranked), path)


# ---------------------------------------------------------------------------
# Forma reciente — goles promedio últimos N partidos
# ---------------------------------------------------------------------------

def compute_rolling_goals(df_all: pd.DataFrame, df_wc: pd.DataFrame, n: int = 5) -> pd.DataFrame:
    """Agrega goles promedio de los últimos n partidos (home y away combinados) a df_wc.

    Considera TODOS los partidos de df_all (no solo Mundiales) para calcular
    la forma reciente de cada equipo. Sin leakage: shift(1) excluye el partido actual.
    """
    # Timeline plano: una fila por equipo por partido
    home = df_all[["date", "home_team", "home_score", "away_score"]].dropna().copy()
    home.columns = ["date", "team", "scored", "conceded"]

    away = df_all[["date", "away_team", "away_score", "home_score"]].dropna().copy()
    away.columns = ["date", "team", "scored", "conceded"]

    timeline = (
        pd.concat([home, away])
        .sort_values(["team", "date"])
        .reset_index(drop=True)
    )

    # Rolling con shift para evitar leakage
    timeline[f"scored_avg{n}"] = timeline.groupby("team")["scored"].transform(
        lambda x: x.shift(1).rolling(n, min_periods=1).mean()
    )
    timeline[f"conceded_avg{n}"] = timeline.groupby("team")["conceded"].transform(
        lambda x: x.shift(1).rolling(n, min_periods=1).mean()
    )

    # Relleno para primera aparición histórica (sin historial previo)
    global_scored_mean = df_all["home_score"].dropna().mean()
    global_conceded_mean = df_all["away_score"].dropna().mean()
    timeline[f"scored_avg{n}"] = timeline[f"scored_avg{n}"].fillna(global_scored_mean)
    timeline[f"conceded_avg{n}"] = timeline[f"conceded_avg{n}"].fillna(global_conceded_mean)

    # Merge con partidos de Mundial
    home_stats = timeline[["date", "team", f"scored_avg{n}", f"conceded_avg{n}"]].copy()
    home_stats.columns = [
        "date", "home_team",
        f"home_goals_scored_avg{n}", f"home_goals_conceded_avg{n}",
    ]
    away_stats = timeline[["date", "team", f"scored_avg{n}", f"conceded_avg{n}"]].copy()
    away_stats.columns = [
        "date", "away_team",
        f"away_goals_scored_avg{n}", f"away_goals_conceded_avg{n}",
    ]

    df_out = df_wc.merge(home_stats, on=["date", "home_team"], how="left")
    df_out = df_out.merge(away_stats, on=["date", "away_team"], how="left")
    return df_out


# ---------------------------------------------------------------------------
# H2H — % victorias del local en enfrentamientos previos
# ---------------------------------------------------------------------------

def compute_h2h(df_wc: pd.DataFrame) -> pd.DataFrame:
    """Agrega h2h_home_win_pct usando acumulación con dict (O(n), sin leakage)."""
    df = df_wc.sort_values("date").reset_index(drop=True).copy()

    # pair_total[{A,B}] = total partidos jugados entre A y B hasta ahora
    # pair_wins[{A,B}][team] = victorias de team en esos enfrentamientos
    pair_total: Dict[frozenset, int] = defaultdict(int)
    pair_wins: Dict[frozenset, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    h2h_values = []

    for row in df.itertuples(index=False):
        home, away = row.home_team, row.away_team
        pair = frozenset([home, away])

        total = pair_total[pair]
        home_wins = pair_wins[pair][home]
        h2h_values.append(home_wins / total if total > 0 else 0.5)

        # Actualizar después de registrar (sin leakage)
        pair_total[pair] += 1
        if row.outcome == "home_win":
            pair_wins[pair][home] += 1
        elif row.outcome == "away_win":
            pair_wins[pair][away] += 1

    df["h2h_home_win_pct"] = h2h_values
    return df


# ---------------------------------------------------------------------------
# Experiencia en Mundiales
# ---------------------------------------------------------------------------

def compute_wc_experience(df_wc: pd.DataFrame) -> pd.DataFrame:
    """Agrega wc_experience_diff usando contador acumulado (O(n), sin leakage)."""
    df = df_wc.sort_values("date").reset_index(drop=True).copy()

    experience: Dict[str, int] = defaultdict(int)
    exp_diff = []

    for row in df.itertuples(index=False):
        home, away = row.home_team, row.away_team
        exp_diff.append(experience[home] - experience[away])
        experience[home] += 1
        experience[away] += 1

    df["wc_experience_diff"] = exp_diff
    return df


# ---------------------------------------------------------------------------
# Pesos por torneo — escala 0.0–1.0 (mayor = partido más informativo)
# ---------------------------------------------------------------------------

TOURNAMENT_WEIGHTS: Dict[str, float] = {
    # Máximo peso: fase final de Copa del Mundo y grandes copas continentales
    "FIFA World Cup": 1.0,
    "UEFA Euro": 0.90,
    "Copa América": 0.90,
    "African Cup of Nations": 0.80,
    "AFC Asian Cup": 0.80,
    "Gold Cup": 0.75,
    "CONCACAF Nations League": 0.65,
    "UEFA Nations League": 0.65,
    "OFC Nations Cup": 0.65,
    # Eliminatorias mundialistas
    "FIFA World Cup qualification": 0.60,
    "UEFA Euro qualification": 0.55,
    "African Cup of Nations qualification": 0.50,
    "Copa América qualification": 0.50,
    "AFC Asian Cup qualification": 0.50,
    "CONCACAF Nations League qualification": 0.45,
    "Friendly": 0.20,
}
_DEFAULT_WEIGHT = 0.35  # torneos regionales menores


def get_tournament_weight(tournament: str) -> float:
    return TOURNAMENT_WEIGHTS.get(tournament, _DEFAULT_WEIGHT)


# ---------------------------------------------------------------------------
# Días de descanso entre partidos
# ---------------------------------------------------------------------------

def compute_rest_days(
    df_all: pd.DataFrame,
    df_target: pd.DataFrame,
    cap_days: int = 365,
) -> pd.DataFrame:
    """Agrega home_days_rest / away_days_rest a df_target.

    Para cada partido, calcula cuántos días lleva cada equipo sin jugar un
    internacional antes de ese partido. Sin leakage: shift(1) excluye el
    partido actual del cómputo.

    cap_days=365 aplica a la primera aparición histórica de un equipo.
    """
    home = df_all[["date", "home_team"]].rename(columns={"home_team": "team"})
    away = df_all[["date", "away_team"]].rename(columns={"away_team": "team"})
    timeline = (
        pd.concat([home, away])
        .drop_duplicates(subset=["team", "date"])
        .sort_values(["team", "date"])
        .reset_index(drop=True)
    )
    timeline["prev_date"] = timeline.groupby("team")["date"].shift(1)
    timeline["days_since_last"] = (
        (timeline["date"] - timeline["prev_date"]).dt.days
        .clip(upper=cap_days)
        .fillna(float(cap_days))
    )

    home_rest = timeline[["date", "team", "days_since_last"]].rename(
        columns={"team": "home_team", "days_since_last": "home_days_rest"}
    )
    away_rest = timeline[["date", "team", "days_since_last"]].rename(
        columns={"team": "away_team", "days_since_last": "away_days_rest"}
    )

    df_out = df_target.merge(home_rest, on=["date", "home_team"], how="left")
    df_out = df_out.merge(away_rest, on=["date", "away_team"], how="left")
    df_out["home_days_rest"] = df_out["home_days_rest"].fillna(float(cap_days))
    df_out["away_days_rest"] = df_out["away_days_rest"].fillna(float(cap_days))
    return df_out


# ---------------------------------------------------------------------------
# H2H y experiencia para el set completo de internacionales
# ---------------------------------------------------------------------------

def compute_h2h_all(df: pd.DataFrame) -> pd.DataFrame:
    """Versión de compute_h2h que opera sobre cualquier DataFrame con outcome."""
    df = df.sort_values("date").reset_index(drop=True).copy()
    pair_total: Dict[frozenset, int] = defaultdict(int)
    pair_wins: Dict[frozenset, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    h2h_values = []
    for row in df.itertuples(index=False):
        home, away = row.home_team, row.away_team
        pair = frozenset([home, away])
        total = pair_total[pair]
        h2h_values.append(pair_wins[pair][home] / total if total > 0 else 0.5)
        pair_total[pair] += 1
        if row.outcome == "home_win":
            pair_wins[pair][home] += 1
        elif row.outcome == "away_win":
            pair_wins[pair][away] += 1
    df["h2h_home_win_pct"] = h2h_values
    return df


def compute_wc_experience_all(df_all: pd.DataFrame, df_target: pd.DataFrame) -> pd.DataFrame:
    """Acumula experiencia mundialista hasta la fecha de cada partido en df_target."""
    wc_only = df_all[df_all["tournament"] == "FIFA World Cup"].sort_values("date").copy()
    exp: Dict[str, int] = defaultdict(int)
    for row in wc_only.itertuples(index=False):
        exp[row.home_team] += 1
        exp[row.away_team] += 1

    # Para df_target, calculamos la experiencia acumulada hasta cada fecha
    df_target = df_target.sort_values("date").reset_index(drop=True).copy()
    exp_running: Dict[str, int] = defaultdict(int)
    wc_iter = iter(wc_only.itertuples(index=False))
    wc_row = next(wc_iter, None)
    exp_diff = []
    for trow in df_target.itertuples(index=False):
        # Avanza el acumulador de WC hasta la fecha del partido actual
        while wc_row is not None and wc_row.date < trow.date:
            exp_running[wc_row.home_team] += 1
            exp_running[wc_row.away_team] += 1
            wc_row = next(wc_iter, None)
        exp_diff.append(exp_running[trow.home_team] - exp_running[trow.away_team])
    df_target["wc_experience_diff"] = exp_diff
    return df_target


# ---------------------------------------------------------------------------
# Pipeline completo
# ---------------------------------------------------------------------------

def build_feature_matrix(
    df_all: pd.DataFrame,
    df_wc: pd.DataFrame,
    use_all_matches: bool = True,
) -> pd.DataFrame:
    """Ensambla la feature matrix para entrenamiento.

    use_all_matches=True (default): usa todos los ~49k internacionales con score,
    ponderados por torneo. Esto multiplica el dataset de entrenamiento por ~50x.
    use_all_matches=False: comportamiento original (solo partidos de WC, ~966 filas).
    """
    logger.info("ELO sobre %d partidos históricos...", len(df_all))
    df_elo, _ = compute_elo_ratings(df_all)

    if use_all_matches:
        from src.extractor import add_outcome
        # Todos los partidos con score disponible
        df_base = df_all[df_all["home_score"].notna()].copy()
        df_base = add_outcome(df_base)

        # Merge ELO pre-match
        base = df_base.merge(
            df_elo[["date", "home_team", "away_team", "elo_home", "elo_away", "elo_diff"]],
            on=["date", "home_team", "away_team"],
            how="left",
        )

        logger.info("Goles promedio últimos 5 partidos (todos los internacionales)...")
        base = compute_rolling_goals(df_all, base, n=5)

        logger.info("H2H (todos los internacionales)...")
        base = compute_h2h_all(base)

        logger.info("Experiencia en Mundiales (acumulada cronológicamente)...")
        base = compute_wc_experience_all(df_all, base)

        base["is_neutral"] = base["neutral"].astype(int)
        base["year"] = base["date"].dt.year
        base["tournament_weight"] = base["tournament"].map(get_tournament_weight).fillna(_DEFAULT_WEIGHT)

        feature_cols = [
            "date", "year", "home_team", "away_team", "outcome", "tournament_weight",
            "elo_diff", "elo_home", "elo_away",
            "home_goals_scored_avg5", "home_goals_conceded_avg5",
            "away_goals_scored_avg5", "away_goals_conceded_avg5",
            "h2h_home_win_pct", "is_neutral", "wc_experience_diff",
        ]
        df_features = base[[c for c in feature_cols if c in base.columns]].dropna(
            subset=["elo_diff", "outcome"]
        ).copy()
        logger.info(
            "Feature matrix completa: %d filas, %d columnas (todos los internacionales)",
            *df_features.shape,
        )
    else:
        # Modo original: solo WC
        wc = df_wc.merge(
            df_elo[["date", "home_team", "away_team", "elo_home", "elo_away", "elo_diff"]],
            on=["date", "home_team", "away_team"],
            how="left",
        )
        wc = compute_rolling_goals(df_all, wc, n=5)
        wc = compute_h2h(wc)
        wc = compute_wc_experience(wc)
        wc["is_neutral"] = wc["neutral"].astype(int)
        wc["year"] = wc["date"].dt.year
        wc["tournament_weight"] = 1.0

        feature_cols = [
            "date", "year", "home_team", "away_team", "outcome", "tournament_weight",
            "elo_diff", "elo_home", "elo_away",
            "home_goals_scored_avg5", "home_goals_conceded_avg5",
            "away_goals_scored_avg5", "away_goals_conceded_avg5",
            "h2h_home_win_pct", "is_neutral", "wc_experience_diff",
        ]
        df_features = wc[[c for c in feature_cols if c in wc.columns]].copy()
        logger.info("Feature matrix WC-only: %d filas, %d columnas", *df_features.shape)

    return df_features


def compute_current_form(
    df_all: pd.DataFrame,
    teams: Optional[List[str]] = None,
    n: int = 5,
) -> Dict[str, Dict[str, float]]:
    """Calcula la forma reciente de cada equipo desde el timeline completo de internacionales.

    A diferencia de build_feature_matrix, aquí NO hacemos shift(1): queremos
    incluir el último partido jugado porque esto es para serving, no entrenamiento.
    Retorna {team: {goals_scored: x, goals_conceded: y}} con los últimos n partidos.
    """
    home = df_all[["date", "home_team", "home_score", "away_score"]].dropna().copy()
    home.columns = ["date", "team", "scored", "conceded"]
    away = df_all[["date", "away_team", "away_score", "home_score"]].dropna().copy()
    away.columns = ["date", "team", "scored", "conceded"]

    timeline = (
        pd.concat([home, away])
        .sort_values(["team", "date"])
        .reset_index(drop=True)
    )

    global_scored = float(df_all["home_score"].dropna().mean())
    global_conceded = float(df_all["away_score"].dropna().mean())

    target_teams = set(teams) if teams is not None else set(timeline["team"].unique())
    result: Dict[str, Dict[str, float]] = {}

    for team, grp in timeline.groupby("team"):
        if team not in target_teams:
            continue
        last_n = grp.tail(n)
        result[team] = {
            "goals_scored": float(last_n["scored"].mean()) if len(last_n) > 0 else global_scored,
            "goals_conceded": float(last_n["conceded"].mean()) if len(last_n) > 0 else global_conceded,
        }

    # Equipos sin historial → media global
    for team in target_teams:
        if team not in result:
            result[team] = {"goals_scored": global_scored, "goals_conceded": global_conceded}

    return result


def save_features(df: pd.DataFrame, path: Path = DATA_PROCESSED / "features.parquet") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
    logger.info("features.parquet guardado en %s", path)
