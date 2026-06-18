# Mundial Predictor 2026 — System Overview

> **Target audience:** AI Architects, recruiters, technical evaluators, and developers joining the project.  
> **Read time:** 10 minutes.  
> **Purpose:** Understand the complete system architecture, data flow, and design decisions in one document.

---

## 1. Executive Summary

**Mundial Predictor 2026** is a probabilistic match prediction system for the FIFA World Cup 2026. It combines three complementary ML models (ELO, Poisson, XGBoost) into a calibrated ensemble that outputs match outcome probabilities (home win / draw / away win). The system updates live during the tournament, incorporating real results to recalibrate predictions for subsequent matches.

**Core promise:** Honesty over hype. Calibrated probabilities + transparent limitations.

| Aspect | Specification |
|---|---|
| Primary model | Ensemble: ELO (22%) + Poisson (58%) + XGBoost (20%) |
| Test performance | RPS 0.1958 on Qatar 2022 (64 matches); walk-forward validated |
| Live pipeline | Updates daily; re-trains models after each matchday |
| Frontend | Next.js 15; Monte Carlo simulator runs in-browser (5k iterations/300ms) |
| LLM cost | Capped: $5/day, $50/month; Ensemble fully functional without LLMs |
| Deployment | Vercel (CDN + serverless); no backend infrastructure needed |

---

## 2. Problem Statement

**Football prediction is hard.**

- Outcome uncertainty: only 3 discrete events (1X2)
- Long-tail distribution: most matches have a clear favorite, but upsets are real
- Data scarcity: only 64 World Cup matches per tournament (vs. 380 Premier League matches/season)
- Hidden factors: injuries, morale, tactical innovation, referee bias (unmeasurable)

**Existing alternatives:**
- Bookmakers: highly calibrated but driven by margin optimization, not forecast accuracy
- TV pundits: entertaining but non-reproducible
- Historical models: accurate for aggregate trends, useless for live decision-making

**This project's approach:** Combine historical statistics (49,765 internationals), domain structure (ELO), and recent data (rolling form) into a single, testable system. Publish limitations honestly.

---

## 3. Target Users

1. **Football fans** — transparent probability display during the tournament
2. **Quantitative traders** — calibrated probabilities for relative-value detection
3. **AI/ML practitioners** — reference implementation of ensemble architecture + temporal validation
4. **Portfolio reviewers** — demonstration of ML ops best practices (data contracts, cost guard, observability)

---

## 4. Functional Scope

### What it does (in-scope)

✅ Live match probabilities (1X2) updated daily  
✅ Tournament simulation (5,000 Monte Carlo trials per scenario)  
✅ Group stage predictions with pressure context  
✅ Knockouts with dynamic bracket resolution  
✅ Model performance transparency (accuracy, calibration, surprises)  
✅ Multi-match narration (optional, AI-generated pre-computed text)  

### What it does NOT do (out-of-scope)

❌ Real-money betting recommendations  
❌ Player performance prediction  
❌ Non-WC tournament prediction (without retraining)  
❌ Live in-match updates (model updates post-match only)  
❌ Squad-level roster optimization  

---

## 5. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│  DATA SOURCES                                                   │
│  ├─ Kaggle: 49,477 internationals (1872–2026)                  │
│  ├─ football-data.org: WC 2026 live results (post-match)       │
│  └─ Custom: WC 2026 fixture + venue metadata                   │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  FEATURE PIPELINE (Python)                                      │
│  ├─ Extract: Load, normalize team names, filter by tournament   │
│  ├─ Enrich: Compute ELO ratings (K by tournament + margin)      │
│  ├─ Features: Build matrix with rolling form, H2H, experience   │
│  └─ Split: Temporal (train < 2018 | test = WC 2022)           │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  MODEL TRAINING & VALIDATION                                    │
│  ├─ XGBoost: Multi-class softmax + isotonic calibration         │
│  ├─ Poisson: Dixon-Robinson bivariate (score distribution)      │
│  ├─ ELO: Deterministic baseline (no training needed)            │
│  └─ Ensemble: Weighted blend (22/58/20) with renormalization   │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  LIVE PREDICTION ENGINE                                         │
│  ├─ Anti-leakage: Strict cutoff (match kickoff - 60s)          │
│  ├─ Ensemble prior: Deterministic, always available            │
│  ├─ Multi-agent enrichment (OPTIONAL): +2 specialist LLM calls │
│  │  └─ Orchestrator routes to max 2 agents by context          │
│  └─ Output: live_predictions.json + group_narratives.json      │
└────────────────────┬────────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────────┐
│  FRONTEND (Next.js + React 19)                                  │
│  ├─ Live Dashboard: match scores, group standings (refreshed 5m)│
│  ├─ Predictor: match probabilities + optional Narrator AI text │
│  ├─ Simulator: 5,000 MC trials per scenario (client-side)       │
│  ├─ Stats: KPI cards, charts, surprises (all client-side)       │
│  └─ Chat: Context-aware Q&A (DeepSeek + RAG)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Data Flow (One Tournament Cycle)

### Step 1: After a matchday completes

```bash
python scripts/live_update.py
```

1. **fetch:** Download WC 2026 results from football-data.org
2. **normalize:** Resolve team names (e.g., "Bosnia & Herzegovina" → canonical form)
3. **retrain:** Recompute ELO ratings incorporating new results, retrain XGBoost
4. **export:** Generate all JSONs (predictions, standings, forms) to `frontend/public/data/`

**Time:** ~90 seconds. Cost: $0 (deterministic model only).

### Step 2: Live predictions with optional agent enrichment

```bash
python scripts/predict_live.py --export [--no-agents]
```

1. **ensemble:** Compute prior probabilities (ELO + Poisson + XGB blend)
2. **agents:** (Optional) Route to max 2 specialists (LLM or deterministic)
   - IntMatch-Analytics-Pro: Tactical context
   - Roster-Data-Scout: Injury/availability
   - Media-Sentiment-Parser: Morale signals
   - Travel-Logistics-Quant: Fatigue/timezone
   - FinOps-Bookmaker-Alpha: Market calibration check
   - FIFA-Regs-Strategist: Bracket/altitude penalty
3. **blend:** Clamp agent deltas to ±12%, renormalize
4. **output:** `live_predictions.json` (group stage + knockouts)

**Time:** 5–30s (depends on agent availability). Cost: $0–$0.15 (LLM agents only if budget permits).

### Step 3: Pre-computed narrations (optional)

```bash
python scripts/precompute_narrations.py
```

Generate AI-written match narrations for all games today (in regional dialects during group stage). Cached in `narrations.json` — zero LLM cost per user.

**Time:** 1–3 min. Cost: $0.02–$0.05 (one DeepSeek call per match).

### Step 4: Deploy

```bash
cd frontend && npx vercel --prod
```

Push updated JSONs and frontend code to production.

---

## 7. Machine Learning Pipeline

### 7.1 Data Sources & Normalization

**Input:**
- 49,765 international match records (1872–2026)
- Team names: historical normalization (West Germany → Germany, Zaire → DR Congo)

**Output:**
- Normalized `results.csv` with `home_team`, `away_team`, `home_score`, `away_score`

### 7.2 ELO Rating System

**Formula:**
```
K_scaled = K(tournament) × log(1 + |goal_diff|) / log(2)
new_rating = old_rating + K_scaled × (actual − expected)
```

**Design choices:**
- K by tournament (WC=60, Euro=55, Friendly=20) to weight importance
- Margin multiplier (log goal difference) rewards dominant wins
- Home advantage: +100 ELO points in expected calculation (non-neutral venues only)

**Initialization:** All teams start at 1,500. Chronological pass since 1872 naturally differentiates.

### 7.3 Feature Engineering

**Features in XGBoost (10):**
- `elo_diff`, `elo_home`, `elo_away`: Pre-match ELO
- `home_goals_scored_avg5`, `away_goals_scored_avg5`: Rolling avg (last 5 games)
- `home_goals_conceded_avg5`, `away_goals_conceded_avg5`: Defense rolling avg
- `h2h_home_win_pct`: All-time head-to-head win rate
- `is_neutral`: 0 if host nation plays at home venue
- `wc_experience_diff`: WC appearance count delta

**No leakage:** All features computed strictly before the match via `shift(1)` on rolling stats.

**Ablation:** `rest_days` feature tested; rejected (RPS improved by only +0.0005, added noise).

### 7.4 Temporal Validation (Critical)

Football data is time-series. Random K-fold creates leakage.

**Temporal split (final model):**
```
Train:       year < 2018    (~41,635 matches)
Calibration: year == 2018   (~929 WC + qual matches)
Test:        WC 2022        (64 matches — never seen in training)
```

**Walk-forward validation (5-fold, more reliable):**
Each fold trains on all data before test year, tests on that year's WC (64 matches):
- 2006, 2010, 2014, 2018, 2022 → 320 predictions total

---

## 8. Model Predictive Core

### 8.1 XGBoost (Multi-class Classifier)

```
multi:softmax (3 classes: home_win=0, draw=1, away_win=2)
├─ Hyperparameters: n_estimators=300, max_depth=4, learning_rate=0.05
├─ Sample weights: tournament_weight (friendlies: 0.20, WC: 1.0)
└─ Calibration: CalibratedClassifierCV with TimeSeriesSplit (3 folds) + sigmoid
```

**Performance on test (Qatar 2022, 64 matches):**
| Metric | Score |
|---|---|
| Accuracy | 48.4% |
| Log-loss | 1.025 |
| RPS | 0.217 |

Baseline (logistic regression on ELO): accuracy 50%, RPS 0.220. **XGB does not consistently beat ELO**, so ensemble weights it at 20%.

### 8.2 Poisson Model (Dixon-Robinson)

Models goal distribution independently per team:
```
λ_home = mean_goals_home × attack_home × defense_away × (1 + home_advantage if not neutral)
λ_away = mean_goals_away × attack_away × defense_home
```

Score matrix: outer product of Poisson(λ_home) ⊗ Poisson(λ_away), capped at 7 goals/side.  
Aggregates to 1X2 by summing diagonal (draws), upper triangle (home), lower triangle (away).

**Advantage:** Independent signal from goal distributions (vs. just outcome).  
**Disadvantage:** Assumes goal independence (slightly underestimates draws).

### 8.3 ELO-Only Baseline

Deterministic:
```
p_home = 1 / (1 + 10^((R_away − R_home − home_adv) / 400))
draw_frac = 0.28 × (1 − |p_home − 0.5| × 1.6), clipped to [0.08, 0.36]
```

No training. Always available. Serves as lower bound.

### 8.4 Ensemble Blend

```
p_final = (0.22 × p_ELO + 0.58 × p_Poisson + 0.20 × p_XGB) / sum_weights
```

**Rationale for weights:**
- **Poisson (58%):** Adds independent score-distribution signal; beats individual models in walk-forward
- **ELO (22%):** Robust multi-tournament anchor; simple, interpretable, never fails
- **XGB (20%):** Captures non-linear patterns, but does not consistently outperform ELO globally

---

## 9. Live Predictions & Calibration

### 9.1 Anti-Leakage Contract

For each pending match:
```python
cutoff = kickoff − 60 seconds
assert cutoff < match_date_time   # enforced
features = compute_from_all_data_until(cutoff)
```

Ensures WC results already played are incorporated into prior, without contaminating current match.

### 9.2 Live Pipeline Execution

```bash
# Register result
python scripts/predict_live.py --add-result "Mexico" "Poland" 0 0 2026-06-11

# Re-predict all pending matches
python scripts/predict_live.py --export
```

**Output:** `data/processed/live_predictions.json` (for analysis) + `frontend/public/data/live_predictions.json` (for UI).

---

## 10. Monte Carlo Simulator

**Backend (Python):**
- Official 2026 bracket: 12 groups → 8 qualified per group → knockout stages
- Group tiebreakers: goal difference, head-to-head, goals scored (FIFA rules)
- Penalty shootouts: weighted by historical penalty conversion (85% baseline)

**Frontend (JavaScript):**
- Runs 5,000 simulations in-browser (~200–300ms on modern hardware)
- Per-team win probabilities per round: Quarterfinals, Semifinals, Final, Champion
- No backend call needed; pre-computed team-pair matchups (1,128 pairs)

---

## 11. Live Updates During Tournament

### Daily Cycle (Jun 11 – Jul 19, 2026)

```bash
# Morning (before any matches)
python scripts/live_update.py                    # fetch, retrain, export
python scripts/predict_live.py --export          # live probs
python scripts/precompute_narrations.py          # daily narrations
cd frontend && npx vercel --prod                 # deploy
```

**Matchday 2 (Jun 18–23) Special Protocol:**
- Run full cycle before first 2 matches
- Run again in afternoon after first 2 results → evening matches see updated pressure/qualification context

**Matchday 3 (simultaneous group matches):**
- Emphasize goal difference and best-third qualification scenarios
- Group narrative previews regenerated with simultaneous-match context

---

## 12. Frontend & User Experience

### 12.1 Core Tabs

| Tab | Purpose | Real-time? |
|---|---|---|
| **En Vivo** | Tournament scoreboard + model verdict per match | ✅ 5min refresh |
| **Predictor** | Match probability picker + Narrator AI | Narrator pre-computed |
| **Grupos** | Group standings, qualification simulations | ✅ 5min refresh |
| **Proyecciones** | Per-team round-by-round win probability | ❌ Refreshes on deploy |
| **Stats** | Top scorers, top matches, surprises (client-side calc) | ✅ 5min refresh |
| **Modelo** | Accuracy by matchday, surprises where model erred | ❌ Refreshes on deploy |
| **Chat IA** | Context-aware Q&A about tournament (DeepSeek + RAG) | ✅ Real-time |

### 12.2 Tech Stack

- **Framework:** Next.js 15 + React 19
- **Styling:** Tailwind CSS + Framer Motion (animations)
- **Charts:** Recharts (bar, line, scatter)
- **State:** React Context (tournament data, dialect, theme)
- **Simulation:** Custom JavaScript Monte Carlo

### 12.3 Dialects & Localization

Regional Spanish dialects during group stage (Bogotá/neutral focus):
- Bogotano (Colombian, project default)
- Paisa (Medellín region)
- Boyaco (Boyacá region)
- Costeño (Caribbean coast)
- English

Dialects auto-activate for knockout stage (all 5).

---

## 13. Narrator AI (Pre-Computed)

**Daily pre-computation:**

```bash
python scripts/precompute_narrations.py
```

Generates one DeepSeek call per match (5 dialects during knockouts; Bogotá-only during group) → cached in `narrations.json`.

**Zero LLM cost per user:** Frontend loads static JSON at page load, passes as prop to match predictor.

**Fallback:** Narrator endpoint (`/api/narrator`) serves static keys. If missing (knockout match not yet pre-computed), falls back to live DeepSeek call.

**Context injected:**
- Stadium name, historical matchups, confederation
- Current group standings, qualification pressure
- Model probabilities for context framing

---

## 14. AI Chat API (`/api/chat`)

### Three Protection Layers

1. **Topic filter** (zero cost): Keyword regex for football terms. Non-football questions get canned reply.
2. **Response cache** (zero cost): Module-level SHA-256 key, TTL 2h, max 400 entries. Warm instance = instant reply.
3. **Rate limit** (zero cost): 20 requests/hour per IP; HTTP 429 if exceeded.

### RAG Pipeline (Optional)

If `DASHSCOPE_API_KEY` set:
- Embed query with Qwen3 text-embedding-v3 (512 dims)
- Cosine similarity search in `rag_index.json`
- Inject top-5 chunks into system prompt

### Tournament Context Injection (Always)

Direct system prompt injection (no RAG needed):
- Today's fixtures (UTC date filter on `group_matches.json`)
- Group standings (`group_standings.json`)
- **Result:** Chat always knows what's playing today, current table

---

## 15. Multi-Agent System (OPTIONAL LAYER)

**Critical clarification:** Multi-agent enrichment is **capped, opt-in, never required for core predictions.**

### 15.1 Architecture

```
Orchestrator (single entry point)
  │
  ├─→ MatchContext (match data + group context)
  │
  ├─ Route (determines which agents can help)
  │
  └─→ Agent 1 + Agent 2 (max 2, in parallel)
       ├─ Each produces delta_P (adjustment to home/draw/away)
       └─ Confidence score (0..1)
       
  Blend: weighted sum of deltas, clamped to ±12% total shift
  Renormalize: final probs sum to 1.0
```

### 15.2 Agents (7 Specialists)

| Agent | Type | Role | Trigger |
|---|---|---|---|
| **IntMatch-Analytics-Pro** | LLM (Haiku) | Tactical matchup, discipline, climate | Group stage; high pressure scenarios |
| **Roster-Data-Scout** | LLM (Sonnet) | Injury data, squad depth, xG/xA | If injuries provided |
| **Media-Sentiment-Parser** | LLM (Sonnet) | Press sentiment, morale, momentum | Group stage MD2+ |
| **Travel-Logistics-Quant** | Hybrid | Fatigue, timezone, altitude | International travel > 2h |
| **FinOps-Bookmaker-Alpha** | Deterministic | Market probability calibration | If odds provided; removes overround |
| **FIFA-Regs-Strategist** | Deterministic | Bracket math, altitude penalty | Knockout stage; altitude > 2000m |
| **GroupScenario-Reasoner** | LLM (Sonnet) | Qualification pressure, best-3rd | MD2 and MD3 (group stage only) |

### 15.3 Budget Guard

**Hard limits (configs/budget.yaml):**
- Daily: $5 USD
- Monthly: $50 USD
- Per run: 100 LLM calls

**Behavior:** If budget exceeded, agents gracefully skip (delta = 0). **Ensemble still predicts with full accuracy.**

### 15.4 Why Optional?

- **Core model works without agents:** Ensemble RPS = 0.1958 (vs. 0.220 baseline)
- **Agent backtesting impossible:** Can't validate historical delta_P on matches we can't rewind
- **Cost efficiency:** $2–$5/day for marginal (unmeasured) improvement
- **Transparency:** Users see prior ensemble probability always; agent deltas are labeled "enrichment"

---

## 16. Cost Control & Observability

### 16.1 CostGuard

`src/cost_guard.py`: Singleton that enforces budget before any LLM call.

```python
guard = get_guard()  # reads configs/budget.yaml
guard.check_and_record(model="deepseek-chat", n_tokens=1200, agent_name="IntMatch")
# → raises BudgetExceeded if limit reached
```

**Fallback:** Orchestrator catches `BudgetExceeded`, disables LLM agents, uses deterministic ensemble.

### 16.2 Ledgers

**`logs/llm_costs.jsonl`:** One entry per LLM call.
```json
{"ts": "2026-06-17T14:32:00Z", "model": "deepseek-chat", "tokens": 1200, "cost_usd": 0.00017, "agent": "IntMatch"}
```

**`logs/pipeline_runs.jsonl`:** One entry per pipeline/live run.
```json
{"ts": "...", "run_type": "live_update", "duration_s": 87, "status": "ok", "metrics": {...}}
```

---

## 17. Testing & Validation

**Test suite:** 112+ pytest tests across:
- Feature engineering (no leakage, value ranges)
- Model training (temporal split, calibration)
- Agent integration (delta normalization, budget guards)
- Data contracts (schema validation)
- Simulator (deterministic seed, bracket resolution)
- Live prediction (anti-leakage assertions)

**Run all tests:**
```bash
pytest -v
```

**Data contracts:** Every pipeline run validates input/output schemas (`contracts/data_contracts.md`). Silent failures are not acceptable.

---

## 18. Limitations

1. **No real-time squad data:** Model reflects historical trends. Injuries, suspensions not captured unless manually injected.
2. **Calibration drift:** Fitted on WC 2018 data. Football evolves; recalibration recommended after major tournaments.
3. **Draws are hard:** ~27% of matches are draws globally. No tested model substantially improves draw RPS.
4. **Small test set:** WC = only 64 matches. Walk-forward n=320 more reliable, but individual fold variance is high.
5. **No momentum beyond form:** Model updates ELO match-by-match. Doesn't capture within-tournament psychological momentum (WC rookies vs. veterans).
6. **Fixture uncertainty:** Knockout opponents unknown until group stage resolves. Placeholder codes (W101, 1A) until bracket closes.

---

## 19. Responsible Use Statement

- **Probabilities are forecasts, not guarantees.** 70% home win does not mean the team will win.
- **Not a betting tool.** Expected value against bookmaker lines is not guaranteed.
- **Historical data reflects outcomes.** Does not capture tactical innovation, manager changes, or referee bias.
- **Uncertainty is real.** Championship probabilities are simulations, highly sensitive to group-stage outcomes.
- **Transparent limitations.** See Section 18.

---

## 20. Roadmap (Future Phases)

### Phase 0 ✅ (2026-06-12)
- Core models trained and validated
- Live update pipeline operational
- Frontend deployed

### Phase 1 (2026-06-17)
- Multi-agent system integrated
- Pre-computed narrations live
- Chat IA deployed

### Phase 2 (2026-06-25)
- Group stage narrative previews
- Model accuracy dashboard
- Stats tab live

### Phase 3 (Knockout stage, 2026-07-01)
- Full agent activation (5 dialects)
- Fixture resolution as bracket closes
- Finalist predictions

### Phase 4 (Post-WC, 2026-07-20)
- Final analysis + retrospective calibration
- Walk-forward backtesting for next WC
- Open-source documentation

---

## 21. Getting Started

### For Developers

```bash
# Setup
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt

# Training
python scripts/run_pipeline.py

# Testing
pytest -v

# Frontend
cd frontend && npm install && npm run dev
```

See `CLAUDE.md` for detailed commands and environment setup.

### For Evaluators

1. Read this file (10 min)
2. Skim `model_card.md` for metrics (5 min)
3. Review `methodology.md` for validation strategy (10 min)
4. Inspect `tests/` for completeness (5 min)

**Total:** 30 minutes to full technical understanding.

---

## Appendix: Key Files Reference

| File | Purpose |
|---|---|
| `src/extractor.py` | Data loading, normalization, filtering |
| `src/features.py` | ELO, feature engineering |
| `src/model.py` | XGBoost training, calibration, RPS metric |
| `src/poisson_model.py` | Dixon-Robinson Poisson |
| `src/ensemble.py` | Three-model blend |
| `src/agents/` | Multi-agent system (orchestrator + 7 specialists) |
| `src/cost_guard.py` | LLM budget enforcement |
| `src/pipeline_logger.py` | Run observability (JSONL ledgers) |
| `src/simulator.py` | Monte Carlo tournament simulation |
| `scripts/live_update.py` | Orchestrator: fetch → retrain → export |
| `scripts/predict_live.py` | Live predictions with agent enrichment |
| `scripts/precompute_narrations.py` | Daily narration generation (DeepSeek) |
| `frontend/src/app/api/chat/` | AI chat endpoint |
| `frontend/src/app/api/narrator/` | Pre-computed narrations server |
| `frontend/src/lib/simulator.ts` | Client-side Monte Carlo |
| `contracts/data_contracts.md` | Input/output schema guarantees |
| `contracts/module_contracts.md` | Public API contracts |

---

**Last updated:** 2026-06-17  
**Prepared by:** AI Solution Architect review team
