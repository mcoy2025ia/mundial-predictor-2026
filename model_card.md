# Model Card — Mundial Predictor 2026

## Model Summary

**Task:** Multi-class probabilistic prediction of football match outcomes (home win / draw / away win)  
**Primary use:** FIFA World Cup 2026 match probability estimation and tournament simulation  
**Output:** Calibrated probability triple (p_home, p_draw, p_away) summing to 1.0

---

## Model Details

| Component | Description |
|---|---|
| Base model | XGBoost multi-class softmax (`xgb_calibrated`) |
| Calibration | `CalibratedClassifierCV` with `TimeSeriesSplit(n=3)` + sigmoid |
| Ensemble | ELO (22%) + Poisson (58%) + XGB (20%) — weighted blend |
| Goal model | Dixon-Robinson Poisson (iterative attack/defense estimation) |
| ELO system | Custom — K varies by tournament (WC=60, friendly=20), margin multiplier log(1+|GD|), home advantage +100 |
| Temporal split | Train < 2018 · Calibration = 2018 · Test = WC 2022 (never in training) |
| Training data | 49,765 internationals (1872–present), weighted by tournament importance |
| Primary metric | **RPS (Ranked Probability Score)** — lower is better; penalizes confident wrong predictions |

---

## Performance

### Test Set: Qatar 2022 (64 matches, held-out)

| Model | Accuracy | Log-loss | Brier | RPS |
|---|---|---|---|---|
| Logistic Regression (baseline) | 50.0% | 1.063 | 0.205 | 0.220 |
| XGBoost v1 (no calibration) | 48.4% | 1.018 | 0.201 | 0.215 |
| XGBoost calibrated | 48.4% | 1.025 | 0.203 | **0.217** |
| Poisson (Dixon-Robinson) | — | — | — | 0.218 |

### Walk-Forward Validation (5 World Cups, 64 matches each, n=320)

| WC | ELO | Poisson | XGB | **Ensemble** | Winner |
|---|---|---|---|---|---|
| 2006 | 0.1609 | 0.1787 | 0.1614 | 0.1626 | ELO |
| 2010 | 0.2022 | 0.2072 | 0.2052 | **0.1995** | Ensemble |
| 2014 | 0.1925 | 0.2185 | 0.1973 | 0.1984 | ELO |
| 2018 | 0.2050 | 0.2099 | 0.2141 | **0.2043** | Ensemble |
| 2022 | 0.2222 | 0.2181 | 0.2152 | **0.2142** | Ensemble |
| **OVERALL** | 0.1966 | 0.2065 | 0.1986 | **0.1958** | **Ensemble** |

The Ensemble beats all individual models globally (RPS 0.1958). ELO dominates in early tournaments when training data is sparse; the Ensemble takes over as data accumulates.

### Feature Ablation (B3 — Rest Days)

`home_days_rest` / `away_days_rest` were tested via walk-forward ablation. Global RPS worsened by +0.0005 — rejected. ELO already captures fitness implicitly; calendar features added noise rather than signal.

---

## Features

| Feature | Description |
|---|---|
| `elo_diff` | ELO_home − ELO_away (pre-match) |
| `elo_home`, `elo_away` | Absolute ELO ratings |
| `home_goals_scored_avg5` | Rolling avg goals scored (last 5 matches) |
| `home_goals_conceded_avg5` | Rolling avg goals conceded (last 5 matches) |
| `away_goals_scored_avg5` | Same for away team |
| `away_goals_conceded_avg5` | Same for away team |
| `h2h_home_win_pct` | Head-to-head win rate (all-time) |
| `is_neutral` | 0 if home nation is a host country at home venue |
| `wc_experience_diff` | Difference in WC appearances |

All features are computed strictly before the match (no leakage). Rolling statistics use `shift(1)` over the full historical timeline.

---

## Training Data

- **Source:** Kaggle `martj42/international-football-results-from-1872-to-2017` (updated to 2026)
- **Coverage:** 49,477 internationals from November 1872 to June 2026
- **WC matches in dataset:** 1,036 (tournament_weight = 1.0)
- **Sample weighting:** `tournament_weight` from 0.20 (friendlies) to 1.0 (WC). Friendlies reduce their influence by 5×.
- **ELO initialization:** All teams start at 1500. The chronological pass naturally differentiates strong from weak teams before the first WC.

---

## Limitations

1. **Historical bias:** The model reflects historical international football patterns. Teams with few historical records (debutants, regional outsiders) receive less informative priors.

2. **No real-time injury/squad data:** The base model does not account for player availability. The multi-agent system adds optional LLM-based injury adjustments (capped at ±12% total shift), but this requires manual context injection.

3. **Calibration degrades over time:** Calibration was fitted on WC 2018 data. After significant football landscape changes, re-calibration is needed.

4. **Draws are notoriously hard:** Draw probability estimates (≈ 27% across all models) remain the least accurate outcome. No model tested reduces draw RPS substantially.

5. **Knockout stage:** Predictions use group-stage ELO + form. The model does not adapt to within-tournament momentum beyond what the live update pipeline captures.

6. **Not a betting tool:** Probabilities are calibrated for forecasting, not for gambling. Expected value against bookmaker lines is not guaranteed.

---

## Intended Use

- **Primary:** Public display of match probabilities during FIFA World Cup 2026 on the companion web application
- **Secondary:** Tournament simulation (Monte Carlo, 5,000 iterations), champion probability distribution
- **Out of scope:** Real-money wagering, individual player performance prediction, non-WC tournament prediction without retraining

---

## Responsible Use

- Probabilities are model outputs with uncertainty. A 70% win probability does not mean the team will win.
- The model is updated after each match day, not in real time during a match.
- Historical data reflects outcomes; it does not capture tactical evolution, manager changes, or recent form beyond the last 5 matches.
- Championship probability distributions are simulations, not forecasts. Results are sensitive to group-stage outcomes.

---

## Versioning

| Date | Version | Notes |
|---|---|---|
| 2026-06-12 | v1.0 | Initial release: XGB calibrated + walk-forward validated |
| 2026-06-12 | v1.1 | Added Poisson (Dixon-Robinson) + Ensemble |
| 2026-06-17 | v1.3 | Serving aligned to active Ensemble weights 22/58/20 |
| 2026-06-13 | v1.2 | Live update pipeline operational; ablation confirmed rest-day features unhelpful |

---

*Generated by the Mundial Predictor 2026 pipeline. For methodology details see `methodology.md`.*
