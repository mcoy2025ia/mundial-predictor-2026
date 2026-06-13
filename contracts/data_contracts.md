# Data Contracts — Mundial Predictor 2026

Schemas y garantías de los archivos de datos que el pipeline produce y consume.
Un contrato roto debe fallar ruidosamente (AssertionError o ValueError), no silenciosamente.

---

## Archivos de entrada (`data/raw/`)

### `international_results.csv`
Fuente: Kaggle `martj42/international-football-results-from-1872-to-2017` (actualizado).

| Columna | Tipo | Garantía |
|---|---|---|
| `date` | date (YYYY-MM-DD) | No nulo, ordenable cronológicamente |
| `home_team` | str | Normalizado vía `load_former_names()` al cargar |
| `away_team` | str | Normalizado vía `load_former_names()` al cargar |
| `home_score` | float (int nullable) | ≥ 0 o NaN (partido no jugado) |
| `away_score` | float (int nullable) | ≥ 0 o NaN (partido no jugado) |
| `tournament` | str | No nulo; se mapea a `K_BY_TOURNAMENT` y `TOURNAMENT_WEIGHTS` |
| `city` | str | Puede ser vacío |
| `country` | str | Puede ser vacío |
| `neutral` | bool | True = sede neutral; False = local juega en casa |

**Tamaño esperado:** ~49,000–52,000 filas.

---

## Archivos de estado en vivo (`data/external/`)

### `wc2026_live_results.csv`
Resultados del Mundial 2026 ya jugados. Se actualiza manualmente con `predict_live.py --add-result`.

| Columna | Tipo | Garantía |
|---|---|---|
| `date` | date (YYYY-MM-DD) | No nulo; solo fechas del torneo (11 jun – 19 jul 2026) |
| `home_team` | str | Nombre canónico del dataset (ej: "United States", no "USA") |
| `away_team` | str | Nombre canónico del dataset |
| `home_score` | int | ≥ 0 |
| `away_score` | int | ≥ 0 |
| `tournament` | str | Siempre "FIFA World Cup" |
| `city` | str | Ciudad de la sede |
| `country` | str | "USA/Mexico/Canada" |
| `neutral` | bool | Derivado de `_is_neutral()` en predict_live.py |

**Anti-duplicados:** la CLI no verifica duplicados; responsabilidad del operador.

### `wc2026_fixture.json`
Fixture oficial del torneo. Formato plano:

```json
{
  "name": "FIFA World Cup 2026",
  "matches": [
    {
      "round":  "Matchday 1",
      "date":   "2026-06-11",
      "time":   "13:00 UTC-6",
      "team1":  "Mexico",
      "team2":  "South Africa",
      "group":  "Group A",
      "ground": "Mexico City"
    }
  ]
}
```

- Los partidos de knockout usan códigos placeholder (`W101`, `1A`, etc.) hasta resolverse.
- `time` siempre en formato `"HH:MM UTC±X"`.

---

## Artefactos procesados (`data/processed/`)

### `features.parquet`
Feature matrix completa. Una fila por partido internacional con score disponible.

| Columna | Tipo | Garantía |
|---|---|---|
| `date` | datetime | Ordenable, no nulo |
| `year` | int | Derivado de `date.year` |
| `home_team`, `away_team` | str | Nombres normalizados |
| `outcome` | str | "home_win" \| "draw" \| "away_win" |
| `tournament_weight` | float | [0.20, 1.0] — WC=1.0, friendly=0.20 |
| `elo_diff` | float | `elo_home - elo_away` (pre-match) |
| `elo_home`, `elo_away` | float | [800, 2200] aprox. |
| `home_goals_scored_avg5` | float | ≥ 0 |
| `home_goals_conceded_avg5` | float | ≥ 0 |
| `away_goals_scored_avg5` | float | ≥ 0 |
| `away_goals_conceded_avg5` | float | ≥ 0 |
| `h2h_home_win_pct` | float | [0, 1] |
| `is_neutral` | int | 0 o 1 |
| `wc_experience_diff` | int | Entero, puede ser negativo |

**Garantía de no leakage:** cada feature se computa con `shift(1)` o estado acumulado ANTES del partido.  
**Tamaño esperado:** ~49,000–52,000 filas, 16 columnas.

### `elo_current.json`
```json
{ "Brazil": 2082.4, "France": 2045.1, ... }
```
Ratings ELO finales tras el último partido cargado. Ordenado descendente por rating.

### `metrics.json`
```json
{
  "xgb_calibrated": {
    "accuracy": 0.4844,
    "log_loss": 1.025,
    "brier_mean": 0.203,
    "rps": 0.2167,
    "n_train": 41635,
    "n_test": 64,
    "n_calib": 929
  }
}
```

### `walk_forward_results.json`
```json
{
  "2006": { "n_train": 30064, "n_test": 64, "rps_elo": 0.1609, "rps_ensemble": 0.1626, "best_model": "elo" },
  "overall": { "rps_elo": 0.1966, "rps_ensemble": 0.1958, "best_model": "ensemble", "n_predictions": 320 }
}
```

### `live_predictions.json`
```json
{
  "generated_at": "2026-06-13T14:30:00",
  "mode": "live",
  "live_results_used": 4,
  "n_predictions": 72,
  "predictions": [
    {
      "home_team": "Mexico", "away_team": "South Africa",
      "p_home": 0.722, "p_draw": 0.180, "p_away": 0.098,
      "is_neutral": false,
      "kickoff": "2026-06-11T19:00:00",
      "model": "xgb_calibrated_live",
      "stage": "group", "group": "Group A", "venue": "Mexico City", "round": "Matchday 1"
    }
  ]
}
```

---

## Artefactos del frontend (`frontend/public/data/`)

### `predictions.json`
Diccionario indexado por `"HomeTeam|AwayTeam"` con 2,256 pares (todos los equipos vs todos).

```json
{
  "Brazil|France": {
    "home_win": 0.38, "draw": 0.28, "away_win": 0.34,
    "ensemble_home_win": 0.40, "ensemble_draw": 0.27, "ensemble_away_win": 0.33,
    "top_scorelines": [{"home": 1, "away": 1, "prob": 0.12}, ...],
    "lambda_home": 1.42, "lambda_away": 1.28
  }
}
```

**Garantías:**
- `home_win + draw + away_win = 1.0 ± 0.001`
- `ensemble_home_win + ensemble_draw + ensemble_away_win = 1.0 ± 0.001`
- Todas las probabilidades en [0, 1]
- `top_scorelines` tiene exactamente 5 entradas ordenadas por `prob` descendente

---

## Logs (`logs/`)

### `pipeline_runs.jsonl`
Una línea JSON por ejecución de `run_pipeline.py` o `predict_live.py`.

```json
{
  "ts": "2026-06-13T14:30:00.123+00:00",
  "run_type": "full_pipeline",
  "duration_s": 42.3,
  "status": "ok",
  "error": null,
  "metrics": { "xgb_rps": 0.2167, "xgb_accuracy": 0.4844, "n_train": 41635, "n_test": 64 },
  "artifacts": ["data/processed/features.parquet", "models/xgb_calibrated.pkl"],
  "meta": { "n_all_matches": 49765, "n_wc_matches": 1036 }
}
```

**run_type values:** `full_pipeline` | `live_update` | `export`

### `llm_costs.jsonl`
Una línea JSON por llamada LLM de los agentes especialistas.

```json
{
  "ts": "2026-06-13T14:35:00.456+00:00",
  "model": "claude-haiku-4-5-20251001",
  "tokens": 847,
  "cost_usd": 0.000212,
  "agent": "IntMatch-Analytics-Pro",
  "match": "Brazil vs France"
}
```

Gestionado por `src/cost_guard.py`. Límites: $2/día · $50/mes · 5 llamadas/run.
