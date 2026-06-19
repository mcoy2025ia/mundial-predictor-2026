# Mundial Predictor 2026 - Architecture Brief

## Thesis

Mundial Predictor 2026 is a multi-agent evaluation lab for the 2026 World Cup. The football predictor is the benchmark environment; the real objective is to demonstrate agent orchestration, phase-aware reasoning, controlled DeepSeek model usage, cached outputs, and post-match evaluation.

## Layer 1: Statistical Benchmark

The benchmark predictor must work without LLM calls. It gives the agents a reproducible baseline to beat or explain.

Inputs:
- Historical international results from `data/raw/results.csv`.
- Official 2026 fixture from `data/external/wc2026_fixture.json`.
- Live 2026 results from `data/external/wc2026_live_results.csv`.

Main steps:
1. Normalize teams and match metadata.
2. Compute chronological ELO ratings.
3. Build feature matrix with ELO, form, H2H, neutrality and World Cup experience.
4. Train/calibrate XGBoost and fit Poisson goal model.
5. Blend ELO, Poisson and XGBoost in the ensemble.
6. Export frontend JSON artifacts.

Current documented ensemble:

```text
0.22 * ELO + 0.58 * Poisson + 0.20 * XGBoost
```

## Layer 2: Tournament Context

The tournament context layer gives agents the rules they need to reason correctly by phase: standings, matchday, goal difference, direct qualification, best third-place scenarios and simultaneous matches.

Important group-stage logic:
- Top two teams qualify from each group.
- Best third-place teams also qualify.
- J2 needs updated pressure after earlier results in the day.
- J3 needs simultaneous-match logic by group.

## Layer 3: Cached AI Narratives

The narrative layer explains what the agents and model are seeing in football language. It is precomputed and cached so users do not trigger LLM calls repeatedly.

Components:
- Precomputed match narrations in `frontend/public/data/narrations.json`.
- Group narratives from standings, fixtures and pressure context.
- Chat endpoint with topic filtering, cache, rate limiting and optional RAG.

## Layer 4: Agent Debate And Evaluation

Agent Debate is the main architecture demonstration. Multiple agents predict the same match from different perspectives, then the system evaluates each forecast after the real score is known.

Rules:
- Save all agent predictions before the match.
- Measure each agent separately from the benchmark model.
- Track 1X2 hit rate and exact-score hit rate.
- Adjust prompts, weights and model routing by phase.
- Fall back to deterministic model output when API keys, budget or agent execution fail.

## DeepSeek Model Strategy By Phase

| Phase | Model strategy | Reason |
|---|---|---|
| J1 | Lighter DeepSeek calls and cached narration | Context is still simple: favorites, localia, ELO and first results. |
| J2 | More capacity for pressure agents | Points, urgency, rival difficulty and mood start to matter. |
| J3 | DeepSeek Reasoner for selected debates | Simultaneity, goal difference and best-third qualification require multi-step reasoning. |
| Knockout | Reasoner selectively | Use the expensive model only for high-context matches: fatigue, injuries, penalties, tactical conflicts. |

## Key Artifacts

| Artifact | Purpose |
|---|---|
| `data/processed/live_predictions.json` | Backend benchmark predictions. |
| `frontend/public/data/live_predictions.json` | Frontend benchmark prediction feed. |
| `frontend/public/data/agent_debate_results.json` | Agent predictions and consensus outputs. |
| `frontend/public/data/group_standings.json` | Group tables. |
| `frontend/public/data/group_narratives.json` | Group-stage narratives. |
| `frontend/public/data/narrations.json` | Match narrative cache. |
| `logs/pipeline_runs.jsonl` | Pipeline observability. |
| `logs/llm_costs.jsonl` | LLM cost ledger. |

## Boundary Principle

The product should always make clear which layer produced a claim:

- ML model: benchmark probabilities.
- Agents: competing structured forecasts.
- Simulator: tournament scenarios.
- Narrator: cached explanation and storytelling.
- Evaluator: who beat whom after real results.
