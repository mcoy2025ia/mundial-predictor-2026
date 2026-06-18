"""
Modo live — Predicción durante el Mundial 2026.

Por cada partido del fixture:
  cutoff = kickoff - epsilon
  features = ELO + forma calculados con todos los partidos ANTERIORES al cutoff
  (incluyendo resultados ya jugados del propio Mundial 2026)

Uso:
  python scripts/predict_live.py                       # predice partidos pendientes
  python scripts/predict_live.py --all                 # predice todos (incluye ya jugados)
  python scripts/predict_live.py --export              # re-exporta JSONs del frontend
  python scripts/predict_live.py --add-result HOME AWAY HS AS DATE
                                                       # registra un resultado jugado

Anti-leakage garantizado:
  assert features_cutoff < match_kickoff
  Si se detecta fuga → el script aborta.
"""
import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.extractor import load_results, load_former_names
from src.pipeline_logger import run_context
from src.features import compute_elo_ratings, compute_current_form
from src.model import load_model
from src.ensemble import DEFAULT_WEIGHTS, _elo_proba as elo_proba
from src.poisson_model import PoissonModel

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("predict_live")

FIXTURE_PATH = ROOT / "data" / "external" / "wc2026_fixture.json"
LIVE_RESULTS_PATH = ROOT / "data" / "external" / "wc2026_live_results.csv"
OUT_DIR = ROOT / "frontend" / "public" / "data"

EPSILON = timedelta(seconds=60)  # cutoff = kickoff - 60s

# Mapeo nombres del fixture → nombres del dataset (results.csv)
_FIXTURE_TO_DATASET: dict[str, str] = {
    "USA": "United States",
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "Curaçao": "Curacao",
}

# Sedes de cada anfitrión (para determinar is_neutral)
_MEXICO_GROUNDS = {"Mexico City", "Guadalajara", "Guadalajara (Zapopan)", "Monterrey"}
_CANADA_GROUNDS = {"Vancouver", "Toronto"}


def _norm_team(name: str) -> str:
    """Normaliza un nombre de equipo del fixture al nombre canónico del dataset."""
    name = _FIXTURE_TO_DATASET.get(name, name)
    # Aplicar el mapping de nombres históricos del extractor
    try:
        mapping = load_former_names()
        return mapping.get(name, name)
    except Exception:
        return name


def _is_neutral(team1: str, team2: str, ground: str) -> bool:
    """True si la sede no pertenece a ninguna de las selecciones anfitrionas."""
    teams = {team1, team2}
    # México juega en casa en sus tres ciudades
    if "Mexico" in teams and any(g in ground for g in _MEXICO_GROUNDS):
        return False
    # Canadá juega en casa en Toronto o Vancouver
    if "Canada" in teams and any(g in ground for g in _CANADA_GROUNDS):
        return False
    # USA juega en casa en cualquier ciudad de EEUU (las que no son México ni Canadá)
    if ("United States" in teams) and (
        not any(g in ground for g in _MEXICO_GROUNDS)
        and not any(g in ground for g in _CANADA_GROUNDS)
    ):
        return False
    return True


def _parse_kickoff(date_str: str, time_str: str) -> datetime:
    """Convierte 'YYYY-MM-DD' + 'HH:MM UTC±X' a datetime UTC (naive)."""
    m = re.match(r"(\d{2}):(\d{2})\s+UTC([+-]\d+)", time_str)
    if m:
        h, mn, offset = int(m.group(1)), int(m.group(2)), int(m.group(3))
        parts = [int(x) for x in date_str.split("-")]
        local_dt = datetime(parts[0], parts[1], parts[2], h, mn)
        return local_dt - timedelta(hours=offset)
    # Fallback: solo la fecha a las 20:00 UTC
    parts = [int(x) for x in date_str.split("-")]
    return datetime(parts[0], parts[1], parts[2], 20, 0)


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

def load_fixture() -> list[dict]:
    """Carga partidos del fixture oficial (wc2026_fixture.json).

    Normaliza team1/team2 → home_team/away_team con nombres del dataset.
    Solo devuelve partidos con equipos reales (no placeholders tipo W101, 1A, etc.).
    """
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        data = json.load(f)

    _placeholder = re.compile(r"^(W|L|Runner|1[A-L]|2[A-L]|3[A-L])")

    matches = []
    for raw in data.get("matches", []):
        t1_raw = raw.get("team1", "")
        t2_raw = raw.get("team2", "")
        if _placeholder.match(t1_raw) or _placeholder.match(t2_raw):
            continue

        kickoff = _parse_kickoff(raw.get("date", ""), raw.get("time", ""))
        t1 = _norm_team(t1_raw)
        t2 = _norm_team(t2_raw)
        ground = raw.get("ground", "")

        matches.append({
            "home_team": t1,
            "away_team": t2,
            "kickoff": kickoff,
            "kickoff_str": kickoff.strftime("%Y-%m-%dT%H:%M:00"),
            "stage": "group" if raw.get("group") else "knockout",
            "group": raw.get("group", ""),
            "venue": ground,
            "is_neutral": _is_neutral(t1, t2, ground),
            "round": raw.get("round", ""),
        })

    logger.info("Fixture cargado: %d partidos con equipos reales", len(matches))
    return matches


# ---------------------------------------------------------------------------
# Resultados en vivo
# ---------------------------------------------------------------------------

def load_live_results() -> pd.DataFrame:
    """Carga resultados del Mundial 2026 ya registrados en el CSV de live."""
    schema_cols = ["date", "home_team", "away_team", "home_score", "away_score",
                   "tournament", "city", "country", "neutral"]
    if not LIVE_RESULTS_PATH.exists():
        logger.info("Sin resultados en vivo registrados aún (%s no existe).", LIVE_RESULTS_PATH)
        return pd.DataFrame(columns=schema_cols)

    df = pd.read_csv(LIVE_RESULTS_PATH)
    df["date"] = pd.to_datetime(df["date"])
    df["neutral"] = df.get("neutral", True).fillna(True).astype(bool)
    df["tournament"] = df.get("tournament", "FIFA World Cup").fillna("FIFA World Cup")
    logger.info("Resultados en vivo: %d partidos cargados de %s", len(df), LIVE_RESULTS_PATH)
    return df


def add_live_result(
    home_team: str,
    away_team: str,
    home_score: int,
    away_score: int,
    date: str,
    city: str = "",
    neutral: bool = True,
) -> None:
    """Registra un resultado jugado en wc2026_live_results.csv."""
    row = {
        "date": date,
        "home_team": _norm_team(home_team),
        "away_team": _norm_team(away_team),
        "home_score": home_score,
        "away_score": away_score,
        "tournament": "FIFA World Cup",
        "city": city,
        "country": "USA/Mexico/Canada",
        "neutral": neutral,
    }
    LIVE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LIVE_RESULTS_PATH.exists():
        df = pd.read_csv(LIVE_RESULTS_PATH)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.to_csv(LIVE_RESULTS_PATH, index=False)
    logger.info(
        "Resultado registrado: %s %d-%d %s (%s)",
        row["home_team"], home_score, away_score, row["away_team"], date,
    )


# ---------------------------------------------------------------------------
# Anti-leakage
# ---------------------------------------------------------------------------

def assert_no_leakage(features_cutoff: datetime, match_kickoff: datetime) -> None:
    if features_cutoff >= match_kickoff:
        raise ValueError(
            f"LEAKAGE DETECTADO: features_cutoff={features_cutoff} >= kickoff={match_kickoff}."
        )


# ---------------------------------------------------------------------------
# Features en vivo
# ---------------------------------------------------------------------------

def build_live_features(
    df_all: pd.DataFrame,
    df_live: pd.DataFrame,
    cutoff: datetime,
) -> tuple[pd.DataFrame, dict]:
    """Construye ELO y forma con todos los datos ANTERIORES al cutoff.

    Combina el histórico completo (df_all) con los resultados del torneo
    en curso que preceden al cutoff.
    """
    if len(df_live) > 0:
        df_live_played = df_live[
            (df_live["date"] < pd.Timestamp(cutoff)) &
            df_live["home_score"].notna() &
            df_live["away_score"].notna()
        ].copy()
        if len(df_live_played) > 0:
            df_combined = pd.concat([df_all, df_live_played], ignore_index=True)
            df_combined = df_combined.sort_values("date").reset_index(drop=True)
            logger.debug(
                "Live: %d resultados del torneo añadidos (cutoff=%s)",
                len(df_live_played), cutoff.strftime("%Y-%m-%d %H:%M"),
            )
        else:
            df_combined = df_all
    else:
        df_combined = df_all

    _, ratings = compute_elo_ratings(df_combined)
    return df_combined, ratings


# ---------------------------------------------------------------------------
# Predicción de un partido
# ---------------------------------------------------------------------------

def predict_single_match(
    home_team: str,
    away_team: str,
    elo_ratings: dict,
    df_combined: pd.DataFrame,
    model,
    poisson_model: Optional[PoissonModel] = None,
    is_neutral: bool = True,
    kickoff: Optional[datetime] = None,
) -> dict:
    """Predice un partido construyendo el vector de features con ELO en vivo."""
    from src.model import FEATURE_COLS

    DEFAULT_ELO = 1500.0
    DEFAULT_GOALS = 1.3
    DEFAULT_CONC = 1.1

    def _form(team: str) -> tuple[float, float]:
        """Retorna (avg_scored, avg_conceded) de los últimos 5 partidos."""
        mask = (df_combined["home_team"] == team) | (df_combined["away_team"] == team)
        rows = df_combined[mask & df_combined["home_score"].notna()].sort_values("date").tail(5)
        if rows.empty:
            return DEFAULT_GOALS, DEFAULT_CONC
        scored, conceded = [], []
        for r in rows.itertuples():
            if r.home_team == team:
                scored.append(float(r.home_score))
                conceded.append(float(r.away_score))
            else:
                scored.append(float(r.away_score))
                conceded.append(float(r.home_score))
        return float(sum(scored) / len(scored)), float(sum(conceded) / len(conceded))

    def _h2h(t1: str, t2: str) -> float:
        mask = (
            ((df_combined["home_team"] == t1) & (df_combined["away_team"] == t2)) |
            ((df_combined["home_team"] == t2) & (df_combined["away_team"] == t1))
        ) & df_combined["home_score"].notna()
        h2h = df_combined[mask]
        if h2h.empty:
            return 0.5
        from src.extractor import add_outcome
        h2h = add_outcome(h2h.copy())
        wins = (
            ((h2h["home_team"] == t1) & (h2h["outcome"] == "home_win")).sum() +
            ((h2h["away_team"] == t1) & (h2h["outcome"] == "away_win")).sum()
        )
        return float(wins) / len(h2h)

    def _wc_exp(team: str) -> int:
        mask = (
            ((df_combined["home_team"] == team) | (df_combined["away_team"] == team)) &
            (df_combined.get("tournament", pd.Series()) == "FIFA World Cup")
        )
        return int(mask.sum()) if "tournament" in df_combined.columns else 0

    elo_h = elo_ratings.get(home_team, DEFAULT_ELO)
    elo_a = elo_ratings.get(away_team, DEFAULT_ELO)
    gs_h, gc_h = _form(home_team)
    gs_a, gc_a = _form(away_team)

    row = pd.DataFrame([{
        "elo_diff": elo_h - elo_a,
        "elo_home": elo_h,
        "elo_away": elo_a,
        "home_goals_scored_avg5": gs_h,
        "home_goals_conceded_avg5": gc_h,
        "away_goals_scored_avg5": gs_a,
        "away_goals_conceded_avg5": gc_a,
        "h2h_home_win_pct": _h2h(home_team, away_team),
        "is_neutral": int(is_neutral),
        "wc_experience_diff": _wc_exp(home_team) - _wc_exp(away_team),
    }])[FEATURE_COLS]

    proba_xgb = model.predict_proba(row)[0]
    p_elo = np.array(elo_proba(elo_h, elo_a, is_neutral))
    p_xgb = np.array([float(proba_xgb[0]), float(proba_xgb[1]), float(proba_xgb[2])])

    probs = [p_elo, p_xgb]
    weights = [DEFAULT_WEIGHTS["elo"], DEFAULT_WEIGHTS["xgb"]]
    payload_extra = {
        "xgb_home": round(float(p_xgb[0]), 4),
        "xgb_draw": round(float(p_xgb[1]), 4),
        "xgb_away": round(float(p_xgb[2]), 4),
        "elo_home": round(float(p_elo[0]), 4),
        "elo_draw": round(float(p_elo[1]), 4),
        "elo_away": round(float(p_elo[2]), 4),
    }

    if poisson_model is not None:
        try:
            lam_h, lam_a = poisson_model.predict_goals(
                home_team,
                away_team,
                is_neutral=is_neutral,
                elo_diff=elo_h - elo_a,
            )
            matrix = poisson_model.scoreline_matrix(lam_h, lam_a)
            p_poi = np.array(poisson_model.aggregate_1x2(matrix))
            probs.append(p_poi)
            weights.append(DEFAULT_WEIGHTS["poisson"])
            payload_extra.update({
                "poisson_home": round(float(p_poi[0]), 4),
                "poisson_draw": round(float(p_poi[1]), 4),
                "poisson_away": round(float(p_poi[2]), 4),
                "top_scorelines": poisson_model.top_scorelines(matrix, n=5),
                "lambda_home": round(float(lam_h), 3),
                "lambda_away": round(float(lam_a), 3),
            })
        except Exception as e:
            logger.debug("Poisson skipped for %s vs %s: %s", home_team, away_team, e)

    weight_arr = np.array(weights, dtype=float)
    weight_arr /= weight_arr.sum()
    proba = sum(p * w for p, w in zip(probs, weight_arr))
    proba /= proba.sum()

    return {
        "home_team": home_team,
        "away_team": away_team,
        "p_home": round(float(proba[0]), 4),
        "p_draw": round(float(proba[1]), 4),
        "p_away": round(float(proba[2]), 4),
        "is_neutral": is_neutral,
        "kickoff": kickoff.isoformat() if kickoff else None,
        "model": "ensemble_live",
        "ensemble_weights": DEFAULT_WEIGHTS,
        **payload_extra,
    }


# ---------------------------------------------------------------------------
# Contexto de grupo: standings, presión, viajes
# ---------------------------------------------------------------------------

def compute_group_standings(
    fixture: list[dict],
    df_wc26_played: pd.DataFrame,
) -> dict[str, dict]:
    """Computa puntos, GD y GF actuales para cada equipo en cada grupo.

    Returns:
        dict[group_name → dict[team → {"pts": int, "gd": int, "gf": int, "played": int}]]
    """
    standings: dict[str, dict] = {}

    # Inicializar todos los equipos del grupo
    for m in fixture:
        grp = m.get("group", "")
        if not grp:
            continue
        for team in (m["home_team"], m["away_team"]):
            standings.setdefault(grp, {}).setdefault(
                team, {"pts": 0, "gd": 0, "gf": 0, "played": 0}
            )

    # Llenar con resultados jugados
    for _, row in df_wc26_played.iterrows():
        home = str(row["home_team"])
        away = str(row["away_team"])
        hs = int(row["home_score"])
        as_ = int(row["away_score"])

        # Buscar el grupo de este partido en el fixture
        grp = None
        for m in fixture:
            if m["home_team"] == home and m["away_team"] == away:
                grp = m.get("group", "")
                break
        if not grp:
            continue

        s = standings.get(grp, {})
        if home not in s or away not in s:
            continue

        # Actualizar stats
        s[home]["gf"] += hs; s[home]["gd"] += hs - as_; s[home]["played"] += 1
        s[away]["gf"] += as_; s[away]["gd"] += as_ - hs; s[away]["played"] += 1

        if hs > as_:
            s[home]["pts"] += 3
        elif hs == as_:
            s[home]["pts"] += 1; s[away]["pts"] += 1
        else:
            s[away]["pts"] += 3

    return standings


def build_third_place_context(standings: dict[str, dict]) -> str:
    """Build a compact current best-third snapshot across all groups."""
    thirds: list[tuple[str, str, dict]] = []
    for grp, teams in standings.items():
        ordered = sorted(
            teams.items(),
            key=lambda x: (-x[1]["pts"], -x[1]["gd"], -x[1]["gf"], x[0]),
        )
        if len(ordered) >= 3:
            team, data = ordered[2]
            thirds.append((grp, team, data))

    thirds.sort(key=lambda x: (-x[2]["pts"], -x[2]["gd"], -x[2]["gf"], x[1]))
    if not thirds:
        return ""

    cut = thirds[7] if len(thirds) >= 8 else thirds[-1]
    rows = [
        f"{i+1}.{grp[-1]}:{team} {data['pts']}pts GD{data['gd']:+d} GF{data['gf']}"
        for i, (grp, team, data) in enumerate(thirds[:12])
    ]
    cut_grp, cut_team, cut_data = cut
    return (
        f"best_third_cutline={cut_grp[-1]}:{cut_team} "
        f"{cut_data['pts']}pts GD{cut_data['gd']:+d} GF{cut_data['gf']}; "
        + " ".join(rows)
    )


def build_simultaneous_group_context(match: dict, fixture: list[dict]) -> str:
    """List same-group matches with the exact same kickoff, mainly for MD3."""
    grp = match.get("group", "")
    kickoff = match.get("kickoff")
    if not grp or kickoff is None:
        return ""
    peers = []
    for m in fixture:
        if m is match:
            continue
        if m.get("group") != grp or m.get("kickoff") != kickoff:
            continue
        peers.append(f"{m['home_team']} vs {m['away_team']}")
    return "; ".join(peers)


def get_group_context(
    match: dict,
    fixture: list[dict],
    standings: dict[str, dict],
    df_wc26_played: pd.DataFrame,
) -> dict:
    """Construye el contexto de grupo para un partido pendiente.

    Devuelve kwargs listos para MatchContext: group_name, group_points_home/away, etc.
    """
    grp = match.get("group", "")
    if not grp or grp not in standings:
        return {}

    home = match["home_team"]
    away = match["away_team"]
    grp_data = standings[grp]

    if home not in grp_data or away not in grp_data:
        return {}

    # Ordenar para standings string
    sorted_teams = sorted(grp_data.items(), key=lambda x: (-x[1]["pts"], -x[1]["gd"], -x[1]["gf"]))
    standings_str = " ".join(
        f"{i+1}.{t} {d['pts']}pts" for i, (t, d) in enumerate(sorted_teams)
    )

    # Matchday del grupo: contamos cuántos partidos del grupo se han jugado para este equipo
    games_played_home = grp_data[home]["played"]
    games_played_away = grp_data[away]["played"]
    matchday = max(games_played_home, games_played_away) + 1  # 1-based, este es el siguiente

    # Ciudad previa de cada equipo (último partido jugado del WC 2026)
    def _prev_city(team: str) -> Optional[str]:
        played_team = df_wc26_played[
            (df_wc26_played["home_team"] == team) | (df_wc26_played["away_team"] == team)
        ].sort_values("date")
        if played_team.empty:
            return None
        last = played_team.iloc[-1]
        last_home = str(last["home_team"]); last_away = str(last["away_team"])
        for m in fixture:
            if m["home_team"] == last_home and m["away_team"] == last_away:
                return m.get("venue", m.get("ground", None))
        return None

    # Días de descanso desde el último partido
    def _days_rest(team: str) -> Optional[int]:
        played_team = df_wc26_played[
            (df_wc26_played["home_team"] == team) | (df_wc26_played["away_team"] == team)
        ].sort_values("date")
        if played_team.empty:
            return None
        last_date = pd.Timestamp(played_team.iloc[-1]["date"])
        match_date = pd.Timestamp(match["kickoff"].date())
        return max(0, (match_date - last_date).days)

    venue = match.get("venue", "")
    # Normalizar ciudad (quitar paréntesis)
    if "(" in venue:
        venue = venue.split("(")[0].strip()

    return {
        "group_name": grp,
        "group_points_home": grp_data[home]["pts"],
        "group_points_away": grp_data[away]["pts"],
        "games_played_home": games_played_home,
        "games_played_away": games_played_away,
        "matchday": matchday,
        "days_rest_home": _days_rest(home),
        "days_rest_away": _days_rest(away),
        "prev_city_home": _prev_city(home),
        "prev_city_away": _prev_city(away),
        "group_standings": standings_str,
        "simultaneous_group_matches": build_simultaneous_group_context(match, fixture),
        "third_place_context": build_third_place_context(standings),
        "venue_city": venue,
    }


def enrich_with_orchestrator(pred: dict, match: dict, group_ctx: dict,
                              elo_ratings: dict) -> dict:
    """Aplica el Orchestrator al prior del ensemble y devuelve probs ajustadas.

    Si el Orchestrator falla (sin API key, budget agotado, etc.), devuelve pred sin cambios.
    """
    try:
        from src.agents.base import MatchContext
        from src.agents.orchestrator import Orchestrator

        altitude = _CITY_ALTITUDE_M.get(group_ctx.get("venue_city", ""), 0)

        ctx = MatchContext(
            team_home=pred["home_team"],
            team_away=pred["away_team"],
            p_home=pred["p_home"],
            p_draw=pred["p_draw"],
            p_away=pred["p_away"],
            elo_home=float(elo_ratings.get(pred["home_team"], 1500)),
            elo_away=float(elo_ratings.get(pred["away_team"], 1500)),
            is_neutral=pred.get("is_neutral", True),
            venue_city=group_ctx.get("venue_city"),
            venue_altitude_m=altitude,
            round_label=f"{group_ctx.get('group_name', '')} MD{group_ctx.get('matchday', '')}",
            group_name=group_ctx.get("group_name"),
            group_points_home=group_ctx.get("group_points_home"),
            group_points_away=group_ctx.get("group_points_away"),
            games_played_home=group_ctx.get("games_played_home", 0),
            games_played_away=group_ctx.get("games_played_away", 0),
            matchday=group_ctx.get("matchday"),
            days_rest_home=group_ctx.get("days_rest_home"),
            days_rest_away=group_ctx.get("days_rest_away"),
            prev_city_home=group_ctx.get("prev_city_home"),
            prev_city_away=group_ctx.get("prev_city_away"),
            group_standings=group_ctx.get("group_standings"),
            simultaneous_group_matches=group_ctx.get("simultaneous_group_matches"),
            third_place_context=group_ctx.get("third_place_context"),
        )

        out = Orchestrator().predict(ctx)
        pred["p_home"] = out.adjusted["home"]
        pred["p_draw"] = out.adjusted["draw"]
        pred["p_away"] = out.adjusted["away"]
        pred["agents"] = out.agents_called
        pred["agent_notes"] = {r.agent_name: r.notes for r in out.agent_results}
        pred["model"] = "ensemble_agent_adjusted"
    except Exception as e:
        logger.debug("Orchestrator skipped for %s vs %s: %s",
                     pred.get("home_team"), pred.get("away_team"), e)
    return pred


# Altitudes de sedes WC 2026 (metros)
_CITY_ALTITUDE_M: dict[str, int] = {
    "Mexico City": 2240,
    "Guadalajara": 1566,
    "Monterrey":   539,
    "Denver":      1609,
    "Dallas":      139,
    "Houston":     15,
    "Miami":       2,
    "Atlanta":     320,
    "Kansas City": 265,
    "Philadelphia": 12,
    "New York":    10,
    "Los Angeles": 71,
    "San Francisco": 16,
    "Seattle":     56,
    "Boston":      9,
    "Vancouver":   70,
    "Toronto":     76,
}


# ---------------------------------------------------------------------------
# Flujo principal
# ---------------------------------------------------------------------------

def run_live_predictions(
    predict_all: bool = False,
    export: bool = False,
    use_agents: bool = True,
) -> list[dict]:
    _artifacts = [ROOT / "data" / "processed" / "live_predictions.json"]
    if export:
        _artifacts.append(ROOT / "frontend" / "public" / "data" / "live_predictions.json")
    with run_context("live_update", artifacts=_artifacts) as _ctx:
        results = _run_live_predictions(predict_all, export, use_agents, _ctx)
    return results


def _run_live_predictions(
    predict_all: bool,
    export: bool,
    use_agents: bool,
    _ctx: dict,
) -> list[dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    df_all = load_results()
    df_live = load_live_results()
    model = load_model()
    try:
        poisson_model = PoissonModel.load()
    except Exception as e:
        logger.warning("Poisson no disponible (%s). Live usará ELO+XGB renormalizado.", e)
        poisson_model = None
    fixture = load_fixture()

    # Resultados WC 2026 jugados (de results.csv) para computar standings
    from src.extractor import add_outcome
    df_wc26_played = df_all[
        (df_all["tournament"] == "FIFA World Cup") &
        (df_all["date"].dt.year == 2026) &
        df_all["home_score"].notna()
    ].copy()

    group_standings = compute_group_standings(fixture, df_wc26_played)

    results = []
    _cached_cutoff: Optional[datetime] = None
    _cached_df: Optional[pd.DataFrame] = None
    _cached_ratings: Optional[dict] = None

    for match in fixture:
        kickoff: datetime = match["kickoff"]
        is_played = kickoff < now

        if is_played and not predict_all:
            continue

        cutoff = kickoff - EPSILON
        assert_no_leakage(features_cutoff=cutoff, match_kickoff=kickoff)

        # Cache el ELO/df si el cutoff no cambió (evita recalcular 88 veces)
        if _cached_cutoff != cutoff:
            _cached_df, _cached_ratings = build_live_features(df_all, df_live, cutoff)
            _cached_cutoff = cutoff

        try:
            pred = predict_single_match(
                match["home_team"], match["away_team"],
                elo_ratings=_cached_ratings,
                df_combined=_cached_df,
                model=model,
                poisson_model=poisson_model,
                is_neutral=match["is_neutral"],
                kickoff=kickoff,
            )
        except Exception as e:
            logger.warning("No se pudo predecir %s vs %s: %s",
                           match["home_team"], match["away_team"], e)
            continue

        pred["stage"] = match["stage"]
        pred["group"] = match["group"]
        pred["venue"] = match["venue"]
        pred["round"] = match["round"]

        if match["stage"] == "group":
            group_ctx = get_group_context(match, fixture, group_standings, df_wc26_played)
            if group_ctx:
                pred["group_context"] = {
                    "group_name": group_ctx.get("group_name"),
                    "matchday": group_ctx.get("matchday"),
                    "home_points": group_ctx.get("group_points_home"),
                    "away_points": group_ctx.get("group_points_away"),
                    "home_games_played": group_ctx.get("games_played_home"),
                    "away_games_played": group_ctx.get("games_played_away"),
                    "group_standings": group_ctx.get("group_standings"),
                    "simultaneous_group_matches": group_ctx.get("simultaneous_group_matches"),
                    "third_place_context": group_ctx.get("third_place_context"),
                }

        # Enriquecer con agentes si es fase de grupos
        if use_agents and match["stage"] == "group" and _cached_ratings is not None:
            group_ctx = get_group_context(match, fixture, group_standings, df_wc26_played)
            if group_ctx:
                pred = enrich_with_orchestrator(pred, match, group_ctx, _cached_ratings)

        results.append(pred)

        logger.info(
            "%-25s vs %-25s  H:%5.1f%% D:%5.1f%% A:%5.1f%%  [%s]",
            match["home_team"], match["away_team"],
            pred["p_home"] * 100, pred["p_draw"] * 100, pred["p_away"] * 100,
            "played" if is_played else "pending",
        )

    _ctx["meta"] = {
        "n_live_results": len(df_live),
        "n_predictions": len(results),
        "predict_all": predict_all,
        "export": export,
        "use_agents": use_agents,
    }

    if not results:
        logger.info("Sin partidos para predecir.")
        return results

    # Guardar en data/processed/
    live_out = ROOT / "data" / "processed" / "live_predictions.json"
    live_out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": now.isoformat(),
        "mode": "live",
        "live_results_used": len(df_live),
        "n_predictions": len(results),
        "predictions": results,
    }
    with open(live_out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    logger.info("live_predictions.json guardado: %d partidos → %s", len(results), live_out)

    if export:
        pred_frontend = OUT_DIR / "live_predictions.json"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        with open(pred_frontend, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        logger.info("Exportado al frontend: %s", pred_frontend)

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Predicciones en vivo — Mundial 2026")
    parser.add_argument("--all", action="store_true",
                        help="Incluir partidos ya jugados")
    parser.add_argument("--export", action="store_true",
                        help="Copiar live_predictions.json al frontend/public/data/")
    parser.add_argument("--no-agents", action="store_true",
                        help="No llamar agentes LLM; exporta solo el Ensemble determinístico")
    parser.add_argument(
        "--add-result", nargs=5,
        metavar=("HOME", "AWAY", "HS", "AS", "DATE"),
        help="Registrar resultado: HOME AWAY goles_home goles_away YYYY-MM-DD",
    )
    args = parser.parse_args()

    if args.add_result:
        home, away, hs, as_, date = args.add_result
        add_live_result(home, away, int(hs), int(as_), date)
    else:
        run_live_predictions(
            predict_all=args.all,
            export=args.export,
            use_agents=not args.no_agents,
        )
