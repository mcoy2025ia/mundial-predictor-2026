# Mundial Predictor 2026 - AI FinOps Brief

## Goal

Use AI where agent reasoning adds measurable value, not where deterministic code already solves the problem. The product should remain usable when all LLM calls are disabled, and every expensive call should produce an artifact that can be evaluated later.

## Cost Controls

Implemented or documented controls:

- `CostGuard` reads `configs/budget.yaml`.
- LLM cost events are written to `logs/llm_costs.jsonl`.
- The chat endpoint applies topic filtering before model calls.
- Chat responses are cached in memory for warm serverless instances.
- Rate limiting protects against repeated user calls.
- Narrations are precomputed once per day instead of generated per user.
- Agents fail gracefully and return to the deterministic ensemble.

## Current Cost Snapshot And Projection

Operational cost reported as of the current review: **USD 0.51**.

Latest local ledger reviewed: `logs/llm_costs.jsonl`. The ledger can be lower than the operational total if some calls were estimated, run outside the local ledger, or summarized after the fact.

| Cut | Registered cost |
|---|---:|
| Total LLM calls | 1,734 |
| Local ledger subtotal | 0.332464 |
| Operational total to date | 0.51 |
| DeepSeek Reasoner / Agent Debate | 0.159421 |
| DeepSeek Chat / narratives + chat | 0.149083 |
| Claude fallback/testing | 0.023960 |

These values are historical/operational spend, not guaranteed future cost.

## Cost Per Match

| Component | Cost per match | Why |
|---|---:|---|
| Agent Debate System | ~0.08-0.10 | 9 calls to DeepSeek Reasoner: 3 agents times 3 debate rounds. Reasoner bills extended thinking tokens, not only final output. |
| Narrator AI, bogotano | ~0.016 | 1 DeepSeek call for the match narration. Group stage uses one dialect for stability; five dialects would multiply this layer. |
| Specialist agents | ~0.01-0.02 | Up to two specialist agents per match depending on budget and context. Complexity increases from J1 to J3. |

Approximate full-stack cost per match: **USD 0.11-0.14**.

Assuming 104 total World Cup matches, 28 already recorded results and 76 matches remaining:

| Projection | Estimate |
|---|---:|
| Remaining low case | 76 x 0.11 = 8.36 |
| Remaining high case | 76 x 0.14 = 10.64 |
| Final low case | 0.51 + 8.36 = 8.87 |
| Final high case | 0.51 + 10.64 = 11.15 |

This projection assumes the full AI stack runs for every remaining match. If Agent Debate is restricted to selected matches, the final cost falls materially.

## Why Agent Debate Dominates Cost

- It is the main component using `deepseek-reasoner`.
- It performs 9 model calls per match instead of one.
- Extended reasoning/thinking tokens are billed even when they are not shown in the final UI.
- That makes a debated match roughly 5-6x more expensive than a standard narration-only call.

## Model Use Boundaries

Recommended separation:

| Use case | Recommended path |
|---|---|
| Match probability | Core ML ensemble. |
| Exact score candidates | Agent Debate plus Poisson top scorelines as benchmark context. |
| Jornada narrative | Precomputed DeepSeek narrative from structured standings input. |
| User chat | DeepSeek plus injected tournament context and optional RAG. |
| Embeddings | Qwen/DashScope only for retrieval, not prediction. |
| Complex phase reasoning | DeepSeek Reasoner only when J2/J3/knockout context justifies the cost. |

## Group Stage Cost Strategy

During group stage, keep one stable Spanish variant first. Add dialect expansion after the system is stable and after the main tournament logic is verified. The architecture goal is not more generations; it is better routing.

Current priority:
1. Correct standings.
2. Correct today/tomorrow fixtures.
3. Correct J2/J3 pressure logic.
4. Cache predictions and narrations so user clicks do not trigger repeated LLM calls.
5. Then expand dialects.

## Agent Feedback Loop

Agent Debate produces four predictions per match:

- Group Analyst.
- Tactical Scout.
- Sentiment Reader.
- Consensus.

The agents do not fine-tune themselves automatically. The learning loop is operational:

1. Save all agent predictions before the match.
2. After the result, evaluate 1X2 hit and exact-score hit.
3. Compare agent-level performance by matchday and group.
4. Adjust prompts, phase-specific weights and routing rules.
5. Keep the deterministic ensemble as the baseline.

Current evaluated sample in the local data is small: four played matches with Agent Debate. Initial results show Group Analyst strongest on J2 pressure logic, but this should be treated as early evidence, not a stable conclusion.

## Risks

- Serverless memory cache is not durable.
- Missing or stale environment variables can silently reduce RAG quality.
- LLMs can hallucinate if the system prompt lacks current fixtures.
- Agent Debate can become expensive if run for every match without guardrails.

## Recommendation

Keep all LLM-derived outputs labeled and reproducible through saved JSON artifacts whenever possible. For critical public views, prefer precomputed text generated from structured input over live free-form calls.
