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
K_FACTOR = 32.0


# ---------------------------------------------------------------------------
# ELO
# ---------------------------------------------------------------------------

def expected_score(rating_a: float, rating_b: float) -> float:
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(rating: float, expected: float, actual: float, k: float = K_FACTOR) -> float:
    return rating + k * (actual - expected)


def compute_elo_ratings(df_all: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, float]]:
    """Calcula ELO pre-match cronológicamente sobre todos los partidos.

    Retorna (df con elo_home/elo_away/elo_diff, dict ratings finales).
    Partidos sin score (NaN) registran el ELO actual pero no lo actualizan.
    """
    df = df_all.sort_values("date").reset_index(drop=True)
    ratings: Dict[str, float] = {}

    elo_home_pre = np.empty(len(df))
    elo_away_pre = np.empty(len(df))

    for i, row in enumerate(df.itertuples(index=False)):
        home, away = row.home_team, row.away_team
        r_home = ratings.get(home, INITIAL_ELO)
        r_away = ratings.get(away, INITIAL_ELO)

        elo_home_pre[i] = r_home
        elo_away_pre[i] = r_away

        hs, as_ = row.home_score, row.away_score
        if pd.isna(hs) or pd.isna(as_):
            continue

        exp_home = expected_score(r_home, r_away)
        if hs > as_:
            actual_home, actual_away = 1.0, 0.0
        elif hs == as_:
            actual_home = actual_away = 0.5
        else:
            actual_home, actual_away = 0.0, 1.0

        ratings[home] = update_elo(r_home, exp_home, actual_home)
        ratings[away] = update_elo(r_away, 1 - exp_home, actual_away)

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
# Pipeline completo
# ---------------------------------------------------------------------------

def build_feature_matrix(df_all: pd.DataFrame, df_wc: pd.DataFrame) -> pd.DataFrame:
    """Ensambla todas las features para los partidos de Mundial."""
    logger.info("ELO sobre %d partidos históricos...", len(df_all))
    df_elo, _ = compute_elo_ratings(df_all)

    wc = df_wc.merge(
        df_elo[["date", "home_team", "away_team", "elo_home", "elo_away", "elo_diff"]],
        on=["date", "home_team", "away_team"],
        how="left",
    )

    logger.info("Goles promedio últimos 5 partidos...")
    wc = compute_rolling_goals(df_all, wc, n=5)

    logger.info("H2H...")
    wc = compute_h2h(wc)

    logger.info("Experiencia en Mundiales...")
    wc = compute_wc_experience(wc)

    wc["is_neutral"] = wc["neutral"].astype(int)
    wc["year"] = wc["date"].dt.year

    feature_cols = [
        "date", "year", "home_team", "away_team", "outcome",
        "elo_diff", "elo_home", "elo_away",
        "home_goals_scored_avg5", "home_goals_conceded_avg5",
        "away_goals_scored_avg5", "away_goals_conceded_avg5",
        "h2h_home_win_pct", "is_neutral", "wc_experience_diff",
    ]
    df_features = wc[[c for c in feature_cols if c in wc.columns]].copy()
    logger.info("Feature matrix lista: %d filas, %d columnas", *df_features.shape)
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
