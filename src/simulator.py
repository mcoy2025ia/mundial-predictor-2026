"""Simulador de torneo Mundial 2026 con Monte Carlo."""
import json
import logging
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.model import FEATURE_COLS

ROOT = Path(__file__).resolve().parent.parent
DATA_EXTERNAL = ROOT / "data" / "external"
DATA_PROCESSED = ROOT / "data" / "processed"
FIXTURE_PATH = DATA_EXTERNAL / "wc2026_fixture.json"

logger = logging.getLogger(__name__)

DEFAULT_ELO = 1500.0

NAME_MAP: Dict[str, str] = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
    "Curaçao": "Curacao",
}

WC2026_GROUPS: Dict[str, List[str]] = {
    "A": ["Mexico", "South Africa", "South Korea", "Czech Republic"],
    "B": ["Canada", "Qatar", "Bosnia and Herzegovina", "Switzerland"],
    "C": ["Brazil", "Haiti", "Morocco", "Scotland"],
    "D": ["United States", "Paraguay", "Turkey", "Australia"],
    "E": ["Germany", "Ecuador", "Ivory Coast", "Curacao"],
    "F": ["Netherlands", "Japan", "Sweden", "Tunisia"],
    "G": ["Belgium", "Egypt", "Iran", "New Zealand"],
    "H": ["Spain", "Uruguay", "Saudi Arabia", "Cape Verde"],
    "I": ["France", "Senegal", "Norway", "Iraq"],
    "J": ["Argentina", "Algeria", "Austria", "Jordan"],
    "K": ["Colombia", "Portugal", "DR Congo", "Uzbekistan"],
    "L": ["England", "Croatia", "Ghana", "Panama"],
}

WC2026_TEAMS: List[str] = [t for teams in WC2026_GROUPS.values() for t in teams]

# Selecciones que juegan en casa en 2026 (is_neutral=0 cuando son "local" en el fixture)
WC2026_HOSTS: set = {"Mexico", "United States", "Canada"}

ROUND_ORDER = [
    "Fase de Grupos",
    "Ronda de 32",
    "Octavos de final",
    "Cuartos de final",
    "Semifinal",
    "Final",
    "Campeón",
]

# ─── Bracket oficial 2026 (partidos 73–88 del fixture) ────────────────────────
# "1A"/"2A" = primero/segundo del grupo A; "3:ABCDF" = mejor tercero de A/B/C/D/F.
R32_SLOTS = [
    ("2A", "2B"), ("1E", "3:ABCDF"), ("1F", "2C"), ("1C", "2F"),
    ("1I", "3:CDFGH"), ("2E", "2I"), ("1A", "3:CEFHI"), ("1L", "3:EHIJK"),
    ("1D", "3:BEFIJ"), ("1G", "3:AEHIJ"), ("2K", "2L"), ("1H", "2J"),
    ("1B", "3:EFGIJ"), ("1J", "2H"), ("1K", "3:DEIJL"), ("2D", "2G"),
]
# Rondas siguientes: pares de índices sobre los ganadores de la ronda anterior.
R16_PAIRS = [(1, 4), (0, 2), (3, 5), (6, 7), (10, 11), (8, 9), (13, 15), (12, 14)]
QF_PAIRS = [(0, 1), (4, 5), (2, 3), (6, 7)]
SF_PAIRS = [(0, 1), (2, 3)]

THIRD_SLOTS = [
    {"r32_index": i, "allowed": list(away[2:])}
    for i, (_, away) in enumerate(R32_SLOTS)
    if away.startswith("3:")
]


def assign_thirds(qualified: Dict[str, str]) -> Dict[int, str]:
    """Asigna los 8 mejores terceros (grupo→equipo) a sus slots del bracket.

    Backtracking respetando las restricciones del fixture (slots más
    restringidos primero); fallback greedy si la combinación no casa.
    """
    order = sorted(
        THIRD_SLOTS,
        key=lambda s: sum(1 for g in s["allowed"] if g in qualified),
    )
    used: set = set()
    result: Dict[int, str] = {}

    def bt(k: int) -> bool:
        if k == len(order):
            return True
        slot = order[k]
        for g in slot["allowed"]:
            if g in qualified and g not in used:
                used.add(g)
                result[slot["r32_index"]] = qualified[g]
                if bt(k + 1):
                    return True
                used.discard(g)
                del result[slot["r32_index"]]
        return False

    if not bt(0):
        used.clear()
        result.clear()
        avail = list(qualified.keys())
        for slot in order:
            g = next(
                (x for x in slot["allowed"] if x in qualified and x not in used),
                None,
            ) or next(x for x in avail if x not in used)
            used.add(g)
            result[slot["r32_index"]] = qualified[g]
    return result

# ─── Tipo alias ───────────────────────────────────────────────────────────────

ProbsDict = Dict[str, float]   # {"team1_win": p, "draw": p, "team2_win": p}
PropsCache = Dict[tuple, ProbsDict]  # (t1, t2) → probs


# ─── 1. Pre-cómputo de estadísticas (ejecutar una vez al iniciar) ─────────────

def build_team_stats(
    df_features: pd.DataFrame,
    elo_ratings: Dict[str, float],
    teams: Optional[List[str]] = None,
    df_all: Optional[pd.DataFrame] = None,
) -> Dict[str, dict]:
    """Pre-computa stats de equipo para lookups O(1).

    df_all: todos los internacionales (no solo WC). Si se provee, la forma
    reciente se calcula desde el timeline completo — elimina los defaults
    silenciosos para debutantes y el skew train/serving para el resto.
    Si df_all es None, cae al comportamiento anterior (solo feature matrix WC).
    """
    from src.features import compute_current_form

    if teams is None:
        teams = list(set(df_features["home_team"]) | set(df_features["away_team"]))

    # Forma reciente: desde timeline completo si disponible, sino desde WC
    if df_all is not None:
        current_form = compute_current_form(df_all, teams=teams)
    else:
        current_form = None

    cache: Dict[str, dict] = {}
    for team in teams:
        wc_mask = (df_features["home_team"] == team) | (df_features["away_team"] == team)
        wc_matches = int(wc_mask.sum())

        if current_form is not None:
            form = current_form.get(team, {"goals_scored": 1.5, "goals_conceded": 1.2})
            scored = form["goals_scored"]
            conceded = form["goals_conceded"]
        else:
            rows = df_features[wc_mask].sort_values("date")
            if rows.empty:
                scored, conceded = 1.5, 1.2
            else:
                last = rows.iloc[-1]
                if last["home_team"] == team:
                    scored = float(last["home_goals_scored_avg5"])
                    conceded = float(last["home_goals_conceded_avg5"])
                else:
                    scored = float(last["away_goals_scored_avg5"])
                    conceded = float(last["away_goals_conceded_avg5"])

        cache[team] = {
            "elo": elo_ratings.get(team, DEFAULT_ELO),
            "goals_scored": scored,
            "goals_conceded": conceded,
            "wc_matches": wc_matches,
        }
    return cache


def build_h2h_stats(
    df_features: pd.DataFrame,
    teams: Optional[List[str]] = None,
) -> Dict[tuple, float]:
    """
    Pre-computa H2H win% para todos los pares de equipos.
    O(n²) una vez; luego O(1) por consulta.
    """
    if teams is None:
        teams = WC2026_TEAMS

    teams_set = set(teams)
    df_rel = df_features[
        df_features["home_team"].isin(teams_set) | df_features["away_team"].isin(teams_set)
    ]

    h2h: Dict[tuple, float] = {}
    for i, t1 in enumerate(teams):
        for t2 in teams[i + 1:]:
            mask = (
                ((df_rel["home_team"] == t1) & (df_rel["away_team"] == t2)) |
                ((df_rel["home_team"] == t2) & (df_rel["away_team"] == t1))
            )
            sub = df_rel[mask]
            if sub.empty:
                pct = 0.5
            else:
                wins = (
                    ((sub["home_team"] == t1) & (sub["outcome"] == "home_win")).sum() +
                    ((sub["home_team"] == t2) & (sub["outcome"] == "away_win")).sum()
                )
                pct = float(wins) / len(sub)
            h2h[(t1, t2)] = pct
            h2h[(t2, t1)] = 1.0 - pct
    return h2h


def precompute_match_probs(
    model,
    team_stats: Dict[str, dict],
    h2h_stats: Dict[tuple, float],
    teams: Optional[List[str]] = None,
    host_teams: Optional[set] = None,
) -> PropsCache:
    """Pre-computa probabilidades para todos los pares posibles en un batch.

    host_teams: selecciones que juegan en casa (is_neutral=0 cuando son "local").
    Para cada par (t1, t2) se generan dos filas: t1 como local y t2 como local,
    lo que produce probabilidades asimétricas cuando alguno es anfitrión.
    """
    if teams is None:
        teams = WC2026_TEAMS
    if host_teams is None:
        host_teams = WC2026_HOSTS

    _def = {"elo": DEFAULT_ELO, "goals_scored": 1.5, "goals_conceded": 1.2, "wc_matches": 0}

    pairs = [
        (teams[i], teams[j])
        for i in range(len(teams))
        for j in range(i + 1, len(teams))
    ]

    rows = []
    for t1, t2 in pairs:
        s1 = team_stats.get(t1, _def)
        s2 = team_stats.get(t2, _def)
        # is_neutral=0 si t1 es anfitrión y t2 no; neutral en cualquier otro caso
        is_neutral = 0 if (t1 in host_teams and t2 not in host_teams) else 1
        rows.append({
            "elo_diff": s1["elo"] - s2["elo"],
            "elo_home": s1["elo"],
            "elo_away": s2["elo"],
            "home_goals_scored_avg5": s1["goals_scored"],
            "home_goals_conceded_avg5": s1["goals_conceded"],
            "away_goals_scored_avg5": s2["goals_scored"],
            "away_goals_conceded_avg5": s2["goals_conceded"],
            "h2h_home_win_pct": h2h_stats.get((t1, t2), 0.5),
            "is_neutral": is_neutral,
            "wc_experience_diff": s1["wc_matches"] - s2["wc_matches"],
        })

    df_batch = pd.DataFrame(rows)[FEATURE_COLS]
    probas = model.predict_proba(df_batch)

    cache: PropsCache = {}
    for idx, (t1, t2) in enumerate(pairs):
        p0, p1, p2 = float(probas[idx][0]), float(probas[idx][1]), float(probas[idx][2])
        cache[(t1, t2)] = {"team1_win": p0, "draw": p1, "team2_win": p2}
        # Para (t2, t1): t2 es "local" — is_neutral=0 si t2 es anfitrión
        s1, s2 = team_stats.get(t2, _def), team_stats.get(t1, _def)
        is_neutral_rev = 0 if (t2 in host_teams and t1 not in host_teams) else 1
        if is_neutral_rev != is_neutral:
            row_rev = pd.DataFrame([{
                "elo_diff": s1["elo"] - s2["elo"],
                "elo_home": s1["elo"],
                "elo_away": s2["elo"],
                "home_goals_scored_avg5": s1["goals_scored"],
                "home_goals_conceded_avg5": s1["goals_conceded"],
                "away_goals_scored_avg5": s2["goals_scored"],
                "away_goals_conceded_avg5": s2["goals_conceded"],
                "h2h_home_win_pct": h2h_stats.get((t2, t1), 0.5),
                "is_neutral": is_neutral_rev,
                "wc_experience_diff": s1["wc_matches"] - s2["wc_matches"],
            }])[FEATURE_COLS]
            pr = model.predict_proba(row_rev)[0]
            cache[(t2, t1)] = {"team1_win": float(pr[0]), "draw": float(pr[1]), "team2_win": float(pr[2])}
        else:
            cache[(t2, t1)] = {"team1_win": p2, "draw": p1, "team2_win": p0}

    logger.info("precompute_match_probs: %d pares calculados en batch", len(pairs))
    return cache


# ─── 2. Predicción ad-hoc (para Tab 1 con equipos históricos) ─────────────────

def predict_match(
    model,
    team1: str,
    team2: str,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    probs_cache: Optional[PropsCache] = None,
) -> ProbsDict:
    """
    Predice un partido neutral.
    Si probs_cache está disponible y contiene el par, devuelve O(1).
    Fallback: computa desde el DataFrame (lento — solo para equipos sin caché).
    """
    if probs_cache is not None:
        cached = probs_cache.get((team1, team2))
        if cached is not None:
            return cached

    # ── fallback: calcular desde DataFrame ────────────────────────────────
    def _get_stats(team: str) -> tuple:
        mask = (df_features["home_team"] == team) | (df_features["away_team"] == team)
        rows = df_features[mask].sort_values("date")
        if rows.empty:
            return elo_ratings.get(team, DEFAULT_ELO), 1.5, 1.2, 0
        last = rows.iloc[-1]
        if last["home_team"] == team:
            return (elo_ratings.get(team, DEFAULT_ELO),
                    float(last["home_goals_scored_avg5"]),
                    float(last["home_goals_conceded_avg5"]),
                    len(rows))
        return (elo_ratings.get(team, DEFAULT_ELO),
                float(last["away_goals_scored_avg5"]),
                float(last["away_goals_conceded_avg5"]),
                len(rows))

    elo1, gs1, gc1, n1 = _get_stats(team1)
    elo2, gs2, gc2, n2 = _get_stats(team2)

    h2h_mask = (
        ((df_features["home_team"] == team1) & (df_features["away_team"] == team2)) |
        ((df_features["home_team"] == team2) & (df_features["away_team"] == team1))
    )
    h2h = df_features[h2h_mask]
    if h2h.empty:
        h2h_pct = 0.5
    else:
        wins = (
            ((h2h["home_team"] == team1) & (h2h["outcome"] == "home_win")).sum() +
            ((h2h["home_team"] == team2) & (h2h["outcome"] == "away_win")).sum()
        )
        h2h_pct = float(wins) / len(h2h)

    row = pd.DataFrame([{
        "elo_diff": elo1 - elo2, "elo_home": elo1, "elo_away": elo2,
        "home_goals_scored_avg5": gs1, "home_goals_conceded_avg5": gc1,
        "away_goals_scored_avg5": gs2, "away_goals_conceded_avg5": gc2,
        "h2h_home_win_pct": h2h_pct,
        "is_neutral": 0 if (team1 in WC2026_HOSTS and team2 not in WC2026_HOSTS) else 1,
        "wc_experience_diff": n1 - n2,
    }])[FEATURE_COLS]

    proba = model.predict_proba(row)[0]
    return {"team1_win": float(proba[0]), "draw": float(proba[1]), "team2_win": float(proba[2])}


# ─── 3. Penales — historial de tandas por equipo ──────────────────────────────

def build_shootout_stats(df_shootouts: pd.DataFrame) -> Dict[str, dict]:
    """Pre-computa {equipo: {wins, total}} desde shootouts.csv (nombres normalizados)."""
    stats: Dict[str, dict] = defaultdict(lambda: {"wins": 0, "total": 0})
    for row in df_shootouts.itertuples(index=False):
        for team in (row.home_team, row.away_team):
            stats[team]["total"] += 1
            if row.winner == team:
                stats[team]["wins"] += 1
    return dict(stats)


def shootout_win_prob(
    team1: str,
    team2: str,
    shootout_stats: Optional[Dict[str, dict]] = None,
) -> float:
    """P(team1 gana la tanda) según historial, con suavizado hacia 0.5.

    Cada equipo aporta su win rate suavizado (Laplace: +2 victorias / +4 tandas,
    prior 0.5); la probabilidad del cruce es Bradley-Terry entre ambos rates.
    Sin historial para ambos → 0.5 exacto.
    """
    if not shootout_stats:
        return 0.5
    s1 = shootout_stats.get(team1, {"wins": 0, "total": 0})
    s2 = shootout_stats.get(team2, {"wins": 0, "total": 0})
    r1 = (s1["wins"] + 2) / (s1["total"] + 4)
    r2 = (s2["wins"] + 2) / (s2["total"] + 4)
    return r1 / (r1 + r2)


# ─── 4. Muestreo de resultados ────────────────────────────────────────────────

def _sample_outcome(probs: ProbsDict) -> str:
    r = random.random()
    if r < probs["team1_win"]:
        return "team1_win"
    if r < probs["team1_win"] + probs["draw"]:
        return "draw"
    return "team2_win"


def _sample_knockout(
    probs: ProbsDict,
    team1: str,
    team2: str,
    shootout_stats: Optional[Dict[str, dict]] = None,
) -> str:
    """Knockout: empate → penales ponderados por historial de tandas."""
    outcome = _sample_outcome(probs)
    if outcome == "draw":
        p1 = shootout_win_prob(team1, team2, shootout_stats)
        outcome = "team1_win" if random.random() < p1 else "team2_win"
    return team1 if outcome == "team1_win" else team2


# ─── 5. Simulación de grupo ───────────────────────────────────────────────────

FixedResults = Dict[frozenset, Optional[str]]  # {frozenset({t1,t2}): winner | None=empate}


def simulate_group(
    teams: List[str],
    model,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    probs_cache: Optional[PropsCache] = None,
    fixed_results: Optional[FixedResults] = None,
) -> Tuple[Dict[str, int], List[str]]:
    """Simula los 6 partidos de un grupo. Retorna (puntos, clasificación).

    Partidos presentes en fixed_results (ya jugados en el torneo real) no se
    simulan: se fija su resultado real.
    """
    points: Dict[str, int] = defaultdict(int)

    for i, t1 in enumerate(teams):
        for t2 in teams[i + 1:]:
            pair = frozenset((t1, t2))
            if fixed_results is not None and pair in fixed_results:
                winner = fixed_results[pair]
                if winner is None:
                    points[t1] += 1
                    points[t2] += 1
                else:
                    points[winner] += 3
                continue
            probs = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
            outcome = _sample_outcome(probs)
            if outcome == "team1_win":
                points[t1] += 3
            elif outcome == "draw":
                points[t1] += 1
                points[t2] += 1
            else:
                points[t2] += 3

    standings = sorted(
        teams,
        key=lambda t: (points[t], elo_ratings.get(t, DEFAULT_ELO)),
        reverse=True,
    )
    return dict(points), standings


def get_group_match_probs(
    teams: List[str],
    model,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    probs_cache: Optional[PropsCache] = None,
) -> List[Dict]:
    """Retorna probabilidades para los 6 partidos de un grupo (determinista)."""
    matches = []
    for i, t1 in enumerate(teams):
        for t2 in teams[i + 1:]:
            probs = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
            matches.append({"team1": t1, "team2": t2, **probs})
    return matches


# ─── 6. Simulación completa del torneo ───────────────────────────────────────

def simulate_tournament(
    model,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    groups: Optional[Dict[str, List[str]]] = None,
    probs_cache: Optional[PropsCache] = None,
    shootout_stats: Optional[Dict[str, dict]] = None,
    fixed_results: Optional[FixedResults] = None,
) -> Dict[str, str]:
    """
    Simula un torneo completo.
    probs_cache hace el Monte Carlo ~100x más rápido (lookups O(1)).
    """
    if groups is None:
        groups = WC2026_GROUPS

    results: Dict[str, str] = {}
    for teams in groups.values():
        for t in teams:
            results[t] = ROUND_ORDER[0]

    # ── Fase de grupos ──────────────────────────────────────────────────────
    group_standings: Dict[str, List[str]] = {}
    group_points: Dict[str, Dict[str, int]] = {}

    for gname, teams in groups.items():
        pts, standing = simulate_group(
            teams, model, elo_ratings, df_features, probs_cache, fixed_results
        )
        group_standings[gname] = standing
        group_points[gname] = pts

    # ── Clasificados: top 2 (24) + 8 mejores terceros = 32 ──────────────────
    third_candidates: List[Tuple[str, str, int]] = []  # (grupo, equipo, pts)
    for gname, standing in group_standings.items():
        third = standing[2]
        third_candidates.append((gname, third, group_points[gname].get(third, 0)))
    third_candidates.sort(key=lambda x: x[2], reverse=True)

    official_bracket = set(groups.keys()) == set("ABCDEFGHIJKL")

    if official_bracket:
        # ── Ronda de 32 según el bracket oficial del fixture ────────────────
        qualified_thirds = {g: t for g, t, _ in third_candidates[:8]}
        third_by_r32 = assign_thirds(qualified_thirds)

        def _resolve(slot: str, r32_index: int) -> str:
            if slot.startswith("3:"):
                return third_by_r32[r32_index]
            gname = slot[1]
            return group_standings[gname][0 if slot[0] == "1" else 1]

        r32_matches = [
            (_resolve(home, i), _resolve(away, i))
            for i, (home, away) in enumerate(R32_SLOTS)
        ]
        for t1, t2 in r32_matches:
            results[t1] = ROUND_ORDER[1]
            results[t2] = ROUND_ORDER[1]

        winners = [
            _sample_knockout(
                predict_match(model, t1, t2, elo_ratings, df_features, probs_cache),
                t1, t2, shootout_stats,
            )
            for t1, t2 in r32_matches
        ]
        for t in winners:
            results[t] = ROUND_ORDER[2]  # "Octavos de final"

        # R16 → QF → SF → Final con los emparejamientos del fixture
        for pairs, round_name in [
            (R16_PAIRS, ROUND_ORDER[3]),
            (QF_PAIRS, ROUND_ORDER[4]),
            (SF_PAIRS, ROUND_ORDER[5]),
            ([(0, 1)], ROUND_ORDER[6]),
        ]:
            winners = [
                _sample_knockout(
                    predict_match(
                        model, winners[i], winners[j], elo_ratings, df_features, probs_cache
                    ),
                    winners[i], winners[j], shootout_stats,
                )
                for i, j in pairs
            ]
            for t in winners:
                results[t] = round_name
        return results

    # ── Fallback (grupos no oficiales, p.ej. tests): bracket aleatorio ──────
    top2: List[str] = []
    for standing in group_standings.values():
        top2.extend(standing[:2])
    best_thirds = [t for _, t, _ in third_candidates[:8]]

    round_of_32 = top2 + best_thirds
    for t in round_of_32:
        results[t] = ROUND_ORDER[1]  # "Ronda de 32"

    current = round_of_32.copy()
    random.shuffle(current)
    round_idx = 2  # ganadores de R32 → ROUND_ORDER[2] = "Octavos de final"

    while len(current) > 1:
        next_round_name = ROUND_ORDER[round_idx] if round_idx < len(ROUND_ORDER) else ROUND_ORDER[-1]
        winners = []

        for i in range(0, len(current), 2):
            t1, t2 = current[i], current[i + 1]
            probs = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
            winner = _sample_knockout(probs, t1, t2, shootout_stats)
            winners.append(winner)

        for t in winners:
            results[t] = next_round_name

        current = winners
        round_idx += 1

    return results


# ─── 7. Monte Carlo ──────────────────────────────────────────────────────────

def monte_carlo(
    model,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    n: int = 1000,
    groups: Optional[Dict[str, List[str]]] = None,
    probs_cache: Optional[PropsCache] = None,
    shootout_stats: Optional[Dict[str, dict]] = None,
    fixed_results: Optional[FixedResults] = None,
) -> pd.DataFrame:
    """
    Corre n simulaciones y retorna DataFrame con % de llegar a cada ronda.
    Con probs_cache el bucle es puro Python sin pandas ni sklearn — muy rápido.
    Con fixed_results, los partidos ya jugados del torneo real quedan fijos y
    las probabilidades resultantes son condicionales a esos resultados.
    """
    if groups is None:
        groups = WC2026_GROUPS

    all_teams = [t for ts in groups.values() for t in ts]
    counts: Dict[str, Dict[str, int]] = {t: defaultdict(int) for t in all_teams}

    for _ in range(n):
        sim = simulate_tournament(
            model, elo_ratings, df_features, groups, probs_cache,
            shootout_stats, fixed_results,
        )
        for team, round_reached in sim.items():
            if team not in counts:
                continue
            idx = ROUND_ORDER.index(round_reached) if round_reached in ROUND_ORDER else 0
            for r in ROUND_ORDER[: idx + 1]:
                counts[team][r] += 1

    rows = []
    for team in all_teams:
        grupo = next((g for g, ts in groups.items() if team in ts), "?")
        row: dict = {
            "equipo": team,
            "grupo": grupo,
            "elo": round(elo_ratings.get(team, DEFAULT_ELO), 0),
        }
        for r in ROUND_ORDER:
            row[r] = round(counts[team].get(r, 0) / n, 4)
        rows.append(row)

    return pd.DataFrame(rows).sort_values("Campeón", ascending=False).reset_index(drop=True)


# ─── 7. Bracket determinista ─────────────────────────────────────────────────

def simulate_deterministic_tournament(
    model,
    elo_ratings: Dict[str, float],
    df_features: pd.DataFrame,
    groups: Optional[Dict[str, List[str]]] = None,
    probs_cache: Optional[PropsCache] = None,
) -> tuple:
    """
    Simula tomando siempre el resultado más probable.
    Retorna (bracket_rounds, group_standings).
    """
    if groups is None:
        groups = WC2026_GROUPS

    group_standings: Dict[str, List[str]] = {}
    group_expected_pts: Dict[str, Dict[str, float]] = {}

    for gname, teams in groups.items():
        expected_pts: Dict[str, float] = {t: 0.0 for t in teams}
        for i, t1 in enumerate(teams):
            for t2 in teams[i + 1:]:
                p = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
                expected_pts[t1] += 3 * p["team1_win"] + p["draw"]
                expected_pts[t2] += 3 * p["team2_win"] + p["draw"]

        standings = sorted(
            teams,
            key=lambda t: (expected_pts[t], elo_ratings.get(t, DEFAULT_ELO)),
            reverse=True,
        )
        group_standings[gname] = standings
        group_expected_pts[gname] = expected_pts

    top2: List[str] = []
    third_candidates: List[Tuple[str, float]] = []
    for gname, standing in group_standings.items():
        top2.extend(standing[:2])
        third = standing[2]
        third_candidates.append((third, group_expected_pts[gname].get(third, 0.0)))

    third_candidates.sort(key=lambda x: x[1], reverse=True)
    best_thirds = [t for t, _ in third_candidates[:8]]
    current = top2 + best_thirds

    round_names = ["Ronda de 32", "Octavos de final", "Cuartos de final", "Semifinal", "Final"]
    bracket_rounds: Dict[str, List[Dict]] = {}

    for round_name in round_names:
        if len(current) <= 1:
            break
        matches: List[Dict] = []
        next_round: List[str] = []
        for i in range(0, len(current), 2):
            t1, t2 = current[i], current[i + 1]
            probs = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
            winner = t1 if probs["team1_win"] >= probs["team2_win"] else t2
            matches.append({"team1": t1, "team2": t2, "probs": probs, "winner": winner})
            next_round.append(winner)
        bracket_rounds[round_name] = matches
        current = next_round

    return bracket_rounds, group_standings


# ─── 8. Datos en vivo ────────────────────────────────────────────────────────

def fetch_live_fixture(cache_path: Path = FIXTURE_PATH) -> List[Dict]:
    """Refresca el fixture desde openfootball; fallback a cache local."""
    import requests
    url = "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
    try:
        r = requests.get(url, timeout=8)
        if r.status_code == 200:
            data = r.json()
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            return data.get("matches", [])
    except Exception as e:
        logger.warning("No se pudo refrescar fixture: %s", e)

    if cache_path.exists():
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f).get("matches", [])
    return []


def get_played_matches(matches: List[Dict]) -> List[Dict]:
    return [m for m in matches if m.get("score1") is not None and m.get("score2") is not None]


def build_fixed_results(matches: List[Dict]) -> FixedResults:
    """Convierte partidos de grupos ya jugados (fixture live) en FixedResults.

    Solo fase de grupos: el knockout real define los cruces, no los simula.
    """
    fixed: FixedResults = {}
    for m in get_played_matches(matches):
        if not str(m.get("group", "")).startswith("Group"):
            continue
        t1 = normalize_name(m["team1"])
        t2 = normalize_name(m["team2"])
        s1, s2 = int(m["score1"]), int(m["score2"])
        if s1 > s2:
            winner: Optional[str] = t1
        elif s2 > s1:
            winner = t2
        else:
            winner = None
        fixed[frozenset((t1, t2))] = winner
    return fixed


def get_group_live_standings(matches: List[Dict], group_name: str) -> Optional[pd.DataFrame]:
    group_matches = [m for m in matches if m.get("group") == group_name]
    played = get_played_matches(group_matches)
    if not played:
        return None

    all_teams: set = set()
    for m in group_matches:
        all_teams.add(normalize_name(m["team1"]))
        all_teams.add(normalize_name(m["team2"]))

    stats: Dict[str, Dict] = {
        t: {"pts": 0, "gf": 0, "gc": 0, "pj": 0, "v": 0, "e": 0, "d": 0}
        for t in all_teams
    }

    for m in played:
        t1 = normalize_name(m["team1"])
        t2 = normalize_name(m["team2"])
        s1, s2 = int(m["score1"]), int(m["score2"])
        stats[t1]["gf"] += s1; stats[t1]["gc"] += s2; stats[t1]["pj"] += 1
        stats[t2]["gf"] += s2; stats[t2]["gc"] += s1; stats[t2]["pj"] += 1
        if s1 > s2:
            stats[t1]["pts"] += 3; stats[t1]["v"] += 1; stats[t2]["d"] += 1
        elif s1 == s2:
            stats[t1]["pts"] += 1; stats[t2]["pts"] += 1
            stats[t1]["e"] += 1; stats[t2]["e"] += 1
        else:
            stats[t2]["pts"] += 3; stats[t2]["v"] += 1; stats[t1]["d"] += 1

    rows = [{
        "Equipo": t, "PJ": s["pj"], "V": s["v"], "E": s["e"], "D": s["d"],
        "GF": s["gf"], "GC": s["gc"], "DG": s["gf"] - s["gc"], "Pts": s["pts"],
    } for t, s in stats.items()]
    return pd.DataFrame(rows).sort_values(["Pts", "DG", "GF"], ascending=False).reset_index(drop=True)


def normalize_name(name: str) -> str:
    return NAME_MAP.get(name, name)
