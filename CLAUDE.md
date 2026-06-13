# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mundial Predictor 2026** is an end-to-end ML pipeline for predicting FIFA World Cup results using XGBoost with custom ELO ratings, feature engineering, Monte Carlo tournament simulation, and live match tracking.

**Key characteristics:**
- Python backend: data extraction → ELO calculation → feature engineering → XGBoost training/evaluation
- Next.js frontend: live tournament tracking, match predictor, Monte Carlo projections, multi-language (ES/EN/PT)
- Client-side Monte Carlo simulator (runs in browser on pre-calculated team pairs)
- Temporal split strategy (test = Qatar 2022 to avoid leakage in time-series data)
- 35+ pytest tests covering extraction, features, model training, and simulation

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

# (Optional) Enrich goalscorer stats
python scripts/enrich_goalscorers.py
```

### Testing

```bash
# Run all tests
pytest

# Run tests for a specific module
pytest tests/test_model.py
pytest tests/test_features.py
pytest tests/test_simulator.py
pytest tests/test_extractor.py

# Verbose with output
pytest -v

# Run a single test
pytest tests/test_model.py::test_temporal_split_no_leakage
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

### Data Pipeline

```
data/raw/{international_results.csv}
    ↓ [load_results + normalize team names]
    ↓ [filter_world_cups]
    ↓ [add_outcome: map scores to home_win/draw/away_win]
data/processed/wc_clean.csv
    ↓ [compute_elo_ratings: chronological ELO update]
data/processed/current_elo.json
    ↓ [build_feature_matrix: add H2H, form, experience]
data/processed/features.parquet
    ↓ [temporal_split: train < 2022, test = 2022]
    ↓ [train XGBoost + CalibratedClassifierCV]
models/{logistic_regression, xgb_calibrated, xgb}.pkl
```

**Key files:**
- `src/extractor.py`: Data loading, World Cup filtering, outcome mapping, team name normalization
- `src/features.py`: ELO (K by tournament + margin multiplier + home advantage), rolling form, H2H, WC experience, tournament_weight
- `src/model.py`: XGBoost + TimeSeriesSplit calibration, temporal 3-way split (train/calib/test), RPS metric
- `src/simulator.py`: Monte Carlo simulation (official 2026 bracket, host home advantage)
- `src/agents/`: Multi-agent system — Orchestrator routes to max 2 specialists, each produces delta_P adjustments

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
- **Training data:** All 49,765 internationals (use_all_matches=True); WC games weighted 1.0, friendlies 0.20
- **Base model:** XGBoost multi-class softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)
- **Baseline:** Logistic Regression + ELO-only for comparison
- **Metrics:** Accuracy, log-loss, Brier score, **RPS** (Ranked Probability Score — primary metric)
- **Walk-forward validation:** `scripts/walk_forward_validation.py` — folds 2006→2022, XGB vs ELO baseline

### Simulator (Backend)

- Reads fixture (48 teams, 12 groups, knockout rounds) from `data/external/wc2026_fixture.json`
- For each simulation run:
  1. Sample match outcomes using model probabilities
  2. Update group standings (tiebreakers: goal diff, head-to-head)
  3. Advance qualified teams to knockout
  4. Penalties for draws (weighted by historical penalty conversion rates)
- Output: Win probability for each team in each round, champion distribution

### Frontend Architecture

**Technology:** Next.js 15 + React 19 + Tailwind CSS + Recharts

**Key files:**
- `src/app/page.tsx`: Main tabbed interface (Live Tournament, Predictor, Groups, Simulator, etc.)
- `src/lib/simulator.ts`: Client-side Monte Carlo (runs 5,000 simulations in browser)
- `src/lib/live.ts`: Fetches live match results via `/api/live` endpoint (football-data.org proxy)
- `src/lib/i18n.tsx`: Multi-language support context
- `src/components/`: Modular UI components (Groups, Knockout, Predictor, Simulator, etc.)

**Data flow:**
1. Pipeline exports JSON files (`export_frontend_data.py`)
2. Frontend loads pre-computed model predictions and ELO ratings
3. Live results fetched from `/api/live` (server-side caching via football-data.org)
4. Monte Carlo runs on client-side with current standings

---

## Key Decisions & Patterns

### Temporal Split Over K-Fold
Time-series data (match history) requires temporal validation to prevent leakage. Test set is always Qatar 2022 (never in training), not random K-folds.

### Custom ELO vs FIFA Rankings
ELO is computed from all internationals chronologically. K varies by tournament importance (WC=60, friendly=20). A margin-of-victory multiplier `log(1+|GD|)` scales each update. Home advantage adds 100 ELO points to the expected score for non-neutral venues.

### Multi-Agent Architecture (src/agents/)
The Orchestrator is the single API gateway. It routes each match query to at most 2 sub-agents based on available context (injuries, odds, altitude, etc.). Each agent returns a `delta_P` (adjustment to XGBoost prior). The Orchestrator blends deltas with per-agent weights and confidence, clamped to 12% max total shift, then renormalizes to sum=1.
- **LLM agents** (Claude API): IntMatch-Analytics-Pro (Haiku), Roster-Data-Scout (Sonnet), Media-Sentiment-Parser (Sonnet), Travel-Logistics-Quant (Haiku)
- **Deterministic agents** (no LLM): FinOps-Bookmaker-Alpha (odds math), FIFA-Regs-Strategist (altitude/bracket), Travel-Logistics-Quant (haversine fallback)
- Requires `ANTHROPIC_API_KEY` env var; LLM agents fail gracefully (delta=0) without it.

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
│   ├── simulator.py        # Tournament simulation (official 2026 bracket, host advantage)
│   ├── app.py              # Streamlit demo interface
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
├── scripts/
│   ├── run_pipeline.py          # Execute full pipeline
│   ├── walk_forward_validation.py  # Walk-forward RPS vs ELO baseline
│   ├── export_frontend_data.py  # Generate JSONs for frontend
│   └── enrich_goalscorers.py    # Optional: goalscorer enrichment
├── frontend/               # Next.js 15 + React 19
│   ├── src/app/           # Pages (layout, main page, /api/live)
│   ├── src/components/    # UI components (Groups, Predictor, Simulator, etc.)
│   ├── src/lib/
│   │   ├── simulator.ts   # Client-side Monte Carlo
│   │   ├── live.ts        # Live results fetching
│   │   └── i18n.tsx       # i18n context
│   └── package.json
├── tests/                 # pytest — test_extractor, test_features, test_model, test_simulator
├── data/
│   ├── raw/              # Raw input (gitignored, downloaded via kagglehub)
│   ├── processed/        # Generated CSVs, parquets, JSONs (regenerable, gitignored)
│   └── external/         # Manual fixtures (wc2026_fixture.json)
├── models/               # Serialized models (gitignored, regenerable)
├── notebooks/            # EDA and analysis
├── requirements.txt      # Python dependencies
└── README.md             # Project overview
```

---

## Common Workflows

### Training a New Model

1. `python scripts/run_pipeline.py` — Regenerates features and trains all models
2. Check metrics output (accuracy, log-loss, Brier score, calibration error)
3. Verify test set is Qatar 2022 (temporal split, no leakage)

### Updating Model for New Matches

1. Ensure `data/raw/international_results.csv` includes latest matches
2. Run `python scripts/run_pipeline.py` to recompute ELO and features
3. Run `python scripts/export_frontend_data.py` to update frontend JSONs
4. Commit updated model and exported data

### Debugging Model Predictions

- Check `src/model.py`: FEATURE_COLS, LABEL_MAP
- Review feature values in `data/processed/features.parquet`
- Use Streamlit app (`streamlit run src/app.py`) to inspect predictions
- Compare baseline (LogisticRegression) vs XGBoost to isolate non-linear improvements

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

---

## Environment & Secrets

- `.env`: Optional token for football-data.org (server-side API calls)
- `frontend/.env.local`: Frontend env vars (if needed, see `.env.example`)
- No secrets in code; all sensitive config via env vars or `.env`
- Raw data and models are gitignored (regenerable from pipeline)

---

## Performance Notes

- **ELO calculation:** O(n) chronological pass over all matches (~49k rows)
- **Feature matrix:** Pandas vectorized operations, no loops
- **XGBoost training:** ~900 samples (World Cup matches), ~1s training time
- **Frontend simulator:** 5,000 Monte Carlo iterations in browser (~200ms on modern hardware)
- **Live API calls:** Cached server-side (`/api/live`), fallback to openfootball if token unavailable
