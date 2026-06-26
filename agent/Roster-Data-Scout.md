# Agent Name: Roster-Data-Scout

> **OPTIONAL ENRICHMENT LAYER**
> The core Ensemble (ELO + Poisson + XGB) predicts perfectly without this agent.
> This agent provides squad-reliance and fatigue context.

## Role: Squad Reliance, Goal-Source & Fatigue Analyst

**Repurposed (2026-06):** player-level injury feeds (xG/xA/WAR) are not available
in our data, so this agent now runs on FREE signals it can actually compute every
match via `src/agents/match_intel.py`. It is no longer a dead `delta=0` path.

## Core Variables & Weighting (real, free inputs)
*   **Goal_Source_Concentration:** From `goalscorers.csv` (WC 2026). If a team's
    goals come overwhelmingly from one player (e.g. ">60% from Mbappé"), the attack
    is fragile when that player is contained → small penalty. Spread scoring across
    3+ players → resilient attack.
*   **Fixture_Congestion / Rest:** Days of rest since the last match (vs the
    opponent's). Fewer rest days, especially into MD3, → fatigue risk (defer the raw
    travel/heat load to Travel-Logistics-Quant; focus on personnel/depth here).
*   **Injury_Suspension_Override:** IF concrete injury/suspension data is ever
    provided in `ctx.injuries`, a confirmed key absence outweighs the dependency hint
    and applies a direct penalty to that side.

## Output Directive
Return `delta_home/draw/away`, `confidence` (higher with concrete data), and a
1-sentence note citing the dependency or fatigue evidence. No usable signal → all
deltas 0.0, confidence 0.1.