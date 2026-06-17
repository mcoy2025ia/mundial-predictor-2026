"""Travel-Logistics-Quant: flight distance fatigue, jet lag, altitude, heat/humidity."""
from __future__ import annotations

import math
from typing import Optional

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

# Coordenadas de ciudades sede WC 2026
_CITY_COORDS: dict[str, tuple[float, float]] = {
    "New York":     (40.71, -74.01),
    "Los Angeles":  (34.05, -118.24),
    "Dallas":       (32.78, -96.80),
    "San Francisco":(37.77, -122.42),
    "Seattle":      (47.61, -122.33),
    "Miami":        (25.76, -80.19),
    "Atlanta":      (33.75, -84.39),
    "Boston":       (42.36, -71.06),
    "Kansas City":  (39.10, -94.58),
    "Philadelphia": (39.95, -75.17),
    "Houston":      (29.76, -95.37),
    "Vancouver":    (49.25, -123.12),
    "Toronto":      (43.65, -79.38),
    "Mexico City":  (19.43, -99.13),
    "Guadalajara":  (20.66, -103.35),
    "Monterrey":    (25.67, -100.31),
}

# Índice de calor en junio-julio (°C promedio + humedad): penalización para equipos
# que vienen de climas fríos o templados. Equipos de África/Asia/Sudamérica tropical = 0.
_HEAT_PENALTY: dict[str, float] = {
    "Miami":        0.025,   # ~32°C + humedad muy alta, peor sede para europeos norteños
    "Houston":      0.022,   # ~35°C + humedad alta
    "Dallas":       0.018,   # ~38°C pero baja humedad (más tolerable)
    "Atlanta":      0.015,
    "Kansas City":  0.012,
    "Philadelphia": 0.008,
    "New York":     0.005,
    "Los Angeles":  0.003,   # clima mediterráneo, tolerable
    "San Francisco":0.000,   # frío en junio
    "Seattle":      0.000,
    "Boston":       0.005,
    "Vancouver":    0.000,
    "Toronto":      0.005,
    "Mexico City":  0.000,   # 19°C media junio — fresco por altitud
    "Guadalajara":  0.008,
    "Monterrey":    0.018,   # muy caluroso en junio
}

# Equipos aclimatados al calor (África ecuatorial, Asia sudeste, Caribe)
_HEAT_ADAPTED: frozenset[str] = frozenset({
    "Nigeria", "Ghana", "Cameroon", "Ivory Coast", "Morocco", "Senegal",
    "Egypt", "Algeria", "Tunisia", "Cape Verde", "DR Congo",
    "Japan", "South Korea", "Iran", "Saudi Arabia", "Iraq",
    "Qatar", "Australia", "New Zealand",
    "Colombia", "Ecuador", "Venezuela", "Haiti", "Panama", "Cuba",
    "Brazil", "Mexico", "United States",
})

_SYSTEM = """You are Travel-Logistics-Quant, a biometric fatigue analyst for FIFA World Cup 2026.
Analyze the match context JSON and return ONLY a JSON object:
- delta_home: float [-0.05, 0.05] — net fatigue/climate adjustment for home team (positive = benefits home)
- delta_draw: float [-0.03, 0.03]
- delta_away: float [-0.05, 0.05] — net fatigue/climate adjustment for away team
- confidence: float [0.0, 1.0]
- notes: string — max 1 line: dominant factor identified

Constraints: delta_home + delta_draw + delta_away must equal 0.
Prioritize: (1) inter-city displacement km since last match, (2) heat+humidity at venue,
(3) altitude > 1500m, (4) timezone shifts. Days of rest amplifies or reduces all effects."""


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return 2 * R * math.asin(math.sqrt(a))


def _intercity_fatigue(from_city: Optional[str], to_city: Optional[str]) -> float:
    """Penalización por desplazamiento entre sedes del torneo.

    Ejemplo: Vancouver → Miami = ~4700 km → impacto real en recuperación.
    """
    if not from_city or not to_city or from_city == to_city:
        return 0.0
    c1 = _CITY_COORDS.get(from_city)
    c2 = _CITY_COORDS.get(to_city)
    if not c1 or not c2:
        return 0.0
    km = _haversine_km(c1[0], c1[1], c2[0], c2[1])
    # < 1000 km: sin efecto real (autobús/vuelo corto)
    # 1000-3000 km: efecto leve
    # > 3000 km: efecto significativo
    if km < 1000:
        return 0.0
    elif km < 3000:
        return round((km - 1000) / 40000, 4)   # max 0.05 a 3000 km
    else:
        return min(round((km - 3000) / 30000 + 0.05, 4), 0.04)


def _origin_fatigue(team: str, venue_city: Optional[str]) -> float:
    """Penalización por viaje intercontinental desde el país de origen."""
    if not venue_city or venue_city not in _CITY_COORDS:
        return 0.0
    vc = _CITY_COORDS[venue_city]
    far_regions: dict[str, tuple[float, float]] = {
        "Japan": (35.7, 139.7), "South Korea": (37.6, 127.0),
        "Australia": (-25.3, 133.8), "New Zealand": (-36.9, 174.8),
        "Saudi Arabia": (24.7, 46.7), "Iran": (35.7, 51.4),
        "Iraq": (33.3, 44.4),
        "Morocco": (33.6, -7.6), "Egypt": (30.1, 31.2),
        "Nigeria": (9.1, 8.7), "Senegal": (14.7, -17.4),
        "Ivory Coast": (5.4, -4.0), "Cameroon": (3.9, 11.5),
    }
    if team in far_regions:
        origin = far_regions[team]
        km = _haversine_km(origin[0], origin[1], vc[0], vc[1])
        if km > 8000:
            return min((km - 8000) / 20000, 0.035)
    return 0.0


def _heat_fatigue(team: str, venue_city: Optional[str]) -> float:
    """Penalización por calor/humedad para equipos no aclimatados."""
    if not venue_city:
        return 0.0
    base_penalty = _HEAT_PENALTY.get(venue_city, 0.0)
    if base_penalty == 0.0:
        return 0.0
    if team in _HEAT_ADAPTED:
        return 0.0   # ya aclimatados, sin penalización
    return base_penalty


class TravelLogisticsAgent(BaseAgent):
    name = "Travel-Logistics-Quant"
    model = "claude-haiku-4-5-20251001"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        venue = ctx.venue_city

        # ── Factores determinísticos ─────────────────────────────────────────
        # 1. Desplazamiento inter-sede (partido anterior → este)
        home_intercity = _intercity_fatigue(ctx.prev_city_home, venue)
        away_intercity = _intercity_fatigue(ctx.prev_city_away, venue)

        # 2. Viaje intercontinental de origen
        home_origin = _origin_fatigue(ctx.team_home, venue)
        away_origin = _origin_fatigue(ctx.team_away, venue)

        # 3. Calor/humedad
        home_heat = _heat_fatigue(ctx.team_home, venue)
        away_heat = _heat_fatigue(ctx.team_away, venue)

        # Amplificar si pocos días de descanso
        rest_factor = 1.0
        min_rest = min(
            ctx.days_rest_home or 4,
            ctx.days_rest_away or 4,
        )
        if min_rest <= 3:
            rest_factor = 1.4   # partidos cada 3 días o menos = más cansancio
        elif min_rest <= 2:
            rest_factor = 1.8

        home_total = (home_intercity + home_origin + home_heat) * rest_factor
        away_total = (away_intercity + away_origin + away_heat) * rest_factor

        delta_diff = away_total - home_total   # positivo → home se ve favorecido

        # Si hay diferencia determinística significativa, devolvemos sin LLM
        if abs(delta_diff) > 0.008 or home_total > 0.015 or away_total > 0.015:
            delta_home = round(min(delta_diff * 0.5, 0.05), 4)
            delta_away = round(-delta_diff * 0.5, 4)
            delta_draw = round(-(delta_home + delta_away), 4)
            notes = (
                f"home_fatigue={home_total:.3f}(ic={home_intercity:.3f}"
                f" heat={home_heat:.3f}) "
                f"away_fatigue={away_total:.3f}(ic={away_intercity:.3f}"
                f" heat={away_heat:.3f}) "
                f"rest_factor={rest_factor:.1f}"
            )
            return AgentResult(
                agent_name=self.name,
                delta_home=delta_home,
                delta_draw=delta_draw,
                delta_away=delta_away,
                confidence=0.55,
                notes=notes,
            )

        # LLM para altitud o contexto que el modelo determinístico no cubre bien
        if ctx.venue_altitude_m > 1500 or (venue and venue in _CITY_COORDS):
            payload = {
                "home": ctx.team_home,
                "away": ctx.team_away,
                "venue_city": venue,
                "altitude_m": ctx.venue_altitude_m,
                "is_neutral": ctx.is_neutral,
                "prev_city_home": ctx.prev_city_home,
                "prev_city_away": ctx.prev_city_away,
                "days_rest_home": ctx.days_rest_home,
                "days_rest_away": ctx.days_rest_away,
                "home_intercity_km": round(
                    _haversine_km(*(_CITY_COORDS.get(ctx.prev_city_home, (0, 0))),
                                  *(_CITY_COORDS.get(venue, (0, 0)))) if ctx.prev_city_home and venue else 0
                , 0),
                "away_intercity_km": round(
                    _haversine_km(*(_CITY_COORDS.get(ctx.prev_city_away, (0, 0))),
                                  *(_CITY_COORDS.get(venue, (0, 0)))) if ctx.prev_city_away and venue else 0
                , 0),
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
            notes="no significant travel/climate factors",
            confidence=0.1,
        )
