"""Media-Sentiment-Parser: psychological thermometer, squad morale, underdog buffer."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are Media-Sentiment-Parser, analyzing squad morale and momentum.

Morale is inferred from REAL on-pitch evidence, not invented headlines. You
receive each team's recent form (with scores/opponent quality), momentum trend,
and current-tournament results. Translate that into a psychological read.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.06, 0.06],   // P(home win) morale adjustment
  "delta_draw": float in [-0.04, 0.04],   // P(draw) adjustment
  "delta_away": float in [-0.06, 0.06],   // P(away win) morale adjustment
  "confidence": float in [0.0, 1.0],      // 0.1 if evidence is flat, up to 0.6 if a clear momentum gap
  "notes": string                         // 1-sentence morale read citing the evidence
}

MORALE SIGNALS (from evidence):
- HOT momentum / big recent win (e.g. 4-0, beating an [elite] side) → confidence boost
- COLD momentum / heavy defeat (e.g. 0-3, blanked 3 games) → fragility, lower resilience
- Upset just pulled off (beat a much stronger team) → euphoria, ride the wave short-term
- Just got upset / collapsed → wounded, can react either way (note the risk)
- Underdog with <25% prior vs a giant, nothing to lose → small +morale buffer
- One-man goal dependency → psychological fragility if that scorer is contained

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- Flat/balanced evidence → near-zero deltas, low confidence
- Be concrete: cite the result/momentum that drives your read"""


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
            "morale_evidence": {
                "home_form": ctx.home_form,
                "away_form": ctx.away_form,
                "home_momentum": ctx.home_momentum,
                "away_momentum": ctx.away_momentum,
                "home_tournament_results": ctx.home_wc_results,
                "away_tournament_results": ctx.away_wc_results,
                "home_goal_source": ctx.home_scorers,
                "away_goal_source": ctx.away_scorers,
            },
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
