"""FIFA-Regs-Strategist: bracket math, best-thirds, tiebreakers.

Agente determinístico — no usa LLM. Cuantifica si un equipo tiene incentivo
estratégico para terminar 2nd en lugar de 1st (bracket más fácil).
También ajusta probs cuando un equipo está en una posición de 'relajación táctica'
(ya clasificado con margen) vs. 'desesperación' (necesita ganar o empatar).
"""
from __future__ import annotations

import math
from typing import Optional

from src.agents.base import AgentResult, BaseAgent, MatchContext

# Máxima corrección por contexto de grupo (el bracket rara vez cambia >3%)
_MAX_GROUP_DELTA = 0.04

# Grupos del WC 2026 que se juegan a altitudes significativas
_HIGH_ALTITUDE_CITIES = {"Mexico City", "Guadalajara", "Monterrey"}


def _altitude_penalty(altitude_m: int, minutes_played: int = 75) -> float:
    """Penalización aeróbica por altitud para equipos de nivel del mar.

    Basado en estudios de fisiología deportiva: ~1% de caída de VO2max por 300m.
    """
    if altitude_m < 1500:
        return 0.0
    penalty = (altitude_m - 1500) / 300 * 0.01
    # Se amplifica en minutos finales (fatiga compuesta)
    late_game_mult = 1.0 + (minutes_played - 60) / 90 if minutes_played > 60 else 1.0
    return min(penalty * late_game_mult, 0.06)


class FIFARegsAgent(BaseAgent):
    """Corrige el prior según contexto de bracket/grupo y altitud de la sede."""

    name = "FIFA-Regs-Strategist"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        notes = []
        delta_home = 0.0
        delta_away = 0.0

        # Penalización por altitud (afecta al equipo de menor altitud habitual)
        if ctx.venue_altitude_m > 1500:
            pen = _altitude_penalty(ctx.venue_altitude_m)
            if pen > 0:
                # Si el partido es en sede neutral, ambos sufren por igual → sin delta
                # Si hay local (host nation), el local está adaptado → penaliza al visitante
                if not ctx.is_neutral:
                    delta_away -= pen
                    delta_home += pen * 0.3  # local tiene ventaja parcial
                    notes.append(f"altitude_pen={pen:.3f} @ {ctx.venue_altitude_m}m")

        # Bracket path: si round_label contiene hints de "must win" vs "relajado"
        if ctx.round_label:
            rl = ctx.round_label.lower()
            if "must win" in rl or "eliminado" in rl:
                # El equipo desesperado juega más abierto → más goles, mais riscos
                # Ligera corrección: más probable victoria decisiva o derrota
                delta_home += 0.01
                delta_away += 0.01
                delta_home -= 0.02  # el prior ya refleja esto parcialmente
                notes.append("must-win context: increased variance")
            elif "clasificado" in rl or "already through" in rl:
                # Rotaciones/descanso → underperformance leve
                delta_home -= 0.02
                delta_draw += 0.015
                notes.append("rotation risk: team already qualified")

        confidence = 0.4 if notes else 0.1
        delta_draw = -(delta_home + delta_away)

        return AgentResult(
            agent_name=self.name,
            delta_home=round(delta_home, 4),
            delta_draw=round(delta_draw, 4),
            delta_away=round(delta_away, 4),
            confidence=confidence,
            notes="; ".join(notes) if notes else "no structural adjustments",
        )
