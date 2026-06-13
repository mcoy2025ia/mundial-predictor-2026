# Methodology — Mundial Predictor 2026

This document describes the end-to-end pipeline that produces the match probabilities displayed on the Mundial Predictor 2026 web application. It covers data sourcing, feature engineering, model training, validation, and the live update mechanism.

---

## 1. Data Pipeline

### 1.1 Source Data

| Dataset | Path | Description |
|---|---|---|
| International results | `data/raw/` (Kaggle) | 49,477 matches, Nov 1872 – present |
| WC 2026 fixture | `data/external/wc2026_fixture.json` | Official 104-match bracket |
| Live results | `data/external/wc2026_live_results.csv` | Updated manually/via CLI after each match day |

### 1.2 Name Normalization

Team names are normalized to their current canonical form at load time (`src/extractor.py`). Historical names (e.g., "West Germany" → "Germany", "Zaire" → "DR Congo") are resolved through a transitivity-closed mapping.

The fixture uses non-standard names in some cases:

| Fixture | Dataset |
|---|---|
| USA | United States |
| Bosnia & Herzegovina | Bosnia and Herzegovina |
| Curaçao | Curacao |

### 1.3 Tournament Filtering

World Cup matches are identified by `tournament == "FIFA World Cup"`. All 49,765 matches with available scores are used for ELO computation and feature engineering; the tournament weight determines their influence during XGBoost training.

---

## 2. ELO Rating System

ELO is computed in a single chronological pass over all 49,477 internationals (`src/features.py: compute_elo_ratings`).

### 2.1 Update Formula

```
K_scaled = K(tournament) × log(1 + |GD|) / log(2)
new_rating = old_rating + K_scaled × (actual - expected)
```

Where:
- `K(tournament)` — varies from 60 (FIFA World Cup) to 20 (Friendly). See `K_BY_TOURNAMENT` dict.
- `log(1 + |GD|) / log(2)` — goal margin multiplier: a 2-goal win (|GD|=2) scales K by ~1.58×. Normalised so |GD|=1 gives multiplier=1.0.
- `expected = 1 / (1 + 10^((R_away − R_home_adj) / 400))` with `R_home_adj = R_home + 100` for non-neutral venues.

### 2.2 Home Advantage

When `neutral=False`, the home team's ELO is boosted by **+100 points** in the expected score calculation only (not stored). This captures the ~56% empirical home win rate in WC qualifying matches.

### 2.3 Tournament K-Factors

| Tournament | K |
|---|---|
| FIFA World Cup | 60 |
| UEFA Euro / Copa América | 55 |
| AFCON / AFC Asian Cup | 50 |
| WC Qualification | 40 |
| Nations Leagues | 40 |
| Friendly | 20 |
| Other | 30 (default) |

### 2.4 Initialisation

All teams start at 1,500. The chronological pass since 1872 differentiates ratings naturally; by 2026 the spread is approximately 1,100–2,100.

---

## 3. Feature Engineering

The full feature matrix (`src/features.py: build_feature_matrix`) contains 49,765 rows (all scored internationals) and 16 columns. Only 10 of these enter the XGBoost model (`FEATURE_COLS`).

### 3.1 Feature Construction (no leakage)

| Feature | Method |
|---|---|
| `elo_diff`, `elo_home`, `elo_away` | Pre-match ELO (computed before the match in the chronological pass) |
| `home_goals_scored_avg5` | `shift(1).rolling(5).mean()` over the team's match timeline |
| `home_goals_conceded_avg5` | Same, for goals conceded |
| `away_goals_scored_avg5` | Same for the away team |
| `away_goals_conceded_avg5` | Same for the away team |
| `h2h_home_win_pct` | Cumulative H2H record, updated after each match (no self-reference) |
| `is_neutral` | 0 if the match home team is a 2026 host nation at a home venue |
| `wc_experience_diff` | Cumulative WC appearances (chronologically gated) |

### 3.2 Tournament Weights

Each row carries a `tournament_weight` (0.20–1.0) used as `sample_weight` in XGBoost training. WC matches receive 5× the influence of friendlies.

### 3.3 Ablated Features

`home_days_rest` / `away_days_rest` (days since last international) were tested via 5-fold walk-forward ablation. Global RPS worsened by +0.0005. Hypothesis: ELO implicitly captures team fitness through recent results; calendar distance adds noise. Features excluded from `FEATURE_COLS`.

---

## 4. Model Architecture

### 4.1 XGBoost (Primary Classifier)

```
XGBoost multi-class softmax
  → CalibratedClassifierCV(cv=TimeSeriesSplit(n=3), method="sigmoid")
```

- **Temporal calibration split:** train < 2018 / calibration = 2018 / test = WC 2022
- `TimeSeriesSplit` ensures the calibration folds respect time ordering
- **Sample weights:** `tournament_weight` column — WC matches drive the loss more

Key hyperparameters (defaults):
- `n_estimators=300`, `max_depth=4`, `learning_rate=0.05`
- `subsample=0.8`, `colsample_bytree=0.8`
- `objective=multi:softmax`, `num_class=3`

### 4.2 Poisson Model (Dixon-Robinson)

`src/poisson_model.py` estimates per-team attack/defense parameters via iterative coordinate descent:

1. Fix defense, optimise attack (weighted MLE over Poisson count data)
2. Fix attack, optimise defense
3. Normalise mean(attack) = mean(defense) = 1.0
4. Repeat for 100 iterations or until convergence

Prediction: λ_home = mean_goals_home × attack_home × defense_away × (1 + home_advantage if non-neutral)

The 8×8 scoreline matrix (`MAX_GOALS=7`) is computed as the outer product of independent Poisson(λ) distributions. Aggregating yields 1X2 probabilities.

### 4.3 ELO-Only Baseline

A deterministic model with dynamic draw fraction:

```python
draw_frac = 0.28 × (1 − |p_home_raw − 0.5| × 1.6)
draw_frac = clip(draw_frac, 0.08, 0.36)
```

No training required. Serves as the lower bound for model evaluation.

### 4.4 Ensemble

```
p_ensemble = 0.35 × p_ELO + 0.35 × p_Poisson + 0.30 × p_XGB
```

Weights chosen by grid search over walk-forward RPS. ELO and Poisson are given equal priority because they are independent signal sources; XGB is slightly down-weighted as it overfits more in small WC datasets.

The blend is renormalised to sum=1.0 before outputting.

---

## 5. Validation Strategy

### 5.1 Why Not K-Fold?

Football data is a time series. Random K-fold splits create leakage: a model trained on 2022 WC data that is tested on a 2010 WC match will achieve unrealistically optimistic metrics. We use **strictly temporal splits** throughout.

### 5.2 Temporal Split (final model)

```
Train:       year < 2018   (~41,635 matches)
Calibration: year == 2018  (~929 WC + qualifying matches)
Test:        WC 2022       (64 matches, never seen during training)
```

### 5.3 Walk-Forward Validation (5-fold)

Each fold:
- Train on all matches before test year
- Test on that year's WC (exactly 64 matches)
- Folds: 2006, 2010, 2014, 2018, 2022 → n=320 predictions total

This is the most reliable estimate of out-of-sample performance because it mirrors the actual deployment scenario (predict a WC with data up to that point).

### 5.4 Primary Metric: RPS

**Ranked Probability Score** (lower = better):

```
RPS = (1/(K-1)) × Σ_{j=1}^{K-1} (CDF_predicted_j − CDF_observed_j)²
```

For K=3 outcomes (home/draw/away), RPS is the mean squared difference between predicted and observed cumulative distribution. It rewards confident correct predictions and penalises confident wrong predictions more than accuracy does.

A coin-flip model has RPS ≈ 0.25. Our ensemble achieves 0.1958 overall.

---

## 6. Live Update Pipeline

### 6.1 Anti-Leakage Contract

For each pending match:
```
cutoff = kickoff − 60 seconds
assert cutoff < kickoff           # enforced by assert_no_leakage()
features = ELO(all_data_until_cutoff)
```

This ensures WC results already played are incorporated into the ELO and form of subsequent matches, without contaminating the current match's prediction.

### 6.2 Update Workflow

```bash
# 1. Register match result
python scripts/predict_live.py --add-result "Mexico" "South Africa" 2 0 2026-06-11

# 2. Re-predict all pending matches (ELO now includes the new result)
python scripts/predict_live.py --export
```

Output: `data/processed/live_predictions.json` + `frontend/public/data/live_predictions.json`

### 6.3 Venue and Neutrality

The 2026 tournament has three host nations (Mexico, USA, Canada). `is_neutral=False` is applied when:
- **Mexico** plays at Mexico City, Guadalajara, or Monterrey
- **Canada** plays at Vancouver or Toronto
- **United States** plays at any other 2026 venue

This is encoded at fixture load time and propagates to the `is_neutral` feature in predictions.

---

## 7. Multi-Agent Adjustments (Optional)

The multi-agent system (`src/agents/`) provides optional context-aware adjustments on top of the Ensemble prior:

1. The **Orchestrator** selects at most 2 agents per match (by priority)
2. Each agent returns a `delta_P` (adjustment to home/draw/away probabilities)
3. Deltas are blended with per-agent weights × confidence, then clamped to ±12% total shift
4. Renormalised to sum=1.0

**LLM agents:** IntMatch-Analytics-Pro (Claude Haiku), Roster-Data-Scout (Sonnet), Media-Sentiment-Parser (Sonnet), Travel-Logistics-Quant (Haiku)  
**Deterministic agents:** FinOps-Bookmaker-Alpha (odds overround removal), FIFA-Regs-Strategist (altitude penalty)

Budget guardrails: $2/day · $50/month · max 5 LLM calls per pipeline run (`configs/budget.yaml`).

The base Ensemble is fully functional without the multi-agent layer. LLM agents fail gracefully (delta=0) if `ANTHROPIC_API_KEY` is not set or budget is exhausted.

---

## 8. Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| No real-time squad data | Up to ±10% accuracy loss for injury-affected matches | Roster-Data-Scout agent (optional) |
| Poisson assumes goal independence | Underestimates draw probability slightly | Ensemble weight compensates |
| ELO doesn't decay over inactivity | Teams with long gaps may be over/under-rated | Days-rest feature was tested; rejected (no RPS improvement) |
| Small WC test set (64 matches) | High variance in fold-level metrics | 5-fold walk-forward mitigates; aggregate n=320 more reliable |
| Calibration fitted on WC 2018 | Drift possible as football evolves | Re-calibrate after each tournament |
| Fixture placeholders (W-codes) | Knockout teams unknown until results computed | Live pipeline re-runs predictions as bracket resolves |

---

*For model performance summary see `model_card.md`. For setup and usage see `CLAUDE.md`.*
