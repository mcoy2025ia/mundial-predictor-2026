"""Media-Sentiment-Parser: psychological thermometer, squad morale, underdog buffer."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are Media-Sentiment-Parser, analyzing squad morale and pressure signals.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.06, 0.06],   // P(home win) morale adjustment
  "delta_draw": float in [-0.04, 0.04],   // P(draw) adjustment
  "delta_away": float in [-0.06, 0.06],   // P(away win) morale adjustment
  "confidence": float in [0.0, 1.0],      // 0.1 if no signal, up to 0.6 if clear
  "notes": string                         // 1-sentence morale/pressure insight
}

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- No media context → all deltas = 0.0
- Underdog bonus: team with <25% win prob facing giant = +morale
- Crisis mode: team with heavy negative media scrutiny = -resilience
- Be conservative; avoid speculation"""


class MediaSentimentAgent(BaseAgent):
    name = "Media-Sentiment-Parser"
    model = "claude-sonnet-4-6"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        payload = {
            "home": ctx.team_home,
            "away": ctx.team_away,
            "p_prior": {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away},
            "elo": {"home": ctx.elo_home, "away": ctx.elo_away},
            "round": ctx.round_label,
            "is_neutral": ctx.is_neutral,
        }
        raw = call_claude(_SYSTEM, payload, model=self.model, max_tokens=400)
        data = parse_delta_json(raw)

        notes = str(data.get("notes", ""))
        therm = data.get("psychological_thermometer")
        if therm is not None:
            notes = f"[Therm={therm}] {notes}"

        return AgentResult(
            agent_name=self.name,
            delta_home=float(data.get("delta_home", 0.0)),
            delta_draw=float(data.get("delta_draw", 0.0)),
            delta_away=float(data.get("delta_away", 0.0)),
            confidence=min(1.0, max(0.0, float(data.get("confidence", 0.2)))),
            notes=notes,
            raw_response=raw,
        )
