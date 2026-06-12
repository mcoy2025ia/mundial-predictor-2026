"""Carga y limpieza del dataset raw de resultados internacionales."""
import logging
from pathlib import Path
from typing import Dict, Optional

import pandas as pd

ROOT = Path(__file__).parent.parent
DATA_RAW = ROOT / "data" / "raw"
DATA_PROCESSED = ROOT / "data" / "processed"

logger = logging.getLogger(__name__)

# Federaciones sucesoras según FIFA: el historial completo se atribuye al
# equipo actual (igual que hace eloratings.net). Curaçao se normaliza a ASCII
# porque el fixture 2026 y el frontend usan "Curacao".
SUCCESSOR_MAP: Dict[str, str] = {
    "Czechoslovakia": "Czech Republic",
    "Yugoslavia": "Serbia",
    "Curaçao": "Curacao",
}

TEAM_COLS = ["home_team", "away_team", "winner", "first_shooter", "team"]


def load_former_names(path: Path = DATA_RAW / "former_names.csv") -> Dict[str, str]:
    """Construye el mapa former→current desde former_names.csv + sucesores FIFA.

    Encadena renombres (p.ej. Netherlands Antilles→Curaçao→Curacao).
    """
    mapping: Dict[str, str] = {}
    if path.exists():
        df = pd.read_csv(path)
        mapping.update(dict(zip(df["former"], df["current"])))
    mapping.update(SUCCESSOR_MAP)
    # resolver cadenas (máx. 3 saltos en la práctica)
    for former, current in mapping.items():
        seen = {former}
        while current in mapping and current not in seen:
            seen.add(current)
            current = mapping[current]
        mapping[former] = current
    return mapping


def normalize_team_names(df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """Reemplaza nombres históricos por el nombre actual en columnas de equipo."""
    if mapping is None:
        mapping = load_former_names()
    df = df.copy()
    n_replaced = 0
    for col in TEAM_COLS:
        if col in df.columns:
            mask = df[col].isin(mapping)
            n_replaced += int(mask.sum())
            df[col] = df[col].replace(mapping)
    logger.info("normalize_team_names: %d valores reemplazados", n_replaced)
    return df


def load_results(path: Path = DATA_RAW / "results.csv", normalize: bool = True) -> pd.DataFrame:
    """Carga results.csv, parsea date y normaliza nombres históricos."""
    df = pd.read_csv(path, parse_dates=["date"])
    if normalize:
        df = normalize_team_names(df)
    logger.info("results.csv cargado: %d filas", len(df))
    return df


def load_shootouts(path: Path = DATA_RAW / "shootouts.csv", normalize: bool = True) -> pd.DataFrame:
    """Carga shootouts.csv y normaliza nombres históricos."""
    df = pd.read_csv(path, parse_dates=["date"])
    if normalize:
        df = normalize_team_names(df)
    logger.info("shootouts.csv cargado: %d filas", len(df))
    return df


def filter_world_cups(df: pd.DataFrame) -> pd.DataFrame:
    """Filtra solo partidos de fase final del Mundial (excluye calificatorias)."""
    mask = df["tournament"] == "FIFA World Cup"
    df_wc = df[mask].copy()
    logger.info("Partidos de Mundial filtrados: %d", len(df_wc))
    return df_wc


def add_outcome(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega columna outcome desde perspectiva del equipo local."""
    import numpy as np

    df = df.copy()
    # np.select con strings falla en numpy>=2.0; usar np.where encadenado
    df["outcome"] = np.where(
        df["home_score"] > df["away_score"], "home_win",
        np.where(df["home_score"] == df["away_score"], "draw", "away_win"),
    )
    return df


def save_wc_clean(df: pd.DataFrame, path: Path = DATA_PROCESSED / "wc_clean.csv") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    logger.info("wc_clean.csv guardado en %s", path)
