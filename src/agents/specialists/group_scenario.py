"""GroupScenario-Reasoner: J2/J3 qualification pressure with deep reasoning."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are GroupScenario-Reasoner for FIFA World Cup 2026.
Your job is not to recalculate the base model. Your job is to reason about group-stage incentives.

Use only the provided JSON. Return ONLY a JSON object:
- delta_home: float [-0.06, 0.06]
- delta_draw: float [-0.05, 0.05]
- delta_away: float [-0.06, 0.06]
- confidence: float [0.0, 1.0]
- notes: short Spanish note, max 240 chars

Constraints:
- delta_home + delta_draw + delta_away must equal 0.
- If both teams mainly need not to lose, increase draw.
- If a team has 0-1 points in J2/J3, it usually needs a result or win.
- In J2, decide whether this is the winnable match or the hard group match from prior probabilities.
- In J3, consider simultaneous group behavior, top-2 qualification, and best-third pressure.
- Four points are usually strong for best third; three points depend on goal difference and other groups.
- Six points imply qualification/rotation risk.
- Never invent injuries, weather, odds, or external facts.
"""


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
