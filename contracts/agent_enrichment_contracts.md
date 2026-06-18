# Agent Enrichment Contracts — Mundial Predictor 2026

> These are OPTIONAL, NICE-TO-HAVE interfaces. The system works perfectly without them.  
> All agents degrade gracefully: if budget exceeded, API unavailable, or context missing → delta=0 (no adjustment to prior).

---

## Critical Disclaimer

**The Ensemble (ELO + Poisson + XGBoost) is the core predictive model.**

**The multi-agent system is an OPTIONAL enrichment layer** that:
- Attempts to capture tactical context, roster changes, market signals
- Is cost-capped (configurable daily/monthly limits)
- Has unmeasured impact (backtest impossible on historical data)
- Can be disabled entirely without degrading core predictions
- Fails gracefully: if budget or API unavailable, Ensemble still predicts with full accuracy

Users see the Ensemble prior **always**. Agent deltas are labeled as optional "enrichment."

---

## Budget Guardrails (Soft Caps)

```yaml
# configs/budget.yaml
llm:
  daily_limit_usd: 5.00           # reset at midnight UTC
  monthly_limit_usd: 50.00
  max_calls_per_run: 100          # per pipeline run (live_update.py, predict_live.py)
  cost_per_1k_tokens:
    deepseek-chat: 0.00014        # primary
    deepseek-reasoner: 0.00055    # complex tasks only
    claude-haiku-4-5-20251001: 0.00025    # fallback
    claude-sonnet-4-6: 0.003      # fallback
```

**Behavior:**
- `CostGuard.check_and_record()` verifies limits BEFORE any LLM call
- If limit exceeded: raises `BudgetExceeded`
- Orchestrator catches exception: disables LLM agents, uses deterministic agents + Ensemble
- **Result:** Ensemble prior still delivered; no prediction failure

---

## `src/cost_guard.py` — Budget Enforcement

### `class CostGuard`

#### `check_and_record(model: str, n_tokens: int, agent_name: str = "", match: str = "") → None`

**Input:**
- `model`: model ID (e.g., "deepseek-chat")
- `n_tokens`: estimated token count
- `agent_name`: which agent is calling (for logging)
- `match`: which match (for logging)

**Behavior:**
- Reads `configs/budget.yaml` at process start
- Reads spend ledger from `logs/llm_costs.jsonl` (append-only)
- Computes: daily spend, monthly spend, calls in current run
- Verifies all three limits

**Raises:**
- `BudgetExceeded`: if any limit would be breached
- Records entry to `logs/llm_costs.jsonl` ONLY if check passes

**Guarantee:**
- Idempotent: multiple calls with same query don't double-count
- Ledger is JSONL (one entry per call): `{"ts": "...", "model": "...", "tokens": ..., "cost_usd": ...}`

#### `run_calls_remaining() → int`

**Output:**
- How many LLM calls remain in this run (before hitting `max_calls_per_run`)

---

## `src/agents/base.py` — Contracts for All Agents

### `class MatchContext`

**Input payload for any agent analysis:**

```python
@dataclass
class MatchContext:
    team_home: str
    team_away: str
    p_home: float               # prior from Ensemble
    p_draw: float               # prior from Ensemble
    p_away: float               # prior from Ensemble
    elo_home: float = 1500.0
    elo_away: float = 1500.0
    is_neutral: bool = True
    venue_city: Optional[str] = None
    venue_altitude_m: int = 0
    round_label: Optional[str] = None     # "Group A MD1", "QF", etc.
    injuries: list = None       # ["Mbappé (knee)", ...]
    home_odds: Optional[float] = None
    draw_odds: Optional[float] = None
    away_odds: Optional[float] = None
    query_hint: Optional[str] = None
    # Group stage context
    group_name: Optional[str] = None
    group_points_home: Optional[int] = None
    group_points_away: Optional[int] = None
    games_played_home: int = 0
    games_played_away: int = 0
    days_rest_home: Optional[int] = None
    days_rest_away: Optional[int] = None
    prev_city_home: Optional[str] = None
    prev_city_away: Optional[str] = None
    group_standings: Optional[str] = None
    simultaneous_group_matches: Optional[str] = None
    third_place_context: Optional[str] = None
    matchday: Optional[int] = None
```

**Guarantee:**
- `p_home + p_draw + p_away = 1.0` (Ensemble prior)
- All fields optional except team names and prior probs
- Agent must handle missing context gracefully (return delta=0)

---

### `class AgentResult`

**Output contract for every agent:**

```python
@dataclass
class AgentResult:
    agent_name: str
    delta_home: float = 0.0    # adjustment to P(home_win), ∈ [-0.12, +0.12]
    delta_draw: float = 0.0    # adjustment to P(draw), ∈ [-0.12, +0.12]
    delta_away: float = 0.0    # adjustment to P(away_win), ∈ [-0.12, +0.12]
    confidence: float = 0.5    # how confident in this adjustment, ∈ [0, 1]
    notes: str = ""            # human-readable rationale
    raw_response: Optional[str] = None
```

**Guarantee:**
- Deltas sum to ~0 (redistribution, not creation)
- Confidence in [0, 1]
- Orchestrator clamps total delta to ±12% per match
- `is_neutral_delta(tol=1e-6)` checks if adjustment is zero

---

### `class BaseAgent` (ABC)

#### `analyze(ctx: MatchContext) → AgentResult`

**Contract:**
- Input: MatchContext with available context
- Output: AgentResult with delta_P and confidence
- Never raises exception (catch and return delta=0 via safe_analyze())

#### `safe_analyze(ctx: MatchContext) → AgentResult`

**Wrapper that guarantees no exceptions:**
- Calls `analyze(ctx)`
- If exception: logs warning, returns `AgentResult(delta=0, notes="error: ...")`
- Normalizes deltas to sum=0

---

## `src/agents/orchestrator.py` — Routing & Blending

### `class OrchestratorOutput`

```python
@dataclass
class OrchestratorOutput:
    team_home: str
    team_away: str
    prior: dict              # {"home": float, "draw": float, "away": float}
    adjusted: dict           # same keys, post-agent adjustments
    agents_called: list[str] # which agents were invoked
    routing_decision: dict   # metadata on why
    agent_results: list[AgentResult] = field(default_factory=list)
```

---

### `Orchestrator.predict(ctx: MatchContext) → OrchestratorOutput`

**Contract:**

1. **Always returns prior:** The Ensemble (ELO + Poisson + XGB) prior is computed and returned
2. **Optional agent routing:**
   - If budget available: select 0–2 agents based on context
   - If budget exhausted: skip to step 4
3. **Blend agent deltas:**
   - Each agent produces delta_P (adjustment)
   - Weight deltas by agent weight × confidence
   - Clamp total delta to ±12% of prior probabilities
   - Renormalize to sum=1.0
4. **Output:** OrchestratorOutput with prior and adjusted probs

**Guarantee:**
- No exceptions: all agents use `safe_analyze()`
- Adjusted probs always sum to 1.0
- Prior always valid and readable by caller
- Agent failures don't break prediction

---

## Agent Specifications (7 Specialists)

### Deterministic Agents (Always Work, No API Key)

#### **1. FinOps-Market-Calibration-Validator**

**Role:** Compare bookmaker odds with Ensemble prior.

**Input:**
- `ctx.home_odds`, `ctx.draw_odds`, `ctx.away_odds` (decimal odds)
- `ctx.p_home`, `ctx.p_draw`, `ctx.p_away` (Ensemble prior)

**Output:**
- `delta_P`: How much market consensus diverges from model (max ±15%)
- `confidence`: Based on overround margin and edge magnitude

**Guarantee:**
- Deterministic (no LLM)
- Returns delta=0 if odds not provided
- No betting recommendations; calibration check only

---

#### **2. FIFA-Regs-Strategist**

**Role:** Bracket math, altitude penalty, qualification rules.

**Input:**
- `ctx.round_label` (R16, QF, etc.)
- `ctx.venue_altitude_m`
- `ctx.group_name` (if applicable)

**Output:**
- `delta_P`: Altitude penalty (-2% to -8% for teams below certain sea-level thresholds)
- Bracket resolution context

**Guarantee:**
- Deterministic (no LLM)
- Returns delta=0 if not applicable
- Penalty based on scientific studies of high-altitude sports performance

---

### LLM Agents (Cost-Gated, Graceful Fallback)

#### **3. IntMatch-Analytics-Pro** (Haiku)

**Role:** Tactical matchup, home advantage, discipline, climate.

**Context triggers:**
- Group stage (especially MD2 with pressure)
- High-profile matchups
- Tactical style divergence

**Cost:** ~0.3k tokens/call → $0.00004

---

#### **4. Roster-Data-Scout** (Sonnet)

**Role:** Injury data, squad depth, expected goals, player WAR.

**Context triggers:**
- Injuries provided in context
- Squad depth variation between teams
- Key player absences

**Cost:** ~0.5k tokens/call → $0.0015

---

#### **5. Media-Sentiment-Parser** (Sonnet)

**Role:** Press sentiment, morale, momentum narratives.

**Context triggers:**
- MD2 and MD3 (high-stakes group matches)
- Narratives about team morale/scandal

**Cost:** ~0.5k tokens/call → $0.0015

---

#### **6. Travel-Logistics-Quant** (Haiku + Deterministic Fallback)

**Role:** Fatigue, timezone drift, travel distance.

**Context triggers:**
- International travel > 2 hours
- Altitude > 2000m
- Timezone shift > 5 hours

**Cost:** ~0.2k tokens/call → $0.00003 (if LLM) or $0 (deterministic fallback)

---

#### **7. GroupScenario-Reasoner** (Sonnet)

**Role:** Qualification pressure, best-3rd scenarios, simultaneous match effects.

**Context triggers:**
- MD2 and MD3 only (group stage)
- When standings are dynamic (points matter)

**Cost:** ~0.6k tokens/call → $0.0018

---

## Graceful Degradation Scenarios

### Scenario 1: Cost Budget Exhausted

```
predict_live.py --export (after 50 LLM calls consumed)
  ↓
Orchestrator.predict(ctx) called for match 51
  ↓
CostGuard.check_and_record() → BudgetExceeded
  ↓
Orchestrator catches exception
  ↓
Skips LLM agents (IntMatch, Roster, Media, GroupScenario)
  ↓
Uses only deterministic agents (FinOps, FIFA-Regs, Travel-deterministic-fallback)
  ↓
Ensemble prior still outputs
  ↓
Match prediction: FULL ACCURACY
```

### Scenario 2: API Key Missing

```
predict_live.py --export (DEEPSEEK_API_KEY not set, ANTHROPIC_API_KEY not set)
  ↓
Orchestrator.predict(ctx)
  ↓
LLM agents try to initialize client
  ↓
RuntimeError: "DEEPSEEK_API_KEY not configured"
  ↓
Caught by safe_analyze() → returns delta=0
  ↓
Orchestrator sums deltas: only deterministic agents contribute
  ↓
Ensemble prior still outputs
  ↓
Match prediction: FULL ACCURACY
```

### Scenario 3: Missing Context

```
predict_live.py --export (no injuries provided, no odds provided, no group standings)
  ↓
Orchestrator.predict(ctx) with sparse MatchContext
  ↓
Agents check context; no relevant data → return delta=0
  ↓
Orchestrator output = prior only
  ↓
Match prediction: FULL ACCURACY
```

---

## Testing Guarantees

Agent enrichment is **not backtested** (cannot validate delta_P on historical matches we can't rewind). Instead:

1. **Unit tests** (all agents): Verify input → output contract
2. **Integration tests:** Orchestrator routing, delta blending, clamping
3. **Cost guard tests:** Budget enforcement, ledger correctness
4. **Graceful failure tests:** Missing API keys, missing context, budget exceeded

```bash
pytest tests/test_agents.py tests/test_cost_guard.py -v
```

---

## Cost Transparency

**Expected monthly spend (group stage, 48 matches):**

| Scenario | Calls/Day | Cost/Day | Cost/Month |
|---|---|---|---|
| Ensemble only | 0 | $0 | $0 |
| +2 LLM agents per match (group) | 96 | $0.05 | $1.50 |
| +all agents, peak pressure (MD2) | 192 | $0.10 | $3.00 |
| Full multi-agent pipeline | 300+ | $2–$5 | $50+ (hits limit) |

**Budget configured in `configs/budget.yaml`; can be adjusted per deployment.**

---

## Operational Best Practices

### For Deployers

1. Set `DEEPSEEK_API_KEY` if you want LLM agents (cheapest)
2. Set `ANTHROPIC_API_KEY` as fallback if DeepSeek unavailable
3. Monitor `logs/llm_costs.jsonl` daily for spend tracking
4. Adjust daily/monthly limits in `configs/budget.yaml` as needed
5. Run `python scripts/predict_live.py --export --no-agents` to disable all LLM agents

### For Researchers

- **Do NOT backtest agent impact:** You'll get false positives (lookahead bias)
- **Accept the risk:** Agents improve context-awareness but impact is unmeasured
- **Disable if skeptical:** Run Ensemble-only (`--no-agents`) and compare user feedback
- **Contribute:** If you have new specialist agents, follow the `BaseAgent` contract

---

**Updated:** 2026-06-17  
**Status:** Optional enrichment layer; Ensemble is core and always works
