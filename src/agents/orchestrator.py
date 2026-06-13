"""WorldCup2026-Core-Orchestrator: single entry point for the multi-agent system.

Routes to at most 2 sub-agents per call, strips tokens, applies weighted delta blending.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists import (
    FinOpsAgent,
    FIFARegsAgent,
    IntMatchAgent,
    MediaSentimentAgent,
    RosterScoutAgent,
    TravelLogisticsAgent,
)
from src.cost_guard import BudgetExceeded, get_guard

# Agentes que NO usan LLM (siempre seguros de llamar)
_DETERMINISTIC_AGENTS = {"FinOps-Bookmaker-Alpha", "FIFA-Regs-Strategist"}

logger = logging.getLogger(__name__)

# Pesos de contribución de cada agente al blend final (suma ≤ 1 por diseño)
_AGENT_WEIGHTS: dict[str, float] = {
    "Roster-Data-Scout": 0.30,        # datos concretos de jugadores → mayor impacto
    "IntMatch-Analytics-Pro": 0.25,   # táctico + clima → impacto medio-alto
    "FinOps-Bookmaker-Alpha": 0.20,   # mercado como señal independiente
    "Media-Sentiment-Parser": 0.10,   # psicológico → señal complementaria
    "Travel-Logistics-Quant": 0.10,   # logística → efecto pequeño pero real
    "FIFA-Regs-Strategist": 0.05,     # bracket/altitud → determinístico, bajo peso
}

# Máxima corrección total del prior por todos los agentes combinados
_MAX_TOTAL_SHIFT = 0.12


@dataclass
class OrchestratorOutput:
    """Salida estructurada del orquestador."""
    team_home: str
    team_away: str
    prior: dict           # {"home": float, "draw": float, "away": float}
    adjusted: dict        # probabilidades finales ajustadas
    agents_called: list[str]
    routing_decision: dict
    agent_results: list[AgentResult] = field(default_factory=list)


def _route(ctx: MatchContext) -> list[BaseAgent]:
    """Determina cuáles 2 agentes llamar según el contexto disponible.

    Prioridad: Roster (si hay lesiones) > FinOps (si hay odds) > IntMatch (siempre)
    > Travel (si hay altitud/ciudad) > FIFA-Regs (si hay info de grupo) > Media.
    Máximo 2 agentes por llamada (spec del orquestador).
    """
    queue: list[tuple[int, BaseAgent]] = []  # (priority, agent)

    if ctx.injuries:
        queue.append((1, RosterScoutAgent()))
    if ctx.home_odds is not None:
        queue.append((2, FinOpsAgent()))
    queue.append((3, IntMatchAgent()))
    if ctx.venue_altitude_m > 1500 or (
        ctx.venue_city and ctx.venue_city in (
            "Mexico City", "Guadalajara", "Monterrey", "Denver"
        )
    ):
        queue.append((4, TravelLogisticsAgent()))
    if ctx.round_label:
        queue.append((5, FIFARegsAgent()))
    queue.append((6, MediaSentimentAgent()))

    # Dedup por nombre (evita llamar el mismo agente dos veces)
    seen: set[str] = set()
    selected: list[BaseAgent] = []
    for _, agent in sorted(queue, key=lambda x: x[0]):
        if agent.name not in seen:
            seen.add(agent.name)
            selected.append(agent)
        if len(selected) == 2:
            break

    # Si query_hint sobreescribe el routing
    if ctx.query_hint:
        hint = ctx.query_hint.lower()
        override: Optional[BaseAgent] = None
        if "tactic" in hint or "match" in hint:
            override = IntMatchAgent()
        elif "odds" in hint or "bet" in hint:
            override = FinOpsAgent()
        elif "injur" in hint or "roster" in hint:
            override = RosterScoutAgent()
        elif "travel" in hint or "altitude" in hint:
            override = TravelLogisticsAgent()
        elif "bracket" in hint or "group" in hint:
            override = FIFARegsAgent()
        elif "media" in hint or "sentiment" in hint:
            override = MediaSentimentAgent()
        if override and override.name not in seen:
            selected = [override, selected[0]] if selected else [override]

    return selected[:2]


def _blend_deltas(results: list[AgentResult], prior: dict) -> dict:
    """Combina los delta_P de los agentes con sus pesos y confianzas.

    Formula: delta_i * weight_i * confidence_i, luego clamp a MAX_TOTAL_SHIFT,
    renormaliza a suma=1.
    """
    total_delta = {"home": 0.0, "draw": 0.0, "away": 0.0}

    for r in results:
        w = _AGENT_WEIGHTS.get(r.agent_name, 0.05)
        scale = w * r.confidence
        total_delta["home"] += r.delta_home * scale
        total_delta["draw"] += r.delta_draw * scale
        total_delta["away"] += r.delta_away * scale

    # Clamp: ninguna corrección supera MAX_TOTAL_SHIFT
    max_abs = max(abs(v) for v in total_delta.values())
    if max_abs > _MAX_TOTAL_SHIFT:
        factor = _MAX_TOTAL_SHIFT / max_abs
        total_delta = {k: v * factor for k, v in total_delta.items()}

    adjusted = {
        "home": prior["home"] + total_delta["home"],
        "draw": prior["draw"] + total_delta["draw"],
        "away": prior["away"] + total_delta["away"],
    }

    # Clamp a [0.02, 0.96] y renormalizar
    adjusted = {k: max(0.02, min(0.96, v)) for k, v in adjusted.items()}
    total = sum(adjusted.values())
    adjusted = {k: round(v / total, 4) for k, v in adjusted.items()}
    return adjusted


class Orchestrator:
    """API gateway del sistema multi-agente.

    Uso típico:
        ctx = MatchContext(team_home="Brazil", team_away="France",
                           p_home=0.38, p_draw=0.28, p_away=0.34,
                           elo_home=2010, elo_away=2050, is_neutral=True)
        out = Orchestrator().predict(ctx)
        print(out.adjusted)  # {"home": ..., "draw": ..., "away": ...}
    """

    def predict(self, ctx: MatchContext) -> OrchestratorOutput:
        agents = _route(ctx)
        agent_names = [a.name for a in agents]

        routing_meta = {
            "routing_decision": agent_names,
            "tokens_pruned_estimate": "conversation_history=stripped; only dense JSON payload forwarded",
            "active_constraints": [
                f"injuries={bool(ctx.injuries)}",
                f"odds_available={ctx.home_odds is not None}",
                f"altitude={ctx.venue_altitude_m}m",
            ],
        }

        logger.info("[Orchestrator] %s vs %s → agents: %s",
                    ctx.team_home, ctx.team_away, agent_names)

        guard = get_guard()
        results: list[AgentResult] = []
        for agent in agents:
            is_llm = agent.name not in _DETERMINISTIC_AGENTS
            if is_llm and guard.run_calls_remaining() == 0:
                logger.warning(
                    "[Orchestrator] Saltando %s — CostGuard: max_calls_per_run agotado",
                    agent.name,
                )
                results.append(AgentResult(agent_name=agent.name, notes="skipped: budget"))
                continue
            result = agent.safe_analyze(ctx)
            results.append(result)
            logger.info("[%s] delta=(h=%+.4f, d=%+.4f, a=%+.4f) conf=%.2f | %s",
                        result.agent_name, result.delta_home, result.delta_draw,
                        result.delta_away, result.confidence, result.notes[:80])

        prior = {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away}
        adjusted = _blend_deltas(results, prior)

        return OrchestratorOutput(
            team_home=ctx.team_home,
            team_away=ctx.team_away,
            prior=prior,
            adjusted=adjusted,
            agents_called=agent_names,
            routing_decision=routing_meta,
            agent_results=results,
        )
