# Retrospective — Mundial Predictor 2026

**Tournament:** FIFA World Cup 2026 (June 11 – July 19, 2026)  
**Fill in:** After the final (July 19+)

---

## 1. Model Baseline

| Model | Walk-Forward RPS | Qatar 2022 RPS | WC 2026 RPS |
|---|---|---|---|
| ELO baseline | 0.1966 | — | _fill_ |
| XGBoost calibrated | 0.2167 | — | _fill_ |
| Ensemble 35/35/30 | **0.1958** | — | _fill_ |
| Human/market average | — | — | _fill_ |

> **Primary metric:** RPS (lower = better). Benchmark: naive 1/3 uniform = 0.222.

---

## 2. WC 2026 Results vs Predictions

| Round | N matches | Ensemble correct (mode) | RPS |
|---|---|---|---|
| Group stage | 48 | _fill_ | _fill_ |
| Round of 32 | 16 | _fill_ | _fill_ |
| Round of 16 | 8 | _fill_ | _fill_ |
| Quarter-finals | 4 | _fill_ | _fill_ |
| Semi-finals | 2 | _fill_ | _fill_ |
| Final | 1 | _fill_ | _fill_ |
| **Total** | **79** | **_fill_** | **_fill_** |

---

## 3. Champion Probability at Tournament Start

| Team | Pre-tournament P(champion) | Result |
|---|---|---|
| _Top 5 from simulator_ | — | _fill_ |

---

## 4. What Worked

- [ ] Ensemble (ELO + Poisson + XGB) beat pure ELO
- [ ] Temporal calibration (no leakage, no random K-fold)
- [ ] Tournament weights in training (WC=1.0, friendly=0.20)
- [ ] Host advantage detection (USA/Mexico/Canada is_neutral=0)
- [ ] Live update pipeline (predict_live.py)

---

## 5. What Didn't Work / Surprises

_Write after tournament. Examples: upsets the model missed, calibration drift, live update failures, deploy issues._

---

## 6. Feature Ablation Post-Tournament

| Feature | Was it worth adding? | Evidence |
|---|---|---|
| `days_since_last_match` | Rejected pre-tournament (gate +0.0005) | _reassess with 2026 data_ |
| FIFA ranking integration | Not built (Etapa C backlog) | _fill_ |
| Weather/altitude (FIFA-Regs agent) | Built, rarely triggered | _fill_ |

---

## 7. Operational Notes

- Live results updated manually via `predict_live.py --add-result`; automation status: _fill_
- LLM agent cost total (from `logs/llm_costs.jsonl`): $____ / budget $50
- Pipeline runs logged in `logs/pipeline_runs.jsonl`: ____ runs, ____ errors
- Deploy platform: _fill_ | Uptime: ___% | Peak traffic: ___ req/day

---

## 8. Next Tournament (Euros 2028 / WC 2030) Backlog

- [ ] FIFA ranking features (ablate with 2026 data first)
- [ ] Automated live result ingestion (football-data.org API)
- [ ] Injury data pipeline (Roster agent as real feature, not just LLM)
- [ ] Scoreline predictions exposed in frontend (Poisson top-5 already computed)
- [ ] Walk-forward including WC 2026 in folds

---

_Template created 2026-06-13. Fill in after July 19._
