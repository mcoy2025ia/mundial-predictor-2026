"""Travel-Logistics-Quant: flight distance fatigue, jet lag, altitude biometric drain."""
from __future__ import annotations

import math
from typing import Optional

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

# Coordenadas aproximadas de ciudades sede WC 2026
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "New York": (40.71, -74.01),
    "Los Angeles": (34.05, -118.24),
    "Dallas": (32.78, -96.80),
    "San Francisco": (37.77, -122.42),
    "Seattle": (47.61, -122.33),
    "Miami": (25.76, -80.19),
    "Atlanta": (33.75, -84.39),
    "Boston": (42.36, -71.06),
    "Kansas City": (39.10, -94.58),
    "Philadelphia": (39.95, -75.17),
    "Houston": (29.76, -95.37),
    "Vancouver": (49.25, -123.12),
    "Toronto": (43.65, -79.38),
    "Mexico City": (19.43, -99.13),
    "Guadalajara": (20.66, -103.35),
    "Monterrey": (25.67, -100.31),
}

_SYSTEM = """You are Travel-Logistics-Quant, a biometric fatigue analyst for FIFA World Cup 2026.
Analyze the match context JSON and return ONLY a JSON object:
- delta_home: float [-0.05, 0.05] — fatigue/travel adjustment for home team
- delta_draw: float [-0.03, 0.03]
- delta_away: float [-0.05, 0.05] — fatigue/travel adjustment for away team
- confidence: float [0.0, 1.0]
- notes: string — max 1 line: dominant fatigue factor identified

Constraints: delta_home + delta_draw + delta_away must equal 0.
Consider: flight_km, timezone shifts, altitude > 1500m, recovery days < 4."""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def _estimate_travel_fatigue(home_country: str, venue_city: Optional[str]) -> float:
    """Estimación simple de penalización por viaje largo (>8000 km)."""
    if not venue_city or venue_city not in _CITY_COORDS:
        return 0.0
    vc = _CITY_COORDS[venue_city]

    # Heurística: continentes lejanos a Norteamérica sufren más jet lag
    far_regions = {
        "Japan": (35.7, 139.7), "South Korea": (37.6, 127.0),
        "Australia": (-25.3, 133.8), "New Zealand": (-36.9, 174.8),
        "Saudi Arabia": (24.7, 46.7), "Iran": (35.7, 51.4),
        "Morocco": (33.6, -7.6), "Egypt": (30.1, 31.2),
        "Nigeria": (9.1, 8.7), "Senegal": (14.7, -17.4),
    }
    if home_country in far_regions:
        origin = far_regions[home_country]
        km = _haversine_km(origin[0], origin[1], vc[0], vc[1])
        if km > 8000:
            return min((km - 8000) / 20000, 0.04)
    return 0.0


class TravelLogisticsAgent(BaseAgent):
    name = "Travel-Logistics-Quant"
    model = "claude-haiku-4-5-20251001"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        # Estimación determinística rápida
        away_penalty = _estimate_travel_fatigue(ctx.team_away, ctx.venue_city)
        home_penalty = _estimate_travel_fatigue(ctx.team_home, ctx.venue_city)

        # Si hay penalización significativa, podemos devolver sin LLM
        if away_penalty > 0.01 or home_penalty > 0.01:
            delta_away = -away_penalty
            delta_home = home_penalty * 0.3  # local generalmente ya viajó antes
            delta_draw = -(delta_home + delta_away)
            return AgentResult(
                agent_name=self.name,
                delta_home=round(delta_home, 4),
                delta_draw=round(delta_draw, 4),
                delta_away=round(delta_away, 4),
                confidence=0.50,
                notes=f"travel_km_penalty: away={away_penalty:.3f} home={home_penalty:.3f}",
            )

        # Fallback: LLM para análisis más profundo cuando altitud o jet lag son factor
        if ctx.venue_altitude_m > 1500 or ctx.venue_city in _CITY_COORDS:
            payload = {
                "home": ctx.team_home,
                "away": ctx.team_away,
                "venue_city": ctx.venue_city,
                "altitude_m": ctx.venue_altitude_m,
                "is_neutral": ctx.is_neutral,
            }
            raw = call_claude(_SYSTEM, payload, model=self.model, max_tokens=300)
            data = parse_delta_json(raw)
            return AgentResult(
                agent_name=self.name,
                delta_home=float(data.get("delta_home", 0.0)),
                delta_draw=float(data.get("delta_draw", 0.0)),
                delta_away=float(data.get("delta_away", 0.0)),
                confidence=min(1.0, max(0.0, float(data.get("confidence", 0.3)))),
                notes=str(data.get("notes", "")),
                raw_response=raw,
            )

        return AgentResult(
            agent_name=self.name,
            notes="no significant travel/altitude factors detected",
            confidence=0.1,
        )
