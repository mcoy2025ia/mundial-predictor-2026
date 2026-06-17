"""IntMatch-Analytics-Pro: tactical matchup, home advantage, discipline, climate."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are IntMatch-Analytics-Pro, a lead sports analyst for FIFA World Cup 2026.
Analyze the match context JSON and return ONLY a JSON object with these keys:
- delta_home: float [-0.08, 0.08] — adjustment to P(home win)
- delta_draw: float [-0.05, 0.05] — adjustment to P(draw)
- delta_away: float [-0.08, 0.08] — adjustment to P(away win)
- confidence: float [0.0, 1.0] — how confident you are
- notes: string — max 2 bullet points, tactical rationale

Constraints: delta_home + delta_draw + delta_away must equal 0.

Key factors to weigh (in priority order):
1. GROUP QUALIFICATION PRESSURE: A team with 0-1 pts needing to win attacks desperately,
   increasing their win probability but also conceding more. A team already through (6 pts)
   rotates heavily — reduce their win probability by 3-5%.
2. MATCHDAY CONTEXT: MD3 simultaneous matches change team behavior completely.
   A team that only needs a draw will play conservatively → increase P(draw).
3. HOST NATION ADVANTAGE: USA/Mexico/Canada get real crowd boost — especially Mexico
   in Mexico City/Guadalajara/Monterrey venues.
4. TACTICAL STYLE CLASH: counter-attack teams benefit when facing possession-heavy
   opponents who must win. High press teams suffer in heat/altitude.
5. CARD ACCUMULATIONS: a team with 2 yellows each plays more cautiously."""


class IntMatchAgent(BaseAgent):
    name = "IntMatch-Analytics-Pro"
    model = "claude-haiku-4-5-20251001"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        payload = {
            "home": ctx.team_home,
            "away": ctx.team_away,
            "p_prior": {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away},
            "elo": {"home": ctx.elo_home, "away": ctx.elo_away},
            "is_neutral": ctx.is_neutral,
            "venue_city": ctx.venue_city,
            "round": ctx.round_label,
            "injuries": ctx.injuries,
            "group_context": {
                "group": ctx.group_name,
                "matchday": ctx.matchday,
                "home_pts": ctx.group_points_home,
                "away_pts": ctx.group_points_away,
                "home_games_played": ctx.games_played_home,
                "away_games_played": ctx.games_played_away,
                "standings": ctx.group_standings,
            } if ctx.group_points_home is not None else None,
        }
        raw = call_claude(_SYSTEM, payload, model=self.model, max_tokens=400)
        data = parse_delta_json(raw)

        return AgentResult(
            agent_name=self.name,
            delta_home=float(data.get("delta_home", 0.0)),
            delta_draw=float(data.get("delta_draw", 0.0)),
            delta_away=float(data.get("delta_away", 0.0)),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.4)))),
            notes=str(data.get("notes", "")),
            raw_response=raw,
        )
