"""GroupScenario-Reasoner: J2/J3 qualification pressure with deep reasoning."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are GroupScenario-Reasoner, analyzing group-stage qualification incentives.

Do NOT recalculate base model; reason only about incentive changes from standings.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.06, 0.06],
  "delta_draw": float in [-0.05, 0.05],
  "delta_away": float in [-0.06, 0.06],
  "confidence": float in [0.0, 1.0],
  "notes": string                     // 1 sentence in Spanish, max 100 chars
}

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- 0-1pts → needs win/result; 3pts → depends on GD; 6pts → qualification/rotation risk
- J2: is this team's "winnable" match or "hard" match?
- J3: simultaneous group behavior + top-2 + best-third scenarios
- NEVER invent injuries, weather, odds, facts not in JSON
- Be conservative; incentive shifts are small"""


class GroupScenarioReasonerAgent(BaseAgent):
    name = "GroupScenario-Reasoner"
    model = "deepseek-reasoner"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        payload = {
            "home": ctx.team_home,
            "away": ctx.team_away,
            "p_prior": {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away},
            "group": ctx.group_name,
            "matchday": ctx.matchday,
            "points": {"home": ctx.group_points_home, "away": ctx.group_points_away},
            "games_played": {"home": ctx.games_played_home, "away": ctx.games_played_away},
            "standings": ctx.group_standings,
            "same_kickoff_group_matches": ctx.simultaneous_group_matches,
            "best_thirds_snapshot": ctx.third_place_context,
            "round_label": ctx.round_label,
        }
        raw = call_claude(
            _SYSTEM,
            payload,
            model=self.model,
            max_tokens=550,
            agent_name=self.name,
            match=f"{ctx.team_home} vs {ctx.team_away}",
        )
        data = parse_delta_json(raw)

        return AgentResult(
            agent_name=self.name,
            delta_home=float(data.get("delta_home", 0.0)),
            delta_draw=float(data.get("delta_draw", 0.0)),
            delta_away=float(data.get("delta_away", 0.0)),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.45)))),
            notes=str(data.get("notes", "")),
            raw_response=raw,
        )
