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
    # ── Contexto de fase de grupos ──────────────────────────────────────────
    group_name: Optional[str] = None          # "Group A"
    group_points_home: Optional[int] = None   # puntos acumulados en el grupo
    group_points_away: Optional[int] = None
    games_played_home: int = 0                # partidos jugados en el grupo
    games_played_away: int = 0
    days_rest_home: Optional[int] = None      # días desde el último partido
    days_rest_away: Optional[int] = None
    prev_city_home: Optional[str] = None      # sede del partido anterior (para viaje)
    prev_city_away: Optional[str] = None
    group_standings: Optional[str] = None     # "1.MEX 6pts 2.USA 3pts 3.URU 1pt 4.BOL 0pts"
    simultaneous_group_matches: Optional[str] = None
    third_place_context: Optional[str] = None
    matchday: Optional[int] = None            # 1, 2, o 3 en fase de grupos
    # ── Inteligencia de partido (MatchIntel, todo derivado gratis) ───────────
    home_form: Optional[str] = None           # "(3W-1D-1L) W 2-0 vs RSA[weak] | ..."
    away_form: Optional[str] = None
    home_goal_trend: Optional[str] = None      # "scored 2.4/g, conceded 0.6/g, 2 clean sheets"
    away_goal_trend: Optional[str] = None
    home_momentum: Optional[str] = None        # "hot" / "rising" / "falling" / "cold"
    away_momentum: Optional[str] = None
    h2h_summary: Optional[str] = None          # "3 meetings: FRA 2W-1D-0L. Recent: 2-1, 1-1"
    home_wc_results: Optional[str] = None       # resultados en WC 2026 con calidad del rival
    away_wc_results: Optional[str] = None
    home_scorers: Optional[str] = None          # "5 WC goals (1 pen): Mbappé 3 — HIGH dependency"
    away_scorers: Optional[str] = None
    third_place_math: Optional[str] = None      # matemática exacta de mejor tercero


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
