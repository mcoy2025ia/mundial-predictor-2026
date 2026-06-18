"""FinOps-Market-Calibration-Validator: Compare bookmaker odds with Ensemble prior.

IMPORTANT: This agent does NOT recommend bets or capital allocation.
It only detects if market implied probabilities diverge significantly from model.
This is a calibration check, not a betting tool.

Deterministic agent — no LLM call needed.
"""
from __future__ import annotations

import math

from src.agents.base import AgentResult, BaseAgent, MatchContext

# Umbral mínimo de edge para considerar que el mercado lleva información real
_MIN_VALUE_EDGE = 0.05
# Peso máximo que el mercado puede desplazar el prior (evita over-trust en odds)
_MAX_MARKET_WEIGHT = 0.15


class FinOpsAgent(BaseAgent):
    """Market calibration validator: compare odds with Ensemble prior.

    If market consensus diverges >= MIN_VALUE_EDGE from prior, adjust delta_P
    proportionally (capped at MAX_MARKET_WEIGHT).

    NO betting recommendations. Calibration check only.
    """

    name = "FinOps-Market-Calibration-Validator"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        if None in (ctx.home_odds, ctx.draw_odds, ctx.away_odds):
            return AgentResult(
                agent_name=self.name,
                notes="no odds provided — skipped",
            )

        # Extrae probabilidades brutas y elimina el margen del libro
        raw = [1 / ctx.home_odds, 1 / ctx.draw_odds, 1 / ctx.away_odds]
        overround = sum(raw)
        implied = [r / overround for r in raw]  # probabilidades limpias

        p_model = [ctx.p_home, ctx.p_draw, ctx.p_away]

        # Value index: cuánto difiere el mercado del modelo
        edges = [implied[i] - p_model[i] for i in range(3)]
        max_edge = max(edges, key=abs)
        edge_abs = abs(max_edge)

        if edge_abs < _MIN_VALUE_EDGE:
            return AgentResult(
                agent_name=self.name,
                notes=f"no value edge (max={edge_abs:.3f} < {_MIN_VALUE_EDGE})",
                confidence=0.3,
            )

        # Ajuste proporcional al edge, limitado a MAX_MARKET_WEIGHT
        scale = min(edge_abs / 0.20, 1.0) * _MAX_MARKET_WEIGHT
        margin = overround - 1.0

        notes_parts = [
            f"overround={margin:.1%}",
            f"implied=[{implied[0]:.2%},{implied[1]:.2%},{implied[2]:.2%}]",
            f"max_edge={max_edge:+.3f}",
        ]

        # Kelly fraction como señal de confianza (conservative Kelly)
        if max_edge > _MIN_VALUE_EDGE:
            p_model_idx = edges.index(max(edges))
            kelly = max_edge / (p_model[p_model_idx] if p_model[p_model_idx] > 0 else 1)
            kelly_conservative = min(kelly * 0.25, 0.50)
            confidence = round(kelly_conservative, 2)
            notes_parts.append(f"kelly_frac={kelly_conservative:.2f}")
        else:
            confidence = 0.25

        delta = [e * scale for e in edges]

        return AgentResult(
            agent_name=self.name,
            delta_home=round(delta[0], 4),
            delta_draw=round(delta[1], 4),
            delta_away=round(delta[2], 4),
            confidence=confidence,
            notes="; ".join(notes_parts),
        )
