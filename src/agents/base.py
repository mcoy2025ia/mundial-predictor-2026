"""Tipos base y ABC para el sistema multi-agente."""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class MatchContext:
    """Contexto de un partido enviado al sistema de agentes."""
    team_home: str
    team_away: str
    p_home: float               # prior XGBoost P(home win)
    p_draw: float               # prior XGBoost P(draw)
    p_away: float               # prior XGBoost P(away win)
    elo_home: float = 1500.0
    elo_away: float = 1500.0
    is_neutral: bool = True
    venue_city: Optional[str] = None      # ej: "Miami", "Mexico City"
    venue_altitude_m: int = 0             # metros sobre el nivel del mar
    round_label: Optional[str] = None     # "Group A MD1", "QF", etc.
    injuries: list = field(default_factory=list)  # ["Mbappé (knee)"]
    home_odds: Optional[float] = None     # odds decimales
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    query_hint: Optional[str] = None      # pista de routing del caller


@dataclass
class AgentResult:
    """Resultado de un agente especializado: delta_P sobre el prior."""
    agent_name: str
    delta_home: float = 0.0   # ajuste a P(home_win)
    delta_draw: float = 0.0   # ajuste a P(draw)
    delta_away: float = 0.0   # ajuste a P(away_win); suma con los otros debe ser ~0
    confidence: float = 0.5   # 0..1, escala el impacto del delta
    notes: str = ""
    raw_response: Optional[str] = None

    def is_neutral_delta(self, tol: float = 1e-6) -> bool:
        return abs(self.delta_home + self.delta_draw + self.delta_away) < tol


class BaseAgent(ABC):
    """Interfaz común para todos los agentes especialistas."""

    name: str = "BaseAgent"
    model: str = "claude-haiku-4-5-20251001"

    @abstractmethod
    def analyze(self, ctx: MatchContext) -> AgentResult:
        """Analiza el contexto y retorna un AgentResult con delta_P."""
        ...

    def safe_analyze(self, ctx: MatchContext) -> AgentResult:
        """Wrapper con manejo de errores; retorna delta=0 ante cualquier fallo."""
        try:
            result = self.analyze(ctx)
            # Normalizar: los deltas deben sumar 0 (redistribución de probabilidad)
            total = result.delta_home + result.delta_draw + result.delta_away
            if abs(total) > 1e-4:
                # Forzar suma=0 quitando el exceso del componente mayor
                result.delta_draw -= total
            return result
        except Exception as exc:
            logger.warning("[%s] safe_analyze error: %s", self.name, exc)
            return AgentResult(
                agent_name=self.name,
                notes=f"error: {exc}",
            )
