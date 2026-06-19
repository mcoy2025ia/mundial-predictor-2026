# Mundial Predictor 2026 - ML Validation Brief

## Validation Strategy

The project uses temporal validation because football data is time-series data. Random K-fold splits would leak future information into past predictions.

Documented split:
- Train: historical matches before 2018.
- Calibration: 2018 World Cup window.
- Test: Qatar 2022, 64 matches retained.

Walk-forward validation aggregates five World Cups for a broader view.

## Primary Metric

RPS, Ranked Probability Score, is the primary metric. Lower is better. It measures the quality of the full probability distribution across home win, draw and away win.

Why RPS matters:
- Accuracy hides whether a model was overconfident.
- RPS penalizes confident wrong predictions.
- Tournament simulation needs calibrated probabilities, not only winners.

## Documented Metrics

From `model_card.md` and `methodology.md`:

| Measurement | Value |
|---|---|
| Qatar 2022 test set | 64 matches |
| XGBoost calibrated RPS on Qatar 2022 | 0.217 |
| Walk-forward sample | 5 World Cups, 320 predictions |
| Ensemble global RPS | 0.1958 |
| Current ensemble weights | 22% ELO, 58% Poisson, 20% XGBoost |

## Dataset Count Note

The repository contains more than one count because different artifacts count different subsets:

- Historical coverage references about 49,477 international matches.
- Feature/model artifacts reference 49,765 scored rows/features.

External communication should use `49k+ historical internationals` unless the exact artifact and definition are named.

## Claims To Avoid

Avoid:
- Guaranteed winner claims.
- Betting-style confidence language.
- Comparing directly with bookmakers unless the comparison method is documented.
- Treating agent output as validated model performance.

Prefer:
- Probability distribution.
- Calibrated model output.
- Scenario simulation.
- Evidence-backed limitations.

## Limitations

- World Cup test sets are small.
- Draw prediction remains difficult.
- Late injuries and lineup changes may not be fully captured.
- ELO can lag behind sudden team-level changes.
- LLM narratives depend on the quality and freshness of injected context.
