"""
Actualiza los scores NA de los partidos del WC 2026 en data/raw/results.csv
usando la API football-data.org. El fixture ya está pre-cargado en el CSV
con scores vacíos (NA); este script los rellena cuando el partido termina.

Exit codes:
  0 = sin cambios (no hay partidos nuevos terminados)
  2 = se actualizaron uno o más scores
  1 = error

Uso:
    python scripts/update_wc_results.py
    python scripts/update_wc_results.py --dry-run
    python scripts/update_wc_results.py --token TOKEN
"""

import argparse
import logging
import os
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

RESULTS_CSV = ROOT / "data" / "raw" / "results.csv"
LIVE_RESULTS_CSV = ROOT / "data" / "external" / "wc2026_live_results.csv"

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("update_wc_results")

# football-data.org team names → nuestros nombres normalizados
FD_NAME_MAP: dict[str, str] = {
    "Bosnia and Herzegovina": "Bosnia and Herzegovina",
    "Bosnia & Herzegovina":   "Bosnia and Herzegovina",
    "Bosnia-Herzegovina":     "Bosnia and Herzegovina",
    "Côte d'Ivoire":          "Ivory Coast",
    "Ivory Coast":            "Ivory Coast",
    "Curaçao":                "Curacao",
    "Curacao":                "Curacao",
    "Cura�ao":           "Curacao",   # CSV encoding artifact (0xE7 Latin-1 byte)
    "United States":          "United States",
    "USA":                    "United States",
    "DR Congo":               "DR Congo",
    "Congo DR":               "DR Congo",
    "Republic of Congo":      "DR Congo",
    "Czech Republic":         "Czech Republic",
    "Czechia":                "Czech Republic",
    "Cape Verde Islands":     "Cape Verde",
    "Cape Verde":             "Cape Verde",
    "Korea Republic":         "South Korea",
    "South Korea":            "South Korea",
    "New Zealand":            "New Zealand",
    "Saudi Arabia":           "Saudi Arabia",
    "IR Iran":                "Iran",
    "Iran":                   "Iran",
    "Germany":                "Germany",
}


def _normalize(name: str) -> str:
    return FD_NAME_MAP.get(name, name)


def _load_token(override: str | None) -> str:
    if override:
        return override.strip()
    token = os.environ.get("FOOTBALL_DATA_TOKEN", "")
    # Buscar en archivos .env si no está en el entorno
    for env_file in [ROOT / "frontend" / ".env.local", ROOT / ".env"]:
        if not token and env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line.startswith("FOOTBALL_DATA_TOKEN="):
                    token = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    # Quitar BOM que PowerShell puede inyectar
    if token and ord(token[0]) == 0xFEFF:
        token = token[1:]
    return token.strip()


def _fetch_finished(token: str) -> list[dict]:
    url = "https://api.football-data.org/v4/competitions/WC/matches"
    resp = requests.get(url, headers={"X-Auth-Token": token}, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    return [m for m in data.get("matches", []) if m.get("status") == "FINISHED"]


def main(dry_run: bool = False, token_override: str | None = None) -> int:
    """
    Devuelve el número de filas actualizadas, 0 si nada cambió, -1 si error.
    """
    token = _load_token(token_override)
    if not token:
        logger.error(
            "FOOTBALL_DATA_TOKEN no encontrado.\n"
            "  Agrega FOOTBALL_DATA_TOKEN=<token> a frontend/.env.local\n"
            "  o exporta: export FOOTBALL_DATA_TOKEN=<token>"
        )
        return -1

    logger.info("Consultando football-data.org...")
    try:
        finished = _fetch_finished(token)
    except requests.HTTPError as e:
        logger.error("HTTP error: %s", e)
        return -1
    except Exception as e:
        logger.error("Error de red: %s", e)
        return -1

    logger.info("%d partido(s) terminado(s) en la API", len(finished))

    if not finished:
        logger.info("El torneo aún no ha comenzado o no hay partidos terminados.")
        return 0

    # Cargar el CSV completo
    df = pd.read_csv(RESULTS_CSV, parse_dates=["date"])

    # Máscara de filas del WC 2026 que todavía tienen scores vacíos
    wc2026_na_mask = (
        (df["tournament"] == "FIFA World Cup") &
        (df["date"].dt.year == 2026) &
        (df["home_score"].isna() | df["away_score"].isna())
    )
    wc2026_done_mask = (
        (df["tournament"] == "FIFA World Cup") &
        (df["date"].dt.year == 2026) &
        df["home_score"].notna() & df["away_score"].notna()
    )
    logger.info(
        "WC 2026 en CSV: %d con scores  /  %d pendientes (NA)",
        wc2026_done_mask.sum(), wc2026_na_mask.sum(),
    )

    updated = 0
    skipped_done = 0
    not_found = []

    for m in finished:
        home_raw = (m.get("homeTeam") or {}).get("name") or ""
        away_raw = (m.get("awayTeam") or {}).get("name") or ""
        score_ft  = (m.get("score") or {}).get("fullTime") or {}
        home_score = score_ft.get("home")
        away_score = score_ft.get("away")

        if not home_raw or not away_raw or home_score is None or away_score is None:
            continue

        home = _normalize(home_raw)
        away = _normalize(away_raw)

        # Buscar la fila del WC 2026 con estos equipos (sin importar fecha UTC vs local)
        # Normalize both sides to handle CSV encoding artifacts (e.g. Curaçao → Curacao)
        row_mask = (
            (df["tournament"] == "FIFA World Cup") &
            (df["date"].dt.year == 2026) &
            (df["home_team"].apply(_normalize) == home) &
            (df["away_team"].apply(_normalize) == away)
        )
        matches_found = df[row_mask]

        if matches_found.empty:
            not_found.append(f"{home} vs {away}")
            continue

        idx = matches_found.index[0]
        existing_h = df.at[idx, "home_score"]
        existing_a = df.at[idx, "away_score"]

        already_has_score = (
            pd.notna(existing_h) and pd.notna(existing_a) and
            str(existing_h) != "NA" and str(existing_a) != "NA"
        )
        if already_has_score:
            logger.debug("Ya tiene score: %s %s-%s %s", home, existing_h, existing_a, away)
            skipped_done += 1
            continue

        logger.info(
            "  [UPDATE] %-25s %d - %d  %s",
            home, int(home_score), int(away_score), away,
        )
        if not dry_run:
            df.at[idx, "home_score"] = int(home_score)
            df.at[idx, "away_score"] = int(away_score)
        updated += 1

    if not_found:
        logger.warning(
            "Partidos de la API no encontrados en el CSV (puede ser nombre distinto): %s",
            ", ".join(not_found),
        )

    logger.info(
        "Resumen: %d actualizado(s)  /  %d ya tenían score  /  %d no encontrados",
        updated, skipped_done, len(not_found),
    )

    if dry_run:
        if updated == 0:
            logger.info("Sin cambios — todos los partidos ya están al día.")
        else:
            logger.info("[DRY-RUN] No se escribió nada en results.csv.")
        return updated

    if updated > 0:
        # Escribir CSV preservando el formato original (sin comillas innecesarias)
        df.to_csv(RESULTS_CSV, index=False)
        logger.info("results.csv guardado con %d score(s) actualizado(s).", updated)
    else:
        logger.info("Sin cambios — todos los partidos ya están al día.")

    # Siempre sincronizar wc2026_live_results.csv con el estado actual de results.csv,
    # incluso si esta corrida no trajo partidos nuevos (corrige desincronizaciones previas).
    _sync_live_results_csv(df)

    return updated


def _sync_live_results_csv(df: pd.DataFrame) -> None:
    """Regenera wc2026_live_results.csv a partir de results.csv (fuente única de verdad).

    results.csv es la única fuente actualizada automáticamente por football-data.org.
    wc2026_live_results.csv es consumido por predict_live.py y precompute_narrations.py
    para detectar qué partidos del WC 2026 ya se jugaron. Si no se sincroniza en cada
    corrida, queda obsoleto y produce narrativas/standings incoherentes con el resultado real.

    Aplica la misma normalización de nombres que src.extractor.load_former_names()
    (p.ej. "Curaçao" → "Curacao") para que los nombres coincidan exactamente con
    los usados en group_matches.json y el resto del pipeline ya normalizado;
    de lo contrario el matching por (home_team, away_team) falla silenciosamente
    y el partido queda como "no jugado" en las narrativas aunque ya tenga resultado.
    """
    sys.path.insert(0, str(ROOT))
    from src.extractor import load_former_names
    name_map = load_former_names()

    played_mask = (
        (df["tournament"] == "FIFA World Cup") &
        (df["date"].dt.year == 2026) &
        df["home_score"].notna() & df["away_score"].notna()
    )
    played = df.loc[played_mask, [
        "date", "home_team", "away_team", "home_score", "away_score",
        "tournament", "city", "country", "neutral",
    ]].copy()
    played["home_team"] = played["home_team"].apply(lambda t: name_map.get(t, t))
    played["away_team"] = played["away_team"].apply(lambda t: name_map.get(t, t))
    played["home_score"] = played["home_score"].astype(int)
    played["away_score"] = played["away_score"].astype(int)
    played["date"] = played["date"].dt.strftime("%Y-%m-%d")
    played = played.sort_values("date")

    LIVE_RESULTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    played.to_csv(LIVE_RESULTS_CSV, index=False)
    logger.info("wc2026_live_results.csv sincronizado: %d partido(s) jugado(s).", len(played))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Actualiza scores NA de WC 2026 en results.csv"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Muestra qué se actualizaría sin escribir nada")
    parser.add_argument("--token", default=None,
                        help="Token football-data.org (sobreescribe env var)")
    args = parser.parse_args()

    n = main(dry_run=args.dry_run, token_override=args.token)
    if n < 0:
        sys.exit(1)
    elif n == 0:
        sys.exit(0)
    else:
        sys.exit(2)
