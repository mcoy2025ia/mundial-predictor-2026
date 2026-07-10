"""Resolución del bracket de eliminatorias del Mundial 2026.

El fixture (`wc2026_fixture.json`) trae los cruces de eliminatorias con
placeholders en lugar de equipos reales:

  - `1A` / `2B`        → 1º/2º del grupo A / B
  - `3A/B/C/D/F`       → mejor tercero asignado entre los grupos A,B,C,D,F
  - `W73` / `L101`     → ganador / perdedor del partido número 73 / 101

Este módulo computa los standings finales de grupo desde los resultados
reales (`wc2026_live_results.csv`), determina los 8 mejores terceros, los
asigna a sus slots respetando las restricciones FIFA del fixture, y resuelve
cada cruce de eliminatorias **hasta donde los datos lo permitan** (R32 en
cuanto terminan los grupos; R16/QF/SF/Final a medida que se juegan).

Es la pieza que faltaba para que `predict_live.py` genere predicciones de
eliminatorias: antes saltaba todo partido con placeholder.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
FIXTURE_PATH = ROOT / "data" / "external" / "wc2026_fixture.json"
LIVE_RESULTS_PATH = ROOT / "data" / "external" / "wc2026_live_results.csv"
# Cruces oficiales del API (autoridad para la asignación de mejores terceros).
KNOCKOUT_FIXTURE_CACHE = ROOT / "data" / "external" / "wc2026_knockout_fixture.json"

# Nombres del fixture → nombres canónicos del dataset (igual que en simulator.py)
_NAME_MAP: dict[str, str] = {
    "Bosnia & Herzegovina": "Bosnia and Herzegovina",
    "USA": "United States",
    "Curaçao": "Curacao",
}


def _norm(name: str) -> str:
    return _NAME_MAP.get(name, name)


# Placeholders
_RE_POS = re.compile(r"^([12])([A-L])$")          # 1A, 2B
_RE_THIRD = re.compile(r"^3([A-L](?:/[A-L])*)$")   # 3A/B/C/D/F
_RE_WL = re.compile(r"^([WL])(\d+)$")              # W73, L101


def load_fixture_raw(path: Path = FIXTURE_PATH) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def group_membership(fixture: dict) -> dict[str, str]:
    """team (normalizado) → letra de grupo, derivado de los partidos de grupo."""
    mem: dict[str, str] = {}
    for m in fixture.get("matches", []):
        grp = m.get("group")
        if not grp:
            continue
        letter = grp.replace("Group ", "").strip()
        for key in ("team1", "team2"):
            t = m.get(key)
            if t:
                mem[_norm(t)] = letter
    return mem


def _empty_stat() -> dict:
    return {"pts": 0, "gd": 0, "gf": 0, "ga": 0, "pj": 0}


def final_standings(
    df_played: pd.DataFrame,
    membership: dict[str, str],
) -> dict[str, list[dict]]:
    """Computa la tabla final ordenada de cada grupo desde los resultados.

    Tiebreakers FIFA: puntos → diferencia de gol → goles a favor →
    head-to-head (puntos entre empatados) → nombre (determinista).
    Devuelve {grupo: [ {team, pts, gd, gf, ga, pj, pos}, ... ]} ordenado.
    """
    stats: dict[str, dict] = defaultdict(_empty_stat)
    # Guardar resultados para desempate head-to-head
    h2h_games: list[tuple[str, str, int, int]] = []

    for _, r in df_played.iterrows():
        h = _norm(str(r["home_team"]))
        a = _norm(str(r["away_team"]))
        if h not in membership or a not in membership or membership[h] != membership[a]:
            continue  # solo partidos de fase de grupos (mismo grupo)
        if pd.isna(r["home_score"]) or pd.isna(r["away_score"]):
            continue
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        stats[h]["gf"] += hs; stats[h]["ga"] += as_; stats[h]["gd"] += hs - as_; stats[h]["pj"] += 1
        stats[a]["gf"] += as_; stats[a]["ga"] += hs; stats[a]["gd"] += as_ - hs; stats[a]["pj"] += 1
        if hs > as_:
            stats[h]["pts"] += 3
        elif as_ > hs:
            stats[a]["pts"] += 3
        else:
            stats[h]["pts"] += 1; stats[a]["pts"] += 1
        h2h_games.append((h, a, hs, as_))

    groups: dict[str, list[str]] = defaultdict(list)
    for team, letter in membership.items():
        groups[letter].append(team)

    def _h2h_points(team: str, rivals: set[str]) -> tuple[int, int, int]:
        """(pts, gd, gf) de `team` solo contra `rivals` (mini-liga de empatados)."""
        p = g = f = 0
        for h, a, hs, as_ in h2h_games:
            if team == h and a in rivals:
                f += hs; g += hs - as_
                p += 3 if hs > as_ else (1 if hs == as_ else 0)
            elif team == a and h in rivals:
                f += as_; g += as_ - hs
                p += 3 if as_ > hs else (1 if hs == as_ else 0)
        return p, g, f

    result: dict[str, list[dict]] = {}
    for letter, teams in groups.items():
        # Orden primario por (pts, gd, gf)
        ordered = sorted(
            teams,
            key=lambda t: (-stats[t]["pts"], -stats[t]["gd"], -stats[t]["gf"], t),
        )
        # Resolver empates exactos en (pts, gd, gf) con head-to-head
        i = 0
        while i < len(ordered):
            j = i + 1
            while (
                j < len(ordered)
                and stats[ordered[j]]["pts"] == stats[ordered[i]]["pts"]
                and stats[ordered[j]]["gd"] == stats[ordered[i]]["gd"]
                and stats[ordered[j]]["gf"] == stats[ordered[i]]["gf"]
            ):
                j += 1
            if j - i > 1:  # bloque de empatados [i, j)
                tied = set(ordered[i:j])
                ordered[i:j] = sorted(
                    ordered[i:j],
                    key=lambda t: (*(-x for x in _h2h_points(t, tied - {t})), t),
                )
            i = j

        result[letter] = [
            {"team": t, "pos": pos + 1, **stats[t]}
            for pos, t in enumerate(ordered)
        ]
    return result


def _complete_groups(
    fixture: dict,
    df_played: pd.DataFrame,
    membership: dict[str, str],
) -> set[str]:
    """Devuelve el conjunto de grupos cuyos partidos de grupo están TODOS jugados.

    Un slot posicional (1A, 2B, 3X) solo es definitivo cuando su grupo terminó.
    """
    scheduled: dict[str, int] = defaultdict(int)
    for m in fixture.get("matches", []):
        grp = m.get("group")
        if grp:
            scheduled[grp.replace("Group ", "").strip()] += 1

    played: dict[str, int] = defaultdict(int)
    for _, r in df_played.iterrows():
        h, a = _norm(str(r["home_team"])), _norm(str(r["away_team"]))
        if h not in membership or a not in membership or membership[h] != membership[a]:
            continue
        if pd.isna(r["home_score"]) or pd.isna(r["away_score"]):
            continue
        played[membership[h]] += 1

    return {g for g, n in scheduled.items() if n > 0 and played.get(g, 0) >= n}


def best_thirds(standings: dict[str, list[dict]]) -> dict[str, str]:
    """Devuelve {grupo: equipo} de los 8 mejores terceros (orden FIFA)."""
    thirds = []
    for letter, table in standings.items():
        if len(table) >= 3:
            t = table[2]
            thirds.append((letter, t["team"], t))
    thirds.sort(key=lambda x: (-x[2]["pts"], -x[2]["gd"], -x[2]["gf"], x[1]))
    return {letter: team for letter, team, _ in thirds[:8]}


def _assign_third_slots(
    slots: list[tuple[int, list[str]]],
    qualified: dict[str, str],
) -> dict[int, str]:
    """Asigna terceros clasificados a slots respetando los grupos permitidos.

    slots: lista de (match_num, [grupos_permitidos]).
    qualified: {grupo: equipo} de los 8 terceros clasificados.
    Backtracking empezando por los slots más restringidos; fallback greedy.
    """
    order = sorted(slots, key=lambda s: sum(1 for g in s[1] if g in qualified))
    used: set[str] = set()
    result: dict[int, str] = {}

    def bt(k: int) -> bool:
        if k == len(order):
            return True
        num, allowed = order[k]
        for g in allowed:
            if g in qualified and g not in used:
                used.add(g)
                result[num] = qualified[g]
                if bt(k + 1):
                    return True
                used.discard(g)
                del result[num]
        return False

    if not bt(0):
        used.clear(); result.clear()
        avail = list(qualified.keys())
        for num, allowed in order:
            g = next((x for x in allowed if x in qualified and x not in used), None) \
                or next(x for x in avail if x not in used)
            used.add(g)
            result[num] = qualified[g]
    return result


def _played_winner_loser(
    df_played: pd.DataFrame,
    home: str,
    away: str,
) -> tuple[Optional[str], Optional[str]]:
    """Si el cruce (home, away) ya se jugó, devuelve (ganador, perdedor).

    Empata por nombres normalizados en cualquier orden. Si terminó en empate
    (los penales no están en el CSV), devuelve (None, None).
    """
    h, a = _norm(home), _norm(away)
    for _, r in df_played.iterrows():
        rh, ra = _norm(str(r["home_team"])), _norm(str(r["away_team"]))
        if {rh, ra} != {h, a}:
            continue
        if pd.isna(r["home_score"]) or pd.isna(r["away_score"]):
            return None, None
        hs, as_ = int(r["home_score"]), int(r["away_score"])
        if hs > as_:
            return rh, ra
        if as_ > hs:
            return ra, rh
        return None, None  # empate: penales no disponibles en el CSV
    return None, None


def _load_api_r32_opponents() -> dict[str, str]:
    """team_norm → rival_norm para LAST_32, desde el cache del API.

    Es la asignación OFICIAL de los mejores terceros: FIFA usa una tabla fija
    según qué combinación de grupos clasifica, que nuestro backtracking no
    replica. Vacío si no hay cache (→ se cae al backtracking).
    """
    if not KNOCKOUT_FIXTURE_CACHE.exists():
        return {}
    try:
        data = json.loads(KNOCKOUT_FIXTURE_CACHE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    opp: dict[str, str] = {}
    for m in data.get("matches", []):
        if m.get("stage") != "LAST_32":
            continue
        h, a = _norm(m.get("home", "")), _norm(m.get("away", ""))
        if h and a:
            opp[h] = a
            opp[a] = h
    return opp


def _assign_thirds_with_api(
    ko_matches: list[dict],
    third_slots: list[tuple[int, list[str]]],
    thirds_qualified: dict[str, str],
    standings: dict[str, list[dict]],
    complete: set[str],
) -> dict[int, str]:
    """Asigna terceros a slots de R32: API como autoridad, backtracking de respaldo.

    Para cada slot `1X/2X vs 3X`: el lado posicional (1X/2X) se resuelve por
    standings, se busca su rival REAL en el cache del API → ese es el tercero
    correcto para ese slot. Los slots no cubiertos por el API se resuelven por
    backtracking con los terceros restantes (evita duplicar equipos).
    """
    if not thirds_qualified:
        return {}

    api_opp = _load_api_r32_opponents()
    overrides: dict[int, str] = {}
    for m in ko_matches:
        if m.get("round") != "Round of 32" or not api_opp:
            continue
        num = m.get("num")
        t1, t2 = m.get("team1", ""), m.get("team2", "")
        if _RE_THIRD.match(t1):
            pos_token = t2
        elif _RE_THIRD.match(t2):
            pos_token = t1
        else:
            continue
        mp = _RE_POS.match(pos_token)
        if not mp:
            continue
        pos, letter = int(mp.group(1)), mp.group(2)
        if letter not in complete:
            continue
        table = standings.get(letter, [])
        if len(table) < pos:
            continue
        pos_team = table[pos - 1]["team"]
        opp = api_opp.get(pos_team)
        if opp:
            overrides[num] = opp

    used = set(overrides.values())
    remaining_slots = [(n, al) for (n, al) in third_slots if n not in overrides]
    remaining_quals = {g: t for g, t in thirds_qualified.items() if t not in used}
    third_by_num = _assign_third_slots(remaining_slots, remaining_quals)
    third_by_num.update(overrides)
    return third_by_num


def resolve_bracket(
    fixture: Optional[dict] = None,
    df_played: Optional[pd.DataFrame] = None,
) -> dict[int, dict]:
    """Resuelve los cruces de eliminatorias hasta donde permiten los datos.

    Returns:
        {match_num: {"home": str|None, "away": str|None,
                     "round": str, "date": str, "time": str,
                     "ground": str, "resolved": bool}}
        home/away son None si el cruce todavía no es determinable.
    """
    if fixture is None:
        fixture = load_fixture_raw()
    if df_played is None:
        if LIVE_RESULTS_PATH.exists():
            df_played = pd.read_csv(LIVE_RESULTS_PATH)
        else:
            df_played = pd.DataFrame(
                columns=["home_team", "away_team", "home_score", "away_score"]
            )

    mem = group_membership(fixture)
    standings = final_standings(df_played, mem)
    complete = _complete_groups(fixture, df_played, mem)
    all_groups_done = complete == set(mem.values())
    # Los terceros solo se determinan cuando TODOS los grupos terminaron
    # (el ranking de mejores terceros es cruzado entre grupos).
    thirds_qualified = best_thirds(standings) if all_groups_done else {}

    ko_matches = [m for m in fixture.get("matches", []) if not m.get("group")]

    # 1) Recolectar todos los third-slots para asignarlos en conjunto
    third_slots: list[tuple[int, list[str]]] = []
    for m in ko_matches:
        num = m.get("num")
        for key in ("team1", "team2"):
            mt = _RE_THIRD.match(m.get(key, ""))
            if mt and num is not None:
                third_slots.append((num, mt.group(1).split("/")))
    third_by_num = _assign_thirds_with_api(
        ko_matches, third_slots, thirds_qualified, standings, complete,
    )

    def _resolve_token(token: str, num: int, slot_key: str) -> Optional[str]:
        """Resuelve un placeholder a un equipo real, o None si no se puede."""
        mp = _RE_POS.match(token)
        if mp:
            pos, letter = int(mp.group(1)), mp.group(2)
            if letter not in complete:
                return None  # grupo aún sin terminar → posición no definitiva
            table = standings.get(letter, [])
            return table[pos - 1]["team"] if len(table) >= pos else None
        if _RE_THIRD.match(token):
            return third_by_num.get(num)
        mwl = _RE_WL.match(token)
        if mwl:
            kind, ref = mwl.group(1), int(mwl.group(2))
            ref_match = resolved.get(ref)
            if not ref_match or not ref_match["home"] or not ref_match["away"]:
                return None
            winner, loser = _played_winner_loser(
                df_played, ref_match["home"], ref_match["away"]
            )
            return winner if kind == "W" else loser
        # Token desconocido o ya es nombre real
        return _norm(token) if token else None

    # 2) Resolver en orden de número de partido (16avos → Final),
    #    para que W/L puedan apoyarse en cruces ya resueltos.
    resolved: dict[int, dict] = {}
    for m in sorted(ko_matches, key=lambda x: x.get("num", 0)):
        num = m.get("num")
        if num is None:
            continue
        home = _resolve_token(m.get("team1", ""), num, "team1")
        away = _resolve_token(m.get("team2", ""), num, "team2")
        resolved[num] = {
            "home": home,
            "away": away,
            "round": m.get("round", ""),
            "date": m.get("date", ""),
            "time": m.get("time", ""),
            "ground": m.get("ground", ""),
            "resolved": bool(home and away),
        }
    return resolved
