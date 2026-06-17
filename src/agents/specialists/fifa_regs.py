"""FIFA-Regs-Strategist: bracket math, qualification pressure, altitude, best-thirds.

Agente determinístico — no usa LLM. Cuantifica:
  1. Presión de clasificación: ¿cuántos puntos necesita cada equipo?
  2. Altitud: penalización aeróbica a nivel del mar vs sede alta.
  3. Rotaciones tácticas: equipo ya clasificado puede descansar titulares.
  4. Partido "ganable" del grupo: si un equipo viene de jugar a un rival difícil
     y este es su partido "fácil" o viceversa.
"""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext


_MAX_GROUP_DELTA = 0.06   # máxima corrección por presión de grupo


def _altitude_penalty(altitude_m: int) -> float:
    """Penalización aeróbica por altitud para equipos de nivel del mar (~1% VO2max/300m)."""
    if altitude_m < 1500:
        return 0.0
    return min((altitude_m - 1500) / 300 * 0.01, 0.06)


def _qualification_pressure(points: int, games_played: int, matchday: int) -> str:
    """Clasifica la situación de un equipo según puntos y partidos jugados.

    Returns: "must_win" | "needs_result" | "comfortable" | "already_through" | "unknown"
    """
    if games_played >= 3:
        return "unknown"  # ya terminó su fase de grupos

    games_remaining = 3 - games_played  # incluyendo este partido

    if matchday == 3 or games_remaining == 1:
        # Último partido: análisis más preciso
        if points == 0:
            return "must_win"        # 0 puntos, último partido → gana o elimnado (casi seguro)
        elif points == 1:
            return "must_win"        # 1 punto, necesita probablemente ganar
        elif points == 2:
            return "needs_result"    # 2 puntos (2 empates) → empate puede clasificar
        elif points == 3:
            return "needs_result"    # 3 puntos → depende del otro partido
        elif points >= 4:
            return "comfortable"     # 4+ puntos → muy probablemente clasificado
        elif points >= 6:
            return "already_through" # 6 puntos → clasificado matemáticamente
    elif matchday == 2 or games_remaining == 2:
        if points == 0:
            return "must_win"
        elif points == 3:
            return "comfortable"
        elif points >= 6:
            return "already_through"
    # Matchday 1: nadie está presionado todavía
    return "comfortable" if points > 0 else "neutral"

    return "unknown"


def _pressure_to_delta(situation: str, is_home: bool) -> float:
    """Convierte situación de presión a delta_P.

    Equipo desesperado → ataca más → sube su P(win) pero también P(loss) por exposición.
    Equipo relajado → puede rotar → baja ligeramente su P(win).
    """
    sign = 1.0 if is_home else -1.0  # positivo → beneficia al home
    if situation == "must_win":
        return sign * 0.03    # ataca más, pero también más vulnerable
    elif situation == "needs_result":
        return sign * 0.015
    elif situation == "already_through":
        return sign * (-0.025)  # rotaciones, mentalidad relajada
    elif situation == "comfortable":
        return sign * (-0.01)
    return 0.0


class FIFARegsAgent(BaseAgent):
    """Corrige el prior según presión de clasificación, altitud y contexto de grupo."""

    name = "FIFA-Regs-Strategist"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        notes: list[str] = []
        delta_home = 0.0
        delta_away = 0.0

        matchday = ctx.matchday or 1

        # ── 1. Presión de clasificación ──────────────────────────────────────
        if ctx.group_points_home is not None:
            sit_home = _qualification_pressure(
                ctx.group_points_home, ctx.games_played_home, matchday
            )
            d = _pressure_to_delta(sit_home, is_home=True)
            delta_home += d
            if d != 0.0:
                notes.append(f"home_pressure={sit_home}({ctx.group_points_home}pts) d={d:+.3f}")

        if ctx.group_points_away is not None:
            sit_away = _qualification_pressure(
                ctx.group_points_away, ctx.games_played_away, matchday
            )
            d = _pressure_to_delta(sit_away, is_home=False)
            delta_away += d
            if d != 0.0:
                notes.append(f"away_pressure={sit_away}({ctx.group_points_away}pts) d={d:+.3f}")

        # ── 2. Altitud ────────────────────────────────────────────────────────
        if ctx.venue_altitude_m > 1500:
            pen = _altitude_penalty(ctx.venue_altitude_m)
            if pen > 0:
                if not ctx.is_neutral:
                    # Local adaptado, visitante sufre más
                    delta_home += pen * 0.25
                    delta_away -= pen
                    notes.append(f"altitude={ctx.venue_altitude_m}m pen={pen:.3f} (local_adv)")
                else:
                    # Sede neutral: ambos sufren, ventaja para el equipo de mayor altitud habitual
                    # (heurística: si venue es México, MEX tiene ventaja por aclimatación)
                    venue = ctx.venue_city or ""
                    if ctx.team_home in ("Mexico",) and venue in ("Mexico City", "Guadalajara", "Monterrey"):
                        delta_home += pen * 0.5
                        delta_away -= pen * 0.5
                        notes.append(f"altitude={ctx.venue_altitude_m}m home_acclimatized")
                    else:
                        notes.append(f"altitude={ctx.venue_altitude_m}m both_affected")

        # ── 3. Rotaciones por matchday ────────────────────────────────────────
        # Matchday 3 con equipo ya clasificado → rotación alta
        if matchday == 3:
            if ctx.group_points_home is not None and ctx.group_points_home >= 6:
                delta_home -= 0.025
                notes.append("home_MD3_rotation_risk(6pts)")
            if ctx.group_points_away is not None and ctx.group_points_away >= 6:
                delta_away -= 0.025
                notes.append("away_MD3_rotation_risk(6pts)")

        # ── 4. Clamp ──────────────────────────────────────────────────────────
        delta_home = max(-_MAX_GROUP_DELTA, min(_MAX_GROUP_DELTA, delta_home))
        delta_away = max(-_MAX_GROUP_DELTA, min(_MAX_GROUP_DELTA, delta_away))
        delta_draw = -(delta_home + delta_away)

        confidence = min(0.7, 0.2 + len(notes) * 0.15) if notes else 0.1

        return AgentResult(
            agent_name=self.name,
            delta_home=round(delta_home, 4),
            delta_draw=round(delta_draw, 4),
            delta_away=round(delta_away, 4),
            confidence=confidence,
            notes="; ".join(notes) if notes else "no structural adjustments",
        )
