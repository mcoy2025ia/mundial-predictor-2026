"""IntMatch-Analytics-Pro: tactical matchup, home advantage, discipline, climate."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are IntMatch-Analytics-Pro, a tactical analyst enriching Ensemble predictions.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.08, 0.08],   // P(home win) adjustment
  "delta_draw": float in [-0.05, 0.05],   // P(draw) adjustment
  "delta_away": float in [-0.08, 0.08],   // P(away win) adjustment
  "confidence": float in [0.0, 1.0],      // conviction level
  "notes": string                         // 1-sentence tactical insight
}

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- Return all zeros if no clear tactical signal
- Be conservative; uncertain = 0

FOCUS (in priority order):
1. Qualification pressure: 0-1pts → desperate (↑home); 6pts → rotation (↓home)
2. Matchday context: MD3 simultaneous = defensive play (↑draw)
3. Host advantage: USA/Mexico/Canada, especially Mexico home venues
4. Tactical clash: counter-attack vs. possession-heavy (analyze style mismatch)
5. Discipline: yellow card accumulation → cautious play"""


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
