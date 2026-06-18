"""FIFA-Regs-Strategist: group pressure, altitude, and rotation risk.

This agent is deterministic and does not call an LLM. It is intentionally
conservative: it nudges the match prior, while the ensemble remains the main
forecast.
"""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext


_MAX_GROUP_DELTA = 0.06
_THIRD_PLACE_SAFE_POINTS = 4


def _altitude_penalty(altitude_m: int) -> float:
    """Aerobic penalty for altitude, roughly 1% VO2max per 300m above 1500m."""
    if altitude_m < 1500:
        return 0.0
    return min((altitude_m - 1500) / 300 * 0.01, 0.06)


def _qualification_pressure(points: int, games_played: int, matchday: int) -> str:
    """Classify a team's group-stage situation before the current match.

    The 2026 format sends the top 2 in each group plus the best 8 third-place
    teams to R32. Four points are therefore treated as a strong third-place
    threshold, while three points remain volatile and goal-difference driven.

    Returns one of:
    "neutral" | "must_win" | "needs_result" | "third_place_watch" |
    "comfortable" | "already_through" | "unknown"
    """
    if games_played >= 3:
        return "unknown"

    games_remaining = 3 - games_played

    if matchday >= 3 or games_remaining <= 1:
        if points >= 6:
            return "already_through"
        if points >= _THIRD_PLACE_SAFE_POINTS:
            return "comfortable"
        if points == 3:
            return "third_place_watch"
        if points in (1, 2):
            return "needs_result"
        return "must_win"

    if matchday == 2 or games_remaining == 2:
        if points == 0:
            return "must_win"
        if points >= 3:
            return "comfortable"
        return "needs_result"

    if points >= 6:
        return "already_through"
    return "comfortable" if points > 0 else "neutral"


def _pressure_to_delta(situation: str, *, is_home: bool) -> float:
    """Convert pressure into a team-specific win-probability delta.

    Positive values always benefit the team being evaluated, regardless of
    whether it is home or away. Draw absorbs the zero-sum correction later.
    """
    if situation == "must_win":
        return 0.03
    if situation == "needs_result":
        return 0.015
    if situation == "third_place_watch":
        return 0.02
    if situation == "already_through":
        return -0.025
    if situation == "comfortable" and is_home:
        return -0.005
    return 0.0


class FIFARegsAgent(BaseAgent):
    """Adjust the prior using group pressure, altitude, and rotation context."""

    name = "FIFA-Regs-Strategist"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        notes: list[str] = []
        delta_home = 0.0
        delta_away = 0.0

        matchday = ctx.matchday or 1

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

        if ctx.venue_altitude_m > 1500:
            pen = _altitude_penalty(ctx.venue_altitude_m)
            if pen > 0:
                if not ctx.is_neutral:
                    delta_home += pen * 0.25
                    delta_away -= pen
                    notes.append(f"altitude={ctx.venue_altitude_m}m pen={pen:.3f} (local_adv)")
                else:
                    venue = ctx.venue_city or ""
                    if ctx.team_home == "Mexico" and venue in (
                        "Mexico City",
                        "Guadalajara",
                        "Monterrey",
                    ):
                        delta_home += pen * 0.5
                        delta_away -= pen * 0.5
                        notes.append(f"altitude={ctx.venue_altitude_m}m home_acclimatized")
                    else:
                        notes.append(f"altitude={ctx.venue_altitude_m}m both_affected")

        if matchday == 3:
            if ctx.group_points_home is not None and ctx.group_points_home >= 6:
                delta_home -= 0.025
                notes.append("home_MD3_rotation_risk(6pts)")
            if ctx.group_points_away is not None and ctx.group_points_away >= 6:
                delta_away -= 0.025
                notes.append("away_MD3_rotation_risk(6pts)")

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
