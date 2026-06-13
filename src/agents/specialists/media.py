"""Media-Sentiment-Parser: psychological thermometer, squad morale, underdog buffer."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are Media-Sentiment-Parser, a behavioral psychologist for FIFA World Cup 2026.
Analyze the match context and return ONLY a JSON object with these keys:
- delta_home: float [-0.06, 0.06] — P(home win) morale/pressure adjustment
- delta_draw: float [-0.04, 0.04] — P(draw) adjustment
- delta_away: float [-0.06, 0.06] — P(away win) morale/pressure adjustment
- confidence: float [0.0, 1.0] — 0.2 if no media context, up to 0.7 if strong signal
- psychological_thermometer: int [1,100] — overall squad psychological readiness (home team)
- notes: string — max 2 bullet points: media pressure + underdog buffer assessment

Constraints: delta_home + delta_draw + delta_away must equal 0.
Key factors: underdog teams facing zero-pressure giants get +morale buffer.
Crisis-mode squads (heavy media scrutiny, internal conflict) get -resilience penalty.
Without specific media context, return all deltas as 0.0."""


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
