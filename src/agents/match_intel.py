"""Match Intelligence — derived free features to feed the specialist agents.

The agents were starved: most returned delta=0 because MatchContext only carried
ELO + group points. This module computes RICH, ZERO-COST signals from data we
already have on disk:

  - results.csv          (49k+ internationals: form, H2H, goal trends)
  - wc2026_live_results  (current tournament results with scores)
  - goalscorers.csv      (who scored, when, penalties → goal-source concentration)
  - fixture + ELO        (opponent quality of recent results)

Everything here is deterministic and free. It produces compact human-readable
strings that drop straight into each agent's payload, so the LLM reasons over
REAL evidence instead of guessing from team names.

Usage:
    intel = MatchIntel(df_hist, df_wc26, fixture, elo_ratings)
    enr = intel.enrich(home="France", away="Norway", as_of=match_date, group="I",
                       standings=group_standings)
    # enr is a dict of ready-to-inject strings (None when no evidence)
"""
from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent


def _result_letter(team_score: int, opp_score: int) -> str:
    if team_score > opp_score:
        return "W"
    if team_score < opp_score:
        return "L"
    return "D"


class MatchIntel:
    """Computes free contextual signals for the agent system.

    Construct once per run; pass already-loaded dataframes so we don't re-read
    the 49k-row CSV for every match.
    """

    def __init__(
        self,
        df_hist: pd.DataFrame,
        df_wc26: pd.DataFrame,
        fixture: Optional[list[dict]] = None,
        elo_ratings: Optional[dict] = None,
    ) -> None:
        self.df_hist = df_hist
        self.df_wc26 = df_wc26
        self.fixture = fixture or []
        self.elo = elo_ratings or {}
        self._goalscorers = self._load_goalscorers()
        # Mapa equipo->ELO band para clasificar calidad del rival
        self._form_cache: dict[tuple, list[dict]] = {}

    # ── Carga perezosa de goleadores WC 2026 ─────────────────────────────────
    def _load_goalscorers(self) -> pd.DataFrame:
        path = ROOT / "data" / "raw" / "goalscorers.csv"
        if not path.exists():
            return pd.DataFrame()
        try:
            gs = pd.read_csv(path)
            gs["date"] = pd.to_datetime(gs["date"], errors="coerce")
            # Solo WC 2026
            return gs[gs["date"].dt.year == 2026].copy()
        except Exception as e:  # pragma: no cover
            logger.warning("No se pudo cargar goalscorers.csv: %s", e)
            return pd.DataFrame()

    # ── Calidad de un rival vía ELO ──────────────────────────────────────────
    def _quality_label(self, team: str) -> str:
        elo = self.elo.get(team)
        if elo is None:
            return ""
        if elo >= 1900:
            return "elite"
        if elo >= 1750:
            return "strong"
        if elo >= 1600:
            return "mid"
        return "weak"

    # ── Forma reciente (últimos N, todos los internacionales) ────────────────
    def _recent_matches(self, team: str, as_of: datetime, n: int = 5) -> list[dict]:
        key = (team, as_of, n)
        if key in self._form_cache:
            return self._form_cache[key]
        df = self.df_hist
        mask = (
            ((df["home_team"] == team) | (df["away_team"] == team))
            & df["home_score"].notna()
            & (df["date"] < pd.Timestamp(as_of))
        )
        sub = df[mask].sort_values("date").tail(n)
        out: list[dict] = []
        for _, r in sub.iterrows():
            if r["home_team"] == team:
                ts, os_, opp = int(r["home_score"]), int(r["away_score"]), r["away_team"]
            else:
                ts, os_, opp = int(r["away_score"]), int(r["home_score"]), r["home_team"]
            out.append({
                "opponent": opp,
                "gf": ts,
                "ga": os_,
                "result": _result_letter(ts, os_),
                "opp_quality": self._quality_label(opp),
                "tournament": r.get("tournament", ""),
            })
        self._form_cache[key] = out
        return out

    def form_summary(self, team: str, as_of: datetime, n: int = 5) -> Optional[str]:
        rows = self._recent_matches(team, as_of, n)
        if not rows:
            return None
        parts = []
        for m in rows:
            q = f"[{m['opp_quality']}]" if m["opp_quality"] else ""
            parts.append(f"{m['result']} {m['gf']}-{m['ga']} vs {m['opponent']}{q}")
        wins = sum(1 for m in rows if m["result"] == "W")
        draws = sum(1 for m in rows if m["result"] == "D")
        losses = sum(1 for m in rows if m["result"] == "L")
        return f"({wins}W-{draws}D-{losses}L) " + " | ".join(parts)

    def goal_trend(self, team: str, as_of: datetime, n: int = 5) -> Optional[str]:
        rows = self._recent_matches(team, as_of, n)
        if not rows:
            return None
        gf = sum(m["gf"] for m in rows) / len(rows)
        ga = sum(m["ga"] for m in rows) / len(rows)
        clean = sum(1 for m in rows if m["ga"] == 0)
        blank = sum(1 for m in rows if m["gf"] == 0)
        return (
            f"scored {gf:.1f}/g, conceded {ga:.1f}/g, "
            f"{clean} clean sheet(s), {blank} blank(s) in last {len(rows)}"
        )

    def momentum(self, team: str, as_of: datetime) -> Optional[str]:
        rows = self._recent_matches(team, as_of, 5)
        if len(rows) < 3:
            return None
        pts = [3 if m["result"] == "W" else 1 if m["result"] == "D" else 0 for m in rows]
        first_half = sum(pts[: len(pts) // 2])
        second_half = sum(pts[len(pts) // 2:])
        recent3 = pts[-3:]
        if sum(recent3) >= 7:
            return "hot (strong recent run)"
        if sum(recent3) <= 1:
            return "cold (poor recent run)"
        if second_half > first_half:
            return "rising"
        if second_half < first_half:
            return "falling"
        return "stable"

    # ── Head-to-head ─────────────────────────────────────────────────────────
    def h2h_summary(self, home: str, away: str, as_of: datetime, n: int = 5) -> Optional[str]:
        df = self.df_hist
        mask = (
            (((df["home_team"] == home) & (df["away_team"] == away))
             | ((df["home_team"] == away) & (df["away_team"] == home)))
            & df["home_score"].notna()
            & (df["date"] < pd.Timestamp(as_of))
        )
        sub = df[mask].sort_values("date")
        if sub.empty:
            return None
        home_w = draws = away_w = 0
        recent = []
        for _, r in sub.tail(n).iterrows():
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            # Orientar al equipo "home" del partido actual
            if r["home_team"] == home:
                gf, ga = hs, as_
            else:
                gf, ga = as_, hs
            recent.append(f"{gf}-{ga}")
        for _, r in sub.iterrows():
            hs, as_ = int(r["home_score"]), int(r["away_score"])
            if r["home_team"] == home:
                gf, ga = hs, as_
            else:
                gf, ga = as_, hs
            if gf > ga:
                home_w += 1
            elif gf < ga:
                away_w += 1
            else:
                draws += 1
        total = home_w + draws + away_w
        return (
            f"{total} previous meeting(s): {home} {home_w}W-{draws}D-{away_w}L. "
            f"Recent (from {home} view): {', '.join(recent)}"
        )

    # ── Resultados en el torneo actual con detalle ───────────────────────────
    def wc_results(self, team: str) -> Optional[str]:
        df = self.df_wc26
        mask = ((df["home_team"] == team) | (df["away_team"] == team)) & df["home_score"].notna()
        sub = df[mask].sort_values("date")
        if sub.empty:
            return None
        parts = []
        for _, r in sub.iterrows():
            if r["home_team"] == team:
                gf, ga, opp = int(r["home_score"]), int(r["away_score"]), r["away_team"]
            else:
                gf, ga, opp = int(r["away_score"]), int(r["home_score"]), r["home_team"]
            q = self._quality_label(opp)
            qs = f"[{q}]" if q else ""
            parts.append(f"{_result_letter(gf, ga)} {gf}-{ga} vs {opp}{qs}")
        return " | ".join(parts)

    # ── Fuente de goles (concentración / dependencia) ────────────────────────
    def scorer_profile(self, team: str) -> Optional[str]:
        gs = self._goalscorers
        if gs.empty:
            return None
        team_goals = gs[gs["team"] == team]
        if team_goals.empty:
            return None
        total = len(team_goals)
        by_player = team_goals.groupby("scorer").size().sort_values(ascending=False)
        pens = int(team_goals["penalty"].astype(str).str.upper().isin(["TRUE", "1"]).sum())
        top_player = by_player.index[0]
        top_goals = int(by_player.iloc[0])
        dependency = top_goals / total if total else 0
        scorers_str = ", ".join(f"{p} {int(g)}" for p, g in by_player.head(3).items())
        dep_flag = ""
        if dependency >= 0.6 and total >= 2:
            dep_flag = f" — HIGH dependency ({dependency*100:.0f}% from {top_player})"
        elif by_player.size >= 3:
            dep_flag = " — spread scoring (squad depth)"
        return f"{total} WC goals ({pens} pen): {scorers_str}{dep_flag}"

    # ── Matemática exacta de mejor tercero ───────────────────────────────────
    def third_place_math(
        self, team: str, group: str, standings: dict[str, dict]
    ) -> Optional[str]:
        """Compara el 3º del grupo del equipo con los 3os de los otros grupos.

        Calcula qué le falta a `team` para asegurar/disputar un puesto de mejor
        tercero (puntos + diferencia de goles), evidencia real cross-group.
        """
        if not standings or group not in standings:
            return None

        glabel = group.replace("Group ", "").strip()  # "Group I" → "I"

        # Tabla del grupo del equipo
        grp_data = standings[group]
        if team not in grp_data:
            return None
        ranked = sorted(
            grp_data.items(), key=lambda x: (-x[1]["pts"], -x[1]["gd"], -x[1]["gf"])
        )
        pos = next((i + 1 for i, (t, _) in enumerate(ranked) if t == team), None)
        if pos is None:
            return None

        # Recolectar todos los 3os de cada grupo
        thirds = []
        for g, data in standings.items():
            r = sorted(data.items(), key=lambda x: (-x[1]["pts"], -x[1]["gd"], -x[1]["gf"]))
            if len(r) >= 3:
                t3, d3 = r[2]
                thirds.append((g, t3, d3["pts"], d3["gd"], d3["gf"]))

        if not thirds:
            return None
        # 8 mejores terceros avanzan (formato 48 equipos → top 8 de 12 terceros)
        thirds_sorted = sorted(thirds, key=lambda x: (-x[2], -x[3], -x[4]))
        cutoff_idx = min(8, len(thirds_sorted)) - 1
        cutoff_team = thirds_sorted[cutoff_idx]

        my_third = next((x for x in thirds if x[1] == team), None)
        pos_label = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}.get(pos, f"{pos}th")

        if pos <= 2:
            return (
                f"{team} currently {pos_label} in Group {glabel} (direct qualification path). "
                f"Best-third cutoff is ~{cutoff_team[2]}pts/GD{cutoff_team[3]:+d}."
            )
        if pos == 3 and my_third:
            in_top8 = thirds_sorted.index(my_third) < 8
            status = "INSIDE top-8 thirds (would qualify)" if in_top8 else "OUTSIDE top-8 (eliminated as-is)"
            return (
                f"{team} 3rd in Group {glabel} with {my_third[2]}pts/GD{my_third[3]:+d}, "
                f"{status}. Cutoff: {cutoff_team[2]}pts/GD{cutoff_team[3]:+d}. "
                f"A win likely secures advancement; goal difference is the tiebreaker."
            )
        return (
            f"{team} {pos_label} in Group {glabel} — must win and improve goal difference "
            f"to reach best-third contention (cutoff ~{cutoff_team[2]}pts/GD{cutoff_team[3]:+d})."
        )

    # ── Punto de entrada: enriquecer un partido ──────────────────────────────
    def enrich(
        self,
        home: str,
        away: str,
        as_of: datetime,
        group: Optional[str] = None,
        standings: Optional[dict] = None,
    ) -> dict:
        """Devuelve dict de strings listos para inyectar en MatchContext."""
        return {
            "home_form": self.form_summary(home, as_of),
            "away_form": self.form_summary(away, as_of),
            "home_goal_trend": self.goal_trend(home, as_of),
            "away_goal_trend": self.goal_trend(away, as_of),
            "home_momentum": self.momentum(home, as_of),
            "away_momentum": self.momentum(away, as_of),
            "h2h_summary": self.h2h_summary(home, away, as_of),
            "home_wc_results": self.wc_results(home),
            "away_wc_results": self.wc_results(away),
            "home_scorers": self.scorer_profile(home),
            "away_scorers": self.scorer_profile(away),
            "third_place_math": (
                self.third_place_math(home, group, standings)
                if group and standings else None
            ),
        }
