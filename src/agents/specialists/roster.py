"""Roster-Data-Scout: squad reliance, goal-source concentration, fatigue/congestion.

Originally this agent needed player injury feeds we don't have, so it always
skipped (delta=0). It is now repurposed to a SQUAD-RELIANCE analyst driven by
free signals we DO have:

  - goal-source concentration (one striker carrying the team vs spread scoring)
  - fixture congestion / rest days (a tired squad with one key man is brittle)
  - injuries/suspensions IF ever provided (bonus, not required)

This gives it a real, evidence-backed job every match instead of dead weight.
"""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are Roster-Data-Scout, assessing squad reliance and fatigue.

You receive each team's goal source (who scored the tournament goals and whether
the team depends on one player), rest days since last match, and — if available —
injuries/suspensions. Judge squad robustness, not reputation.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.08, 0.08],   // P(home win) adjustment
  "delta_draw": float in [-0.05, 0.05],   // P(draw) adjustment
  "delta_away": float in [-0.08, 0.08],   // P(away win) adjustment
  "confidence": float in [0.0, 1.0],      // higher with concrete injury/dependency data
  "notes": string                         // 1-sentence squad insight citing evidence
}

SIGNALS:
- Goal concentration on one scorer is NOT automatically a weakness — it often means an
  elite finisher. Treat it as a risk ONLY if that player has a confirmed injury/suspension,
  or a clear matchup lets the opponent isolate him. Otherwise it can be a strength.
- Spread scoring across 3+ players → resilient, harder-to-shut-down attack
- Fewer rest days than the opponent (congestion) → fatigue risk, especially MD3 (↓ that team)
- Concrete injury/suspension of a key player → apply a real penalty to that side
- A confirmed key absence is the only signal that turns goal concentration into fragility

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- No usable signal at all → all deltas = 0.0, confidence = 0.1
- Don't double-count fatigue the Travel agent already handles; focus on squad/personnel"""


class RosterScoutAgent(BaseAgent):
    name = "Roster-Data-Scout"
    model = "claude-sonnet-4-6"

    def analyze(self, ctx: MatchContext) -> AgentResult:
        has_signal = bool(
            ctx.injuries
            or ctx.home_scorers
            or ctx.away_scorers
            or ctx.days_rest_home is not None
            or ctx.days_rest_away is not None
        )
        if not has_signal:
            return AgentResult(
                agent_name=self.name,
                notes="no roster/dependency/fatigue signal — skipped",
                confidence=0.1,
            )

        payload = {
            "home": ctx.team_home,
            "away": ctx.team_away,
            "p_prior": {"home": ctx.p_home, "draw": ctx.p_draw, "away": ctx.p_away},
            "elo_diff": ctx.elo_home - ctx.elo_away,
            "round": ctx.round_label,
            "matchday": ctx.matchday,
            "injuries": ctx.injuries,
            "home_goal_source": ctx.home_scorers,
            "away_goal_source": ctx.away_scorers,
            "rest_days": {"home": ctx.days_rest_home, "away": ctx.days_rest_away},
        }
        raw = call_claude(_SYSTEM, payload, model=self.model, max_tokens=500)
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
