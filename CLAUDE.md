# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mundial Predictor 2026** is an end-to-end ML pipeline for predicting FIFA World Cup results using XGBoost with custom ELO ratings, feature engineering, Monte Carlo tournament simulation, live match tracking, and an AI chat assistant.

**Key characteristics:**
- Python backend: data extraction → ELO calculation → feature engineering → XGBoost training/evaluation
- Next.js frontend: live tournament tracking, match predictor, Monte Carlo projections, multi-dialect (bogotano/paisa/boyaco/costeño/en)
- Live update pipeline: fetches WC 2026 results from football-data.org → updates CSV → retrains model automatically
- Client-side Monte Carlo simulator (runs in browser on pre-calculated team pairs)
- Temporal split strategy (test = Qatar 2022 to avoid leakage in time-series data)
- **Narrator AI** — pre-computed match narrations and group previews (DeepSeek, run once/twice per day depending on matchday) stored in `narrations.json` and `group_narratives.json`; zero LLM calls per user for cached content, Bogotá/neutral Spanish during group-stage stabilization, group standings context from MD2 onward
- AI chat assistant (DeepSeek + RAG with DashScope embeddings) with topic filter, response cache, rate limiting, and live tournament context injection
- Multi-agent system (Orchestrator + 6 specialists) that enrich predictions with contextual analysis when API budget allows
- 141 passed, 1 skipped pytest tests covering extraction, features, model training, agents, simulation, integrity, and live prediction

---

## Documentation Guide

This repository includes supporting documents organized by purpose. **Consult them when**:

### Operational & Architecture (docs/)
- **`docs/runbook.md`** — **Daily WC 2026 operations.** Complete cycle, J2/J3 double-run protocols, verification checklist, emergency fallback. Start here if you're deploying after a matchday.
- **`docs/architecture.md`** — **System thesis:** 4-layer design (Statistical Benchmark → Tournament Context → Cached Narratives → Agent Debate & Evaluation). Clarifies which layer produces which claim (ML vs agents vs simulator vs narrator).
- **`docs/finops.md`** — **AI cost strategy & budget tracking.** Current spend snapshot, cost-per-match breakdown (Agent Debate ~0.08–0.10 USD, Narrator ~0.016 USD, Specialists ~0.01–0.02 USD), projections through knockout, model use boundaries.
- **`docs/ml-validation.md`** — Model validation approach and performance benchmarks.

### Project & Model Design
- **`proyecto.md`** — Project definition, deliverables (E1–E5), acceptance criteria. Essential for WC 2026 window priorities (Jun 11 – Jul 19, 2026).
- **`model_card.md`** — Model performance, walk-forward validation results, ensemble weights (22% ELO + 58% Poisson + 20% XGB), feature ablation.
- **`guia.md`** — Technical roadmap (Phases 0–6) and design decisions (D1–D6).
- **`methodology.md`** — Model limitations and responsible-use statement.

### Implementation Reference
- **`contracts/`** — Data schemas and contracts (prevent silent failures). `data_contracts.md` specifies `results.csv`, features, and exported JSONs format.
- **`agent/*.md`** — Each specialist agent (e.g., `intmatch_analytics_pro.md`) documents role, input context, output (delta_P adjustment), and cost profile.
- **`README.md`** — Quick-start for new developers; external marketing.

---

## During WC 2026 Operations (Jun 11 – Jul 19, 2026)

**See `docs/runbook.md` for daily protocols.** The tournament has three phases with distinct workflows:

### Matchday Cycles (J1, J2, J3)
Run **after each group-stage matchday** to sync predictions and narratives with real results:

```bash
python scripts/live_update.py                # Fetch results, retrain model
python scripts/predict_live.py --export      # Update probabilities with live ELO cutoff
python scripts/precompute_narrations.py      # Regenerate match + group narratives
cd frontend && npx vercel --prod             # Deploy
```

### J2 Double-Run Protocol
Matchday 2 (Jun 18–23) has afternoon and evening blocks in the same day. **Run twice:**
1. **Before afternoon matches:** Full cycle with morning predictions
2. **After afternoon results:** Re-run `predict_live.py --export` + `precompute_narrations.py` so evening matches see updated pressure and qualification paths

### J3 Simultaneous Matches
Matchday 3 (Jun 24) has group matches kicking off simultaneously. Narratives must emphasize:
- Direct qualification scenarios (not assumed sequential results)
- Goal difference and best-third qualification pressure
- Scenarios and probabilities, not deterministic claims

### Cost & Agent Debate
- **Group stage:** Narrator in Bogotá/neutral Spanish only (budget stability)
- **Knockout stage:** All 5 dialects auto-activated
- **Agent Debate:** Reserve for high-context matches; costs 0.08–0.10 USD per match (5–6× more than narration)

See `docs/finops.md` for current spend snapshot and projections.

---

## Development Commands

### Setup

```bash
# Python environment
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
cd ..
```

### Pipeline & Model Training

```bash
# Run full pipeline: raw data → ELO → features → model training → metrics
python scripts/run_pipeline.py

# Export pre-computed data for frontend (JSONs with model predictions)
python scripts/export_frontend_data.py

# Live predictions with anti-leakage (cutoff = kickoff - 60s)
python scripts/predict_live.py            # pending matches only
python scripts/predict_live.py --all      # all matches (including played)
python scripts/predict_live.py --export   # also write to frontend/public/data/
python scripts/predict_live.py --add-result HOME AWAY HS AS DATE  # record a result

# Feature ablation: test whether rest-days improve RPS before adding to FEATURE_COLS
python scripts/ablation_features.py

# (Optional) Enrich goalscorer stats
python scripts/enrich_goalscorers.py
```

### Live Update (WC 2026 — use after each matchday)

```bash
# Full cycle: fetch results → retrain → export JSONs (runs ~90s)
python scripts/live_update.py

# Preview what would be fetched without writing anything
python scripts/live_update.py --dry-run

# Force retrain even if no new matches
python scripts/live_update.py --force

# Only fetch and update results.csv (skip retrain)
python scripts/update_wc_results.py --dry-run
```

### Daily Narrations & Group Previews (run after live_update + predict_live)

```bash
# Generate narrations for TODAY's matches × dialects → frontend/public/data/narrations.json
# Group stage: Bogotá/neutral Spanish only while the flow is stable.
# Knockout: all 5 dialects auto (~$0.015/run).
python scripts/precompute_narrations.py

# Extend window to include tomorrow's matches (default is today only)
python scripts/precompute_narrations.py --days 1

# Recompute only group narrative previews → frontend/public/data/group_narratives.json (today only)
python scripts/precompute_narrations.py --groups-only
```

Script always force-regenerates today's matches and group previews so standings, pressure, and context stay fresh. It only generates missing match keys for future days unless the key belongs to today's window.

Group previews must analyze each team individually, not only the group as a whole. The payload includes standings, match schedule, local venue, live predictions, prior group results, and deterministic `team_profiles` with:
- current points and goal difference
- previous result and opponent
- estimated strength of the previous opponent using model probabilities
- result quality (`muy alta`, `positiva`, `normal`, `preocupante`, or no evidence)
- likely mood, pressure, dependency, next opponent, and next match probability

J2/MD2 has a double-run protocol: run the full cycle before the first match window, then run it again after the first two results are in so evening predictions and narratives reflect real qualification pressure. J3/MD3 focuses on simultaneous group matches and best-third qualification scenarios.

Encoding rule: JSON files under `frontend/public/data/` must remain UTF-8. Do not rewrite generated JSON with PowerShell `Get-Content | Set-Content`; use Python scripts or `Path.write_text(..., encoding="utf-8")`. Watch for mojibake markers such as `MÃ©xico`, `arrancÃ³`, `Â`, `â€`, or `ðŸ`.

Full deploy cycle:
```bash
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py
cd frontend && npx vercel --prod
```

### Agent Debate System (logic-based predictions, run after the cycle above)

```bash
# Run the 3-agent debate for specific matches (HOME AWAY pairs)
# Captures 4 predictions per match: Group Analyst, Tactical Scout, Sentiment Reader, + Consensus
# Accumulates into data/processed/agent_debate_results.json — idempotent, skips matches
# already debated unless --force
python scripts/run_agent_debate.py "Mexico" "South Korea" "Scotland" "Morocco"

# Re-run a specific match even if already debated (e.g. after a prompt change)
python scripts/run_agent_debate.py --force "Mexico" "South Korea"

# Publish results to the frontend (also exports teams/predictions/etc as usual)
python scripts/export_frontend_data.py
```

**Output format:** Each match now includes 4 structured predictions:
- `group_analyst`: Group classification context prediction
- `tactical_scout`: Tactical/matchup prediction
- `sentiment_reader`: Psychological/momentum-based prediction
- `consensus`: Blended ranking from all 3 agentes

Forward-only by design: the debate only runs for matches you explicitly pass on the CLI (typically upcoming ones). There is no retroactive backfill of already-played matches — accuracy tracking in the "Modelo" tab only reflects matches debated *and* played after the debate ran.

### Testing

```bash
# Run all tests
pytest

# Run tests for a specific module
pytest tests/test_model.py
pytest tests/test_features.py
pytest tests/test_simulator.py
pytest tests/test_extractor.py
pytest tests/test_agents.py
pytest tests/test_cost_guard.py
pytest tests/test_integrity.py
pytest tests/test_poisson.py
pytest tests/test_predict_live.py
pytest tests/test_simulator_parity.py

# Verbose with output
pytest -v

# Run a single test
pytest tests/test_model.py::test_temporal_split_no_leakage

# Test count: 112+ tests across core pipeline, agents, cost guard, and integrity checks
```

### Development Servers

```bash
# Streamlit demo app (local, shows model output)
streamlit run src/app.py

# Next.js frontend dev server (http://localhost:3000)
cd frontend
npm run dev
```

### Build

```bash
# Build Next.js for production
cd frontend
npm run build
npm start
```

### Linting

```bash
cd frontend
npm run lint
```

---

## Architecture

**See `docs/architecture.md` for the complete thesis.** The system has 4 distinct layers, each producing different claims:

| Layer | Purpose | Produces | Source |
|-------|---------|----------|--------|
| **Layer 1: Statistical Benchmark** | ML predictions without LLM calls | `live_predictions.json` (1X2 probabilities) | XGBoost + ELO + Poisson ensemble |
| **Layer 2: Tournament Context** | Current standings, pressure, qualification paths | `group_standings.json`, `group_matches.json` with scores | Real match results + fixture logic |
| **Layer 3: Cached Narratives** | Explanations and storytelling (pre-computed) | `narrations.json`, `group_narratives.json` | DeepSeek (1 call/match, cached) |
| **Layer 4: Agent Debate** | Logic-based predictions with reasoning | `agent_debate_results.json` (4 predictions: 3 agents + consensus) | DeepSeek Reasoner (9 calls/match, eval after) |

**Boundary principle:** Frontend must make clear which layer produced each claim. Don't mix agent opinions with model probabilities; don't invent narratives when LLM budget fails.

### Data Pipeline

```
data/raw/results.csv  (49k+ internationals, WC 2026 fixture pre-loaded with NA scores)
    ↓ [load_results + normalize team names]
    ↓ [filter_world_cups]
    ↓ [add_outcome: map scores to home_win/draw/away_win]
data/processed/wc_clean.csv
    ↓ [compute_elo_ratings: chronological ELO update]
data/processed/elo_current.json
    ↓ [build_feature_matrix: add H2H, form, experience]
data/processed/features.parquet
    ↓ [temporal_split: train < 2018 | calib = 2018 | test = WC 2022]
    ↓ [train XGBoost + CalibratedClassifierCV]   → models/xgb_calibrated.pkl
    ↓ [fit PoissonModel on tournament data]       → models/poisson_model.pkl
    ↓ [EnsembleModel: ELO 22% + Poisson 58% + XGB 20%]
models/{xgb_calibrated, xgb_v1, poisson_model, ensemble}.pkl
```

**Key files:**
- `src/extractor.py`: Data loading, World Cup filtering, outcome mapping, team name normalization
- `src/features.py`: ELO (K by tournament + margin multiplier + home advantage), rolling form, H2H, WC experience, tournament_weight
- `src/model.py`: XGBoost + TimeSeriesSplit calibration, temporal 3-way split (train/calib/test), RPS metric
- `src/poisson_model.py`: Bivariate Poisson (attack/defense strengths), scoreline matrix, top-5 scorelines, 1X2 aggregation
- `src/ensemble.py`: `EnsembleModel` blends ELO + Poisson + XGB with configurable weights; falls back to ELO+Poisson if XGB unavailable
- `src/simulator.py`: Monte Carlo simulation (official 2026 bracket, host home advantage)
- `src/pipeline_logger.py`: JSONL observability — appends one entry per run to `logs/pipeline_runs.jsonl` via `run_context()`
- `src/cost_guard.py`: `CostGuard` reads `configs/budget.yaml`, tracks LLM spend in `logs/llm_costs.jsonl`, raises `BudgetExceeded` to trigger deterministic fallback
- `src/agents/`: Multi-agent system — Orchestrator routes to max 2 specialists, each produces delta_P adjustments

### Live Update Pipeline

`scripts/update_wc_results.py` fetches finished WC 2026 matches from football-data.org and fills in the NA scores in `results.csv`. The CSV has the full WC 2026 fixture pre-loaded — only the `home_score`/`away_score` columns are NA until matches are played.

`scripts/live_update.py` orchestrates the full cycle:
1. `update_wc_results.py` — fills NA scores for finished matches
2. `run_pipeline.py` — recomputes ELO ratings incorporating new results, retrains XGBoost
3. `export_frontend_data.py` — regenerates all JSON files for the frontend

Exit codes from `update_wc_results.py`: `0` = no new matches, `2` = matches updated, `1` = error. `live_update.py` only re-runs the pipeline if exit code is `2` (or `--force`).

**Name normalization:** football-data.org uses different team names. `FD_NAME_MAP` in `update_wc_results.py` handles all known variants (e.g., `"Bosnia-Herzegovina"` → `"Bosnia and Herzegovina"`, `"Korea Republic"` → `"South Korea"`).

### Feature Engineering

**Features used in XGBoost:**
- `elo_diff`, `elo_home`, `elo_away`: ELO ratings (pre-match)
- `home_goals_scored_avg5`, `away_goals_scored_avg5`: Average goals scored in last 5 games
- `home_goals_conceded_avg5`, `away_goals_conceded_avg5`: Average goals conceded in last 5 games
- `h2h_home_win_pct`: Head-to-head home win percentage
- `is_neutral`: Binary flag for neutral venue
- `wc_experience_diff`: Difference in World Cup appearances

**Label mapping:**
```python
{"home_win": 0, "draw": 1, "away_win": 2}
```

### Model Training

- **Train/test split:** 3-way temporal: train < 2018 | calib = 2018 | test = WC 2022 (64 games)
- **Training data:** All 49k+ internationals (use_all_matches=True); WC games weighted 1.0, friendlies 0.20
- **Base model:** XGBoost multi-class softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)
- **Ensemble:** `EnsembleModel` (default weights: ELO 22% + Poisson 58% + XGB 20%, per walk-forward validation 2026-06-17) — Poisson provides robust goal-distribution signal independent of ELO; XGB captures non-linear patterns but does not consistently improve global RPS
- **Baseline:** Logistic Regression + ELO-only for comparison
- **Metrics:** Accuracy, log-loss, Brier score, **RPS** (Ranked Probability Score — primary metric)
- **Walk-forward validation:** `scripts/walk_forward_validation.py` — folds 2006→2022, XGB vs ELO baseline
- **Feature ablation:** `scripts/ablation_features.py` — tests a candidate feature set against the base FEATURE_COLS; a feature enters `FEATURE_COLS` only if it improves global RPS

### Proyecciones tab (partially static)

The "Proyecciones" tab has two views:
- **Por ronda (Knockout)** — fully static; shows pre-computed probabilities from `predictions.json` / `live_predictions.json`. Only refreshes on deploy.
- **Simulador (Monte Carlo)** — partially dynamic; `fixedResults` (built from `liveMatches`, refreshes every 5 min) locks in played results automatically, but the probabilities for unplayed matches still come from the last `predict_live.py --export` run. Running `predict_live.py --export` + deploy is what updates the Proyecciones probabilities after each matchday.

### Simulator (Backend)

- Reads fixture (48 teams, 12 groups, knockout rounds) from `data/external/wc2026_fixture.json`
- For each simulation run:
  1. Sample match outcomes using model probabilities
  2. Update group standings (tiebreakers: goal diff, head-to-head)
  3. Advance qualified teams to knockout
  4. Penalties for draws (weighted by historical penalty conversion rates)
- Output: Win probability for each team in each round, champion distribution

### Frontend Architecture

**Technology:** Next.js 15 + React 19 + Tailwind CSS + Recharts + Framer Motion

**Key files:**
- `src/app/page.tsx`: Main tabbed interface (Live Tournament, Predictor, Groups, Simulator, ChatTab, etc.)
- `src/app/api/live/route.ts`: Server-side proxy to football-data.org (no-store cache, BOM-safe token parsing)
- `src/app/api/chat/route.ts`: AI chat endpoint — topic filter + response cache + rate limit + RAG + DeepSeek streaming
- `src/app/api/narrator/route.ts`: Scenario detection & contextual metadata (stadium names, historical matchups, confederation info) for match presentation
- `src/lib/simulator.ts`: Client-side Monte Carlo (runs 5,000 simulations in browser)
- `src/lib/live.ts`: Fetches live match results via `/api/live` endpoint
- `src/lib/i18n.tsx`: Dialect context — `Lang = "bogotano"|"paisa"|"boyaco"|"costeño"|"en"`. Base `_es` + 4 dialect narrator overlays; `useI18n()` / `useLang()` hooks
- `src/components/Predictor.tsx`: Match predictor UI — NarratorBanner (scenario detection + stadium info), CelebrationBurst, ColombiaPortugalOverlay, StadiumOverlay SVG
- `src/components/ChatTab.tsx`: Tabbed AI conversation interface with topic filtering and response caching
- `src/components/StatsTab.tsx`: WC 2026 live stats dashboard — goals KPIs, top scoring teams (bar chart), top scoring matches, score distribution, upsets (model misses sorted by lowest actual-winner probability). All computed client-side from `liveMatches` + `groupMatches` + `liveScores`. Replaces the ChatTab in the "Stats" tab (`curiosidades`).
- `src/components/ModelTab.tsx`: Live model accuracy — KPI pills, per-matchday bars, per-group grid with J1/J2/J3/FG columns (FG = group total %, count, delta vs J1), surprises section

**Data flow:**
1. Pipeline exports JSON files (`export_frontend_data.py`) to `frontend/public/data/`
2. `precompute_narrations.py` generates `narrations.json` (one DeepSeek call per match, cached) and `group_narratives.json` (one DeepSeek call per group/day preview)
3. Frontend loads pre-computed model predictions, ELO ratings, and narrations at page load
4. Live results fetched from `/api/live` (server-side proxy to football-data.org)
5. Monte Carlo runs on client-side with current standings
6. Chat questions → `/api/chat` → topic filter → cache check → tournament context injection → RAG → DeepSeek streaming
7. Predictor narration: checks `narrations[home|away|dialect]` first; only calls `/api/narrator` if missing

### CostGuard & LLM Budget

**See `docs/finops.md` for current spend snapshot and cost projections.**

Budget controls are enforced at 3 levels:

1. **Global budget** — `configs/budget.yaml` declares daily ($2), monthly ($50), and per-run (5 calls) limits plus per-model token costs. `src/cost_guard.py:CostGuard.check_and_record()` raises `BudgetExceeded` before any call that would breach a limit.
2. **Component-level strategy** — Each feature (narrations, chat, agent debate) has explicit cost trade-offs:
   - **Narrations:** Pre-computed once daily (DeepSeek, 1 call/match × dialects). Zero LLM cost per user.
   - **Chat:** Topic filter → cache → rate limit (20 req/hour/IP) before calling LLM. Cached responses cost $0.
   - **Agent Debate:** Reserve for high-value matches only (~0.08–0.10 USD per match). Forward-only (no retroactive backfill of already-played matches).
3. **Observability** — All LLM calls logged to `logs/llm_costs.jsonl`. Pipeline runs appended to `logs/pipeline_runs.jsonl` with duration, status, metrics, and artifacts for post-match evaluation.

If budget is exceeded, deterministic predictions fall back to EnsembleModel (no LLM).

### AI Chat API (`/api/chat`)

Three cost-protection layers run in order before any API call:

1. **Topic filter** — keyword regex (Spanish/English/Portuguese football terms). Non-football questions get a canned reply at zero cost.
2. **Response cache** — module-level `Map<sha256, {response, ts}>`, TTL 2h, max 400 entries. Same question within a warm serverless instance returns instantly.
3. **Rate limit** — sliding window 20 requests/hour per IP. Returns HTTP 429 with `Retry-After: 3600` if exceeded.

RAG pipeline (when `DASHSCOPE_API_KEY` is set):
- Embeds query with Qwen3 `text-embedding-v3` (512 dims)
- Cosine similarity over `frontend/public/data/rag_index.json`
- Top-5 chunks injected into DeepSeek system prompt

Without `DASHSCOPE_API_KEY` or without `rag_index.json`, the chat falls back to DeepSeek's general knowledge. In all cases, **tournament context is injected directly** into the system prompt: today's fixtures (UTC date filter on `group_matches.json`) and group standings (`group_standings.json`). This ensures the chat always knows what's playing today and the current table — independent of RAG.

### Narrator Endpoint (`/api/narrator`)

Serves pre-computed narrations from `narrations.json`. Flow:
1. Checks `narrations[home|away|dialect]` key in the static JSON file
2. If found: returns the text immediately (zero LLM cost per user)
3. If missing (knockout match not yet pre-computed, or new dialect): calls DeepSeek to generate on-the-fly

The static file is regenerated daily by `scripts/precompute_narrations.py`. The Predictor component passes `narrations` prop down to `UnifiedNarration`, which has its own `localLang` state (per-match dialect selector, synced to global on mount but independently switchable). Dialect cost strategy: group stage → Bogotá/neutral Spanish only while the flow is stable; knockout → all 5 dialects auto-activated by stage field.

### Group Narrative Previews

`frontend/public/data/group_narratives.json` stores pre-computed narrative previews for the group tab and live tournament cards. Key format: `"GROUP|YYYY-MM-DD|bogotano"`, for example `"A|2026-06-18|bogotano"`.

Generation:
```bash
python scripts/precompute_narrations.py --groups-only --days 1
```

These previews use heavier DeepSeek reasoning than single-match blurbs because they must combine standings, prior results, local venue, model probabilities, and per-team pressure. They should never invent data: if a team has not played, the output must say there is no recent tournament evidence rather than classifying only by historical name.

`deepseek-reasoner` counts its thinking tokens against `max_tokens`; with a tight budget the reasoning phase can consume the whole allowance and the final `content` comes back as an **empty string with a 200 OK** (no exception raised). `_call_group_narrative()` uses `max_tokens=3200` and falls back to `deepseek-chat` (no reasoning phase, so it can't truncate itself) if the reasoner response is empty. The skip-check before generating (`if key in group_narratives`) also treats an empty stored string as "not generated yet" rather than "already done" — otherwise a single bad run permanently blocks that group/date key from ever being retried.

Frontend rendering:
- `frontend/src/components/GroupNarrativeCard.tsx` renders the Markdown-like output as styled sections, tables, team blocks, and narrator phrases.
- `frontend/src/components/LiveTournament.tsx` shows compact previews for the current day — `selectDailyGroupNarratives()` filters strictly to `entry.date === today` (not `>=`) with no result cap, so a group with no narrative generated for today doesn't get backfilled with a future-dated entry that dilutes/displaces the groups actually playing today.
- `frontend/src/components/Groups.tsx` shows the full group narrative.

Operational expectations:
- J1: preview focuses on baseline favorites, uncertainty, venue, and first-match risk.
- J2: preview must reflect current points, previous results, pressure to win/draw, and how evening matches change after afternoon results.
- J3: preview must emphasize simultaneous matches, goal difference, direct qualification, and best-third scenarios.
- The prompt requires per-team fields: points, previous result, previous opponent strength, result quality, mood, pressure, dependency, danger category, and narrative reading.

---

## Key Decisions & Patterns

### Temporal Split Over K-Fold
Time-series data (match history) requires temporal validation to prevent leakage. Test set is always Qatar 2022 (never in training), not random K-folds.

### Custom ELO vs FIFA Rankings
ELO is computed from all internationals chronologically. K varies by tournament importance (WC=60, friendly=20). A margin-of-victory multiplier `log(1+|GD|)` scales each update. Home advantage adds 100 ELO points to the expected score for non-neutral venues.

### Live Learning Strategy
The model doesn't do online learning — XGBoost is re-trained from scratch each update. What changes meaningfully with each WC 2026 matchday is the ELO ratings: a team that beats a stronger opponent gains ELO, which feeds into updated features for subsequent predictions. Run `python scripts/live_update.py` after each matchday.

### Live Prediction Mode (`scripts/predict_live.py`)

Separate from the full pipeline. Reads `data/external/wc2026_live_results.csv` (WC 2026 results only, distinct from `results.csv`) and the full historical dataset, then re-computes ELO + form with a strict cutoff `= kickoff - 60s`. The anti-leakage assertion aborts if `features_cutoff >= match_kickoff`. Outputs `data/processed/live_predictions.json`; with `--export` also writes to `frontend/public/data/live_predictions.json`.

To add a result manually: `python scripts/predict_live.py --add-result "Argentina" "France" 3 3 2026-07-19`

### CostGuard & Observability

- **`configs/budget.yaml`**: declares daily ($2), monthly ($50), and per-run (5 calls) LLM limits plus per-model token costs
- **`src/cost_guard.py`**: `CostGuard.check_and_record()` raises `BudgetExceeded` before any call that would breach a limit; the Orchestrator catches it and falls back to the deterministic Ensemble
- **`src/pipeline_logger.py`**: `run_context(run_type, artifacts)` context manager wraps every pipeline/live run and appends a JSONL entry to `logs/pipeline_runs.jsonl` with duration, status, metrics, and artifacts
- **`logs/llm_costs.jsonl`**: one entry per LLM call (model, tokens, cost, ts)
- **`logs/pipeline_runs.jsonl`**: one entry per pipeline run

### Multi-Agent Architecture (src/agents/)
The Orchestrator is the single API gateway. It routes each match query to at most 2 sub-agents based on available context (injuries, odds, altitude, etc.). Each agent returns a `delta_P` (adjustment to XGBoost prior). The Orchestrator blends deltas with per-agent weights and confidence, clamped to 12% max total shift, then renormalizes to sum=1.
- **LLM agents**: IntMatch-Analytics-Pro, Roster-Data-Scout, Media-Sentiment-Parser, Travel-Logistics-Quant — all route through `src/agents/specialists/_llm.py`
- **LLM provider**: DeepSeek (`DEEPSEEK_API_KEY`) is primary; Anthropic Claude (`ANTHROPIC_API_KEY`) is fallback. Claude model aliases in `_MODEL_MAP` are remapped to `deepseek-chat` automatically.
- **Deterministic agents** (no LLM): FinOps-Bookmaker-Alpha (odds math), FIFA-Regs-Strategist (altitude/bracket), Travel-Logistics-Quant (haversine fallback)
- LLM agents fail gracefully (delta=0) when neither key is set.
- **Design specs**: see `agent/*.md` files (one per specialist) for role, input context, output schema, and cost profile. Consult when modifying or adding a new specialist.

### Agent Debate System (src/agent_debate.py) — logic-based predictions, no ML

Separate from the ML ensemble and from the `src/agents/` Orchestrator above. Three expert personas debate a match in three rounds using **deepseek-reasoner** (extended thinking), reasoning purely from tournament logic — group standings, classification pressure, and MD1/MD2 momentum — never from the trained model's probabilities. Built because the Poisson/XGB ensemble was underpredicting goal variability (see "Poisson Overdispersion" note below) and the user wanted an alternative grounded in pressure/narrative logic rather than statistics.

- **Agents**: Group Analyst (classification pressure, points, GD, what each team needs to advance), Tactical Scout (styles/tactics modulated by that pressure), Sentiment Reader (morale derived from the real MD1/MD2 result, e.g. "WIN vs South Africa (2-0)" reads differently than a 1-0 squeaker).
- **3 rounds**: independent initial positions → each agent rebuts the other two → consensus round produces a ranked top-3 scoreline with classification impact ("¿quién avanza? ¿quién queda eliminado?").
- **Structured output (4 predictions per match)**: Each agent proposes an individual prediction, plus a consensus. The consensus prompt emits:
  ```json
  {"group_analyst": {...}, "tactical_scout": {...}, "sentiment_reader": {...}, "consensus": {...}}
  ```
  Parsed by `AgentDebateSystem.parse_predictions()` into all 4 predictions with agent attribution. The frontend evaluates **individual agent accuracy** vs. consensus. `max_tokens=4500` for the consensus call — deepseek-reasoner counts its thinking tokens against the budget.
- **Real context, not generic**: `get_group_context()` computes actual standings from `data/external/wc2026_live_results.csv` (not from the frontend's pre-tournament Monte Carlo `group_standings.json`), matched to groups via `data/external/wc2026_fixture.json`. Status is granular, not just points: `"Need to WIN to secure 1st (pressure)"` vs `"Can secure 1st with DRAW (comfortable)"` vs `"Critical (0 pts, must win or OUT)"` — a team with 3 points after MD1 is not automatically "comfortable" if a draw in MD2 would let a rival overtake it on goal difference.
- **Name normalization**: `TEAM_NAME_MAPPING` in `agent_debate.py` (`"USA" → "United States"`) bridges the fixture's naming with the live-results CSV's naming — both `get_group_context()` and the frontend's `lib/agentDebate.ts` `normalizeTeamName()` must stay in sync if more aliases are added.
- **Running it**: `python scripts/run_agent_debate.py "Home" "Away" ...` — accumulates into `data/processed/agent_debate_results.json` (does not overwrite), is idempotent (skips a pair that already has a non-error result unless `--force`), and deduplicates by team pair on every run (guards against the Windows console crashing mid-print on emoji output, which previously produced a spurious duplicate error entry alongside the real result).
- **Forward-only**: by design there is no retroactive backfill of already-played matches (cost/time tradeoff — 3 agents × 3 rounds × deepseek-reasoner per match). The "Modelo" tab's agent accuracy tables only reflect matches that were debated *before* being played.
- **Frontend wiring**: `frontend/src/app/api/agent-debate/route.ts` serves the exported static JSON (`frontend/public/data/agent_debate_results.json`, 60s in-memory cache — never calls DeepSeek per request). `frontend/src/components/AgentDebatePanel.tsx` renders it: `variant="compact"` is a collapsed `<details>` (just a "Ver consenso completo" arrow) used in `Predictor.tsx` (right after "Marcador más probable" / altitude badge) and in `LiveTournament.tsx`'s "Próximos" tab (under each fixture's forecast badge); it returns `null` silently when no debate exists for that match, so the upcoming-matches list isn't cluttered with "not available" placeholders. `frontend/src/lib/agentDebate.ts` mirrors `lib/live.ts`'s `modelVerdict`/`orientScore` pattern (`agentVerdict`, `computeAgentResults`) so `ModelTab.tsx` can show the same per-matchday/per-group accuracy breakdown for agents side-by-side with the ML model's.

### Pre-computed Narrations (Zero LLM Cost Per User)
`narrations.json` is built once per day by `scripts/precompute_narrations.py` (DeepSeek, 1 call per match × dialects). Key format: `"home|away|dialect"`. The frontend loads the full JSON at page load and passes it as a prop to `Predictor → UnifiedNarration`. The narrator endpoint serves static keys and only falls back to a live LLM call when a key is missing (e.g., knockout matches before their narration is generated). Group-stage dialect strategy is intentionally restrained: keep `DIALECTS_GROUP = ["bogotano"]` until the prediction/narration flow is stable; `DIALECTS_KNOCKOUT = ["bogotano","paisa","boyaco","costeño","en"]` activates automatically when `match.stage != "group"`.

### Isotonic Calibration
Probabilities matter more than accuracy in a tournament simulator. Isotonic calibration ensures the model's predicted probabilities match observed win rates.

### Client-Side Simulation
1,128 pre-calculated team-pair matchups are embedded in frontend. Monte Carlo runs client-side (no server load) for instant projections and exploration.

### Temporal Split in Tests
Tests use the same temporal strategy: fixture data with year=2014/2018/2022 to verify no leakage occurs between train and test sets.

---

## File Structure Summary

```
├── src/
│   ├── extractor.py        # Data loading + team name normalization
│   ├── features.py         # ELO (K by tournament + margin mult + home adv), H2H, form, weights
│   ├── model.py            # XGBoost + TimeSeriesSplit calibration, RPS metric
│   ├── poisson_model.py    # Bivariate Poisson: attack/defense strengths, scoreline matrix
│   ├── ensemble.py         # EnsembleModel: ELO + Poisson + XGB blend
│   ├── pipeline_logger.py  # JSONL run ledger → logs/pipeline_runs.jsonl
│   ├── cost_guard.py       # CostGuard: reads budget.yaml, enforces LLM spend limits
│   ├── simulator.py        # Tournament simulation (official 2026 bracket, host advantage)
│   ├── app.py              # Streamlit demo interface
│   ├── agent_debate.py     # Agent Debate System: 3-round logic-based debate (deepseek-reasoner)
│   └── agents/
│       ├── base.py         # MatchContext, AgentResult, BaseAgent ABC
│       ├── orchestrator.py # Routing (max 2 agents), delta blending, OrchestratorOutput
│       └── specialists/
│           ├── intmatch.py  # Tactical matchup (Claude Haiku)
│           ├── roster.py    # Injury/WAR analysis (Claude Sonnet)
│           ├── media.py     # Sentiment/morale (Claude Sonnet)
│           ├── travel.py    # Fatigue/altitude (Claude Haiku + deterministic)
│           ├── finops.py    # Odds implied probs (deterministic)
│           └── fifa_regs.py # Bracket/altitude math (deterministic)
├── agent/                  # Agent design specs (one .md per specialist)
│   ├── intmatch_analytics_pro.md
│   ├── roster_data_scout.md
│   ├── media_sentiment_parser.md
│   ├── travel_logistics_quant.md
│   ├── finops_bookmaker_alpha.md
│   └── fifa_regs_strategist.md
├── contracts/              # Formal data + feature schemas (prevent silent failures)
│   ├── data_contracts.md   # Bronze/silver/gold schemas for CSVs, parquets, JSONs
│   └── module_contracts.md # Feature + model input/output contracts
├── configs/
│   └── budget.yaml         # LLM cost limits (daily/monthly/per-run) + token costs
├── scripts/
│   ├── run_pipeline.py             # Execute full pipeline
│   ├── export_frontend_data.py     # Generate JSONs for frontend
│   ├── live_update.py              # Orchestrator: fetch results → retrain → export
│   ├── update_wc_results.py        # Fill NA scores in results.csv from football-data.org
│   ├── predict_live.py             # Live predictions with per-match ELO cutoff (anti-leakage)
│   ├── precompute_narrations.py    # Daily narrations × dialects → narrations.json (DeepSeek, 1 call/match)
│   ├── run_agent_debate.py         # Runs Agent Debate System for given matches → agent_debate_results.json (accumulative, idempotent)
│   ├── ablation_features.py        # Ablation test for candidate features vs base FEATURE_COLS
│   ├── walk_forward_validation.py  # Walk-forward RPS vs ELO baseline
│   ├── build_rag_index.py          # Generate embedding index for chat RAG
│   └── enrich_goalscorers.py       # Optional: goalscorer enrichment
├── frontend/               # Next.js 15 + React 19
│   ├── src/app/
│   │   ├── page.tsx        # Main tabbed interface; loads narrations.json and passes as prop
│   │   ├── api/live/       # Proxy to football-data.org
│   │   ├── api/chat/       # AI chat: tournament context injection + topic filter + cache + RAG + DeepSeek
│   │   ├── api/narrator/   # Serves narrations.json; LLM fallback for missing keys only
│   │   └── api/agent-debate/ # Serves agent_debate_results.json (60s in-memory cache, no live LLM calls)
│   ├── src/components/
│   │   ├── Predictor.tsx   # Match predictor + UnifiedNarration (localLang + dialect selector) + AgentDebatePanel
│   │   ├── ModelTab.tsx    # Live model accuracy: KPIs, per-matchday bars, per-group J1/J2/J3/FG (ML + Agents side-by-side), surprises
│   │   ├── AgentDebatePanel.tsx # Collapsed-by-default consensus panel (compact: Predictor/Próximos; full: detailed)
│   │   ├── StatsTab.tsx    # WC 2026 stats dashboard: goals, top teams, top matches, score dist, upsets
│   │   └── ...             # Groups, Simulator, Knockout, ChatTab, etc.
│   ├── src/lib/
│   │   ├── simulator.ts    # Client-side Monte Carlo
│   │   ├── live.ts         # Live results fetching + orientScore + modelVerdict
│   │   ├── agentDebate.ts  # Agent Debate verdict/accuracy helpers (mirrors live.ts for the ML model)
│   │   └── i18n.tsx        # i18n context + regional dialects
│   └── public/data/        # Exported JSONs: teams, predictions, narrations, group_matches, standings, etc.
├── tests/                  # 112+ tests: features, model, agents, cost guard, integrity, simulator, live prediction
├── data/
│   ├── raw/                # results.csv (incl. WC 2026 fixture), shootouts.csv, goalscorers.csv
│   ├── processed/          # Generated CSVs, parquets, JSONs (regenerable, gitignored)
│   └── external/           # wc2026_fixture.json; wc2026_live_results.csv (played WC 2026 only)
├── models/                 # Serialized models (gitignored, regenerable)
├── logs/                   # pipeline_runs.jsonl, llm_costs.jsonl (gitignored)
├── notebooks/              # EDA and analysis
├── instrucciones.md        # Daily ops: MD1/MD2/MD3 cycles, double-run protocol, cost table
├── proyecto.md             # Project definition, deliverables (E1–E5), and status
├── model_card.md           # Model performance, walk-forward results, feature ablation
├── methodology.md          # Model methodology, limitations, responsible-use statement
├── guia.md                 # Technical roadmap (Phases 0–6), design decisions (D1–D6)
├── requirements.txt        # Python dependencies
└── README.md
```

---

## Common Workflows

### Updating Model After a WC 2026 Matchday

```bash
# 1. Fetch new results, retrain, export JSONs (~90s; skips if no new matches)
python scripts/live_update.py

# 2. Recalculate live predictions with multi-agent enrichment
python scripts/predict_live.py --export

# 3. Pre-compute match narrations + group previews for today's context
python scripts/precompute_narrations.py

# Optional: group previews only, after prompt/context changes or MD2 afternoon results
python scripts/precompute_narrations.py --groups-only --days 1

# Optional: agent debate for specific upcoming matches (forward-only, no backfill)
python scripts/run_agent_debate.py "Mexico" "South Korea"
python scripts/export_frontend_data.py

# 4. Deploy
cd frontend && npx vercel --prod
```

**MD2 double-run protocol** (Jun 18–23, 4 matches/day split afternoon/evening): run the full cycle once in the morning before any match, then run steps 1–4 again in the afternoon after the first 2 results are in. This ensures evening match predictions and group previews reflect qualification pressure from the afternoon results. See `instrucciones.md` for the full MD2/MD3 calendar and cost table.

**MD3 simultaneous protocol:** group matches kick off at the same hour, so standings must be interpreted as scenario probabilities rather than sequential results. Group previews should emphasize direct qualification, goal difference, and best-third pressure.

### Live Predictions Without Full Retrain (between matchdays)

```bash
# Predict pending matches using current model + live ELO cutoff per match
python scripts/predict_live.py --export

# Add a result manually and re-predict
python scripts/predict_live.py --add-result "Mexico" "Poland" 0 0 2026-06-14
python scripts/predict_live.py --export
```

### Training a New Model

1. `python scripts/run_pipeline.py` — Regenerates features and trains all models
2. Check metrics output (accuracy, log-loss, Brier score, calibration error)
3. Verify test set is Qatar 2022 (temporal split, no leakage)

### Debugging Model Predictions

- Check `src/model.py`: FEATURE_COLS, LABEL_MAP
- Review feature values in `data/processed/features.parquet`
- Use Streamlit app (`streamlit run src/app.py`) to inspect predictions
- Compare baseline (LogisticRegression) vs XGBoost to isolate non-linear improvements

### Building the RAG Index (requires DashScope key)

```bash
# Set key in frontend/.env.local: DASHSCOPE_API_KEY=<key>
python scripts/build_rag_index.py
# → generates frontend/public/data/rag_index.json
# Chat API uses it automatically on next deploy
```

### Extending Frontend

- Add new component in `src/components/`
- Use `useI18n()` hook for multi-language support
- Client-side simulator in `lib/simulator.ts` handles Monte Carlo; no backend call needed
- Live results in `lib/live.ts` cache via `/api/live` (server-side proxy to football-data.org)

---

## Testing Strategy

- **Temporal split validation:** Ensure train < test_year
- **Feature presence:** All FEATURE_COLS present in feature matrix
- **Calibration checks:** Brier score and log-loss on test set
- **Simulator:** Deterministic seed (random_state=42) for reproducibility
- **No mock DB:** Integration tests run against real data files (CSV, JSON, PKL)
- **Data contracts:** Every pipeline run validates input/output schemas (see `contracts/data_contracts.md`). Silent data quality failures are unacceptable — all assertions are explicit.

---

## Environment & Secrets

All secrets via env vars only — never in code.

| Variable | Where | Purpose |
|---|---|---|
| `FOOTBALL_DATA_TOKEN` | `frontend/.env.local` + Vercel | Live match data from football-data.org |
| `DEEPSEEK_API_KEY` | `frontend/.env.local` + Vercel + `.env` | AI chat (frontend) + primary LLM for Python agents |
| `DASHSCOPE_API_KEY` | `frontend/.env.local` + Vercel | Query embeddings for RAG (Qwen3 text-embedding-v3) |
| `ANTHROPIC_API_KEY` | `.env` + `frontend/.env.local` + Vercel | Fallback LLM for Python agents + frontend narrator when DeepSeek unavailable |

`update_wc_results.py` auto-loads `FOOTBALL_DATA_TOKEN` from `frontend/.env.local` if not set in the environment — no need to export it manually when running locally.

---

## Performance Notes

- **ELO calculation:** O(n) chronological pass over all matches (~49k rows)
- **Feature matrix:** Pandas vectorized operations, no loops
- **XGBoost training:** ~900 samples (World Cup matches only in test), ~1s training time
- **Full live_update.py cycle:** ~90 seconds (dominated by pipeline + export)
- **Frontend simulator:** 5,000 Monte Carlo iterations in browser (~200ms on modern hardware)
- **Chat cache hit rate:** ~70-80% for warm serverless instances (module-level Map, SHA-256 key, TTL 2h)
- **Chat rate limit:** 20 requests/hour/IP — prevents abuse without Redis
