"""IntMatch-Analytics-Pro: tactical matchup, home advantage, discipline, climate."""
from __future__ import annotations

from src.agents.base import AgentResult, BaseAgent, MatchContext
from src.agents.specialists._llm import call_claude, parse_delta_json

_SYSTEM = """You are IntMatch-Analytics-Pro, a tactical analyst enriching Ensemble predictions.

You now receive REAL EVIDENCE: recent form (with scores and opponent quality),
goal-scoring/conceding trends, head-to-head record, current-tournament results,
and each team's goal source. Reason from this evidence, not from team reputation.

Return ONLY a JSON object:
{
  "delta_home": float in [-0.08, 0.08],   // P(home win) adjustment
  "delta_draw": float in [-0.05, 0.05],   // P(draw) adjustment
  "delta_away": float in [-0.08, 0.08],   // P(away win) adjustment
  "confidence": float in [0.0, 1.0],      // conviction level (raise it when evidence is concrete)
  "notes": string                         // 1-sentence tactical insight citing the evidence
}

CONSTRAINTS:
- Deltas sum to 0 (redistribution only)
- Return near-zero only when the evidence is genuinely balanced
- Cite concrete evidence in notes (e.g. "FRA conceded 0/g last 5, NOR leaks goals")

FOCUS (in priority order):
1. FORM & GOAL TRENDS: a team scoring 2.5/g and keeping clean sheets beats its
   ELO prior; a team that hasn't scored in 3 games is overrated by the prior.
2. STYLE CLASH from goal trends: high-scoring + leaky vs low-scoring + solid
   → favor the side whose strength exploits the other's weakness.
3. GOAL SOURCE: a team with HIGH dependency on one scorer is fragile if that
   player is neutralized; spread scoring is more reliable.
4. HEAD-TO-HEAD: persistent historical dominance is a real tactical signal.
5. QUALIFICATION PRESSURE: 0-1pts → desperate; 6pts already-through → rotation.
6. MATCHDAY: MD3 simultaneous = cautious play (↑draw); host advantage USA/MEX/CAN.
7. Quality of recent wins: beating [elite]/[strong] sides means more than beating [weak]."""


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
            "evidence": {
                "home_form": ctx.home_form,
                "away_form": ctx.away_form,
                "home_goal_trend": ctx.home_goal_trend,
                "away_goal_trend": ctx.away_goal_trend,
                "home_momentum": ctx.home_momentum,
                "away_momentum": ctx.away_momentum,
                "head_to_head": ctx.h2h_summary,
                "home_tournament_results": ctx.home_wc_results,
                "away_tournament_results": ctx.away_wc_results,
                "home_goal_source": ctx.home_scorers,
                "away_goal_source": ctx.away_scorers,
            },
            "group_context": {
                "group": ctx.group_name,
                "matchday": ctx.matchday,
                "home_pts": ctx.group_points_home,
                "away_pts": ctx.group_points_away,
                "home_games_played": ctx.games_played_home,
                "away_games_played": ctx.games_played_away,
                "standings": ctx.group_standings,
                "third_place_math": ctx.third_place_math,
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
