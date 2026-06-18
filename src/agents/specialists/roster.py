"""Roster-Data-Scout: xG/xA, injury risk, WAR model for squad changes."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are Roster-Data-Scout, enriching predictions with squad/injury data.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.10, 0.10],   // P(home win) adjustment
  "delta_draw": float in [-0.06, 0.06],   // P(draw) adjustment
  "delta_away": float in [-0.10, 0.10],   // P(away win) adjustment
  "confidence": float in [0.0, 1.0],      // based on data specificity
  "notes": string                         // 1-sentence player impact summary
}

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- Large adjustments ONLY with concrete injury/suspension data
- No data → all deltas = 0.0, confidence = 0.1
- Be conservative; speculate minimally"""


class RosterScoutAgent(BaseAgent):
    name = "Roster-Data-Scout"
    model = "claude-sonnet-4-6"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        if not ctx.injuries:
            return AgentResult(
                agent_name=self.name,
                notes="no injury/suspension data — skipped",
                confidence=0.1,
            )

        payload = {
            "home": ctx.team_home,
            "away": ctx.team_away,
            "p_prior": {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away},
            "elo_diff": ctx.elo_home - ctx.elo_away,
            "injuries": ctx.injuries,
            "round": ctx.round_label,
        }
        raw = call_claude(_SYSTEM, payload, model=self.model, max_tokens=500)
        data = parse_delta_json(raw)

        return AgentResult(
            agent_name=self.name,
            delta_home=float(data.get("delta_home", 0.0)),
            delta_draw=float(data.get("delta_draw", 0.0)),
            delta_away=float(data.get("delta_away", 0.0)),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.5)))),
            notes=str(data.get("notes", "")),
            raw_response=raw,
        )
