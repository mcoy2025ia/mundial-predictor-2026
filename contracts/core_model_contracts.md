# Core Model Contracts — Mundial Predictor 2026

> These are MUST-HAVE interfaces. The Ensemble always works without LLM agents, API keys, or external dependencies.

---

## Guarantee: Core Predictive Engine (Zero External Dependencies)

The Ensemble model is **deterministic, reproducible, and always available**. It requires no LLM API keys, no agent context, and no additional computation beyond the pre-trained models.

```
Input: team names, ELO ratings, feature vector
↓ (deterministic computation)
Output: (p_home, p_draw, p_away) ∈ [0, 1], sum = 1.0
↓ (always)
No failures, no degradation
```

---

## `src/features.py` — Feature Engineering Pipeline

### `compute_elo_ratings(df_all: pd.DataFrame) → tuple[pd.DataFrame, dict]`

**Input:**
- `df_all`: DataFrame with columns `date, home_team, away_team, home_score, away_score, tournament, neutral`
- Must be ordered by date (ascending) — `load_results()` guarantees this

**Output:**
- Tuple: `(df_with_elo, final_ratings_dict)`
  - `df_with_elo`: Original DataFrame + columns `elo_home, elo_away, elo_diff`
  - `final_ratings_dict`: `{team_name: elo_float}` for all teams in df_all

**Guarantee:**
- No in-place modifications to input DataFrame
- ELO chronological pass: each match processes exactly once, in order
- K-factors by tournament type (WC=60, Euro=55, Friendly=20, etc.)
- Margin multiplier: `log(1 + |goal_diff|) / log(2)`
- Home advantage: +100 ELO points in expected (non-neutral only)
- All teams initialize at 1,500

---

### `build_feature_matrix(df_all, df_wc, use_all_matches=True) → pd.DataFrame`

**Input:**
- `df_all`: Full results DataFrame with ELO computed
- `df_wc`: World Cup subset (for filtering)
- `use_all_matches`: if True, use ~49k internationals; if False, use only WC

**Output:**
- DataFrame with columns: FEATURE_COLS + metadata (date, year, home_team, away_team, outcome, tournament_weight)

**FEATURE_COLS (10 required features):**
```
["elo_diff", "elo_home", "elo_away",
 "home_goals_scored_avg5", "home_goals_conceded_avg5",
 "away_goals_scored_avg5", "away_goals_conceded_avg5",
 "h2h_home_win_pct", "is_neutral", "wc_experience_diff"]
```

**Guarantee:**
- Zero leakage: rolling stats use `shift(1)` over match timeline
- H2H and experience computed forward, never referencing self
- All values pre-match (no post-match data in features)
- NaN handling: drops rows with missing features

---

## `src/model.py` — XGBoost Training & Calibration

### `FEATURE_COLS: list[str]`
See above.

### `LABEL_MAP: dict[str, int]`
```python
LABEL_MAP = {"home_win": 0, "draw": 1, "away_win": 2}
```

### `temporal_split(df, test_year=2022, calib_year=2018) → tuple`

**Output:**
- `(df_train, df_calib, df_test)` — three DataFrames

**Guarantee:**
- `df_train`: year < calib_year (no future data leaks into training)
- `df_calib`: year == calib_year (used only for isotonic calibration)
- `df_test`: year == test_year (held-out, never seen in training or calibration)
- Temporal ordering preserved: test year always > calib year > train cutoff

**Default split (final model):**
- Train: year < 2018 (~41,635 matches)
- Calibration: year == 2018 (~929 matches)
- Test: year == 2022 (64 matches)

---

### `train(df_train, model_type="xgb_calibrated", df_calib=None) → sklearn estimator`

**Input:**
- `df_train`: training DataFrame with FEATURE_COLS + outcome labels
- `model_type`: "baseline" | "xgb" | "xgb_calibrated"
- `df_calib`: (optional) calibration set for isotonic fitting

**Output:**
- Fitted sklearn estimator

**For model_type="xgb_calibrated":**
- Base: XGBoost multi:softmax (3 classes)
- Wrapped: CalibratedClassifierCV(cv=TimeSeriesSplit(n=3), method="sigmoid")
- Sample weights: `tournament_weight` column (friendlies=0.20, WC=1.0)

**Guarantee:**
- Hyperparameters: n_estimators=300, max_depth=4, learning_rate=0.05
- Outputs probabilities summing to 1.0
- Reproducible with random_state=42

---

### `evaluate(model, df_test, model_name="model") → dict`

**Output:**
```python
{
  model_name: {
    "accuracy": float,
    "log_loss": float,
    "brier_mean": float,
    "rps": float,
    "n_train": int,
    "n_test": int
  }
}
```

**Guarantee:**
- RPS (Ranked Probability Score): primary metric; lower is better
- Range: [0, 0.5]; random coin-flip = 0.25

---

### `rps_score(y_true_labels, y_proba) → float`

**Input:**
- `y_true_labels`: array of integers ∈ {0, 1, 2}
- `y_proba`: array of shape (n, 3) with probabilities

**Output:**
- Single float in [0, 0.5]

**Formula:**
```
RPS = (1/(K-1)) × Σ (CDF_pred_j − CDF_true_j)²
```

For K=3 outcomes, penalizes confident wrong predictions more than accuracy does.

---

## `src/poisson_model.py` — Goal Distribution Model

### `class PoissonModel`

#### `fit(df, weight_col="tournament_weight", n_iter=100) → self`

**Input:**
- `df`: DataFrame with `home_team, away_team, home_score, away_score`
- `weight_col`: column name for sample weights

**Guarantee:**
- Iterative coordinate descent: 100 iterations or until convergence
- Attack/defense parameters > 0
- Mean normalization: mean(attack) = mean(defense) = 1.0

#### `predict_goals(home, away, is_neutral=True, elo_diff=0.0) → tuple[float, float]`

**Output:**
- `(lambda_home, lambda_away)` — expected goal counts (both > 0)

**Guarantee:**
- Always returns positive lambdas
- Fallback for unknown teams: dataset mean goals

#### `scoreline_matrix(lam_h, lam_a) → np.ndarray`

**Output:**
- 2D array shape `(MAX_GOALS+1, MAX_GOALS+1)` with probabilities
- Sums to 1.0
- `MAX_GOALS = 7`

**Guarantee:**
- Computed as outer product of Poisson distributions
- Independent goals assumption

#### `aggregate_1x2(matrix) → tuple[float, float, float]`

**Output:**
- `(p_home, p_draw, p_away)` from scoreline matrix
- Sums to 1.0 ± 1e-4

**Guarantee:**
- Home win: upper triangle (home_score > away_score)
- Draw: diagonal (home_score == away_score)
- Away win: lower triangle (home_score < away_score)

---

## `src/ensemble.py` — Final Blend

### `DEFAULT_WEIGHTS: dict`
```python
DEFAULT_WEIGHTS = {"elo": 0.22, "poisson": 0.58, "xgb": 0.20}
```

### `class EnsembleModel`

#### `fit(df_train, df_all=None, xgb_model=None) → self`

**Guarantee:**
- Fits PoissonModel on df_train
- Loads or trains XGBoost if not provided
- Stores weights
- All three models (ELO, Poisson, XGB) loaded and ready

#### `predict_proba_match(home, away, elo_home, elo_away, is_neutral, xgb_features=None) → tuple[float, float, float]`

**Output:**
- `(p_home, p_draw, p_away)` ∈ [0, 1], sum = 1.0

**Guarantee:**
- ELO contribution: always computed (deterministic)
- Poisson contribution: always computed (deterministic)
- XGB contribution: if xgb_features provided and model available; else skipped
- Weights renormalized to account for missing components
- Clamped and rounded to 4 decimals

---

## `src/simulator.py` — Monte Carlo Simulator

### `class TournamentSimulator`

#### `simulate(n_iterations=5000, seed=42) → dict`

**Output:**
```python
{
  "team_win_probs": {
    "team_name": {
      "group_stage": float,  # prob of advancing from group
      "r16": float,          # prob of reaching R16
      "qf": float,           # prob of reaching QF
      "sf": float,           # prob of reaching SF
      "final": float,        # prob of reaching Final
      "champion": float      # prob of winning tournament
    },
    ...  # for all 48 teams
  },
  "champion_distribution": {
    "team_name": float,  # marginal prob of being champion
    ...
  }
}
```

**Guarantee:**
- Bracket: official 2026 structure (12 groups, 2 per group qualify, host auto-qualified? verify)
- Tiebreakers: goal diff, head-to-head, goals scored
- Penalties: 85% baseline conversion, weighted by match history
- Deterministic with seed=42 (reproducible)

---

## Failure Modes: What Always Works

1. **No API keys required** — Core works without DEEPSEEK_API_KEY, ANTHROPIC_API_KEY
2. **No network calls** — All computation is local
3. **Graceful missing features** — If a feature is NaN, it's dropped; XGBoost can handle missing data
4. **Fallback for unknown teams** — Poisson uses dataset mean goals
5. **XGB unavailable** — Ensemble re-weights to ELO+Poisson only (both still work)

---

## Testing Guarantees

All core contracts are validated by `pytest`:
```bash
pytest tests/test_features.py tests/test_model.py tests/test_poisson.py tests/test_ensemble.py tests/test_simulator.py -v
```

Expected: All tests pass, no network calls, no external dependencies.

---

**Updated:** 2026-06-17  
**Status:** Core model guaranteed stable
