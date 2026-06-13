# Module Contracts — Mundial Predictor 2026

Interfaces públicas de los módulos principales. Cambiar una firma listada aquí
sin actualizar los contratos equivale a romper la API del proyecto.

---

## `src/extractor.py`

```python
def load_results() -> pd.DataFrame
    # → columnas: date, home_team, away_team, home_score, away_score, tournament, city, country, neutral
    # → date ya parseada como datetime
    # → nombres normalizados via load_former_names()
    # → ordena por fecha ASC

def filter_world_cups(df: pd.DataFrame) -> pd.DataFrame
    # → filtra tournament == "FIFA World Cup"
    # → preserva todas las columnas de entrada

def add_outcome(df: pd.DataFrame) -> pd.DataFrame
    # → añade columna outcome: "home_win" | "draw" | "away_win"
    # → requiere home_score y away_score no nulos

def load_former_names() -> dict[str, str]
    # → mapa {nombre_histórico: nombre_actual}
    # → cierre transitivo garantizado
```

---

## `src/features.py`

```python
def compute_elo_ratings(df_all: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float]]
    # → retorna (df_con_elo_home_elo_away_elo_diff, ratings_finales)
    # → df_all debe estar ordenado por fecha (load_results() garantiza esto)
    # → ratings_finales: {team: elo_float}, todos los equipos que aparecen en df_all
    # → NO modifica df_all in-place

def build_feature_matrix(df_all, df_wc, use_all_matches=True) -> pd.DataFrame
    # → retorna feature matrix con FEATURE_COLS + date + year + home_team + away_team + outcome + tournament_weight
    # → uso_all_matches=True: ~49k filas (recomendado para entrenamiento)
    # → uso_all_matches=False: solo WC (~966 filas)
    # → garantía de no leakage: shift(1) en rolling stats, acumulación forward en H2H y experiencia

def get_tournament_weight(tournament: str) -> float
    # → [0.20, 1.0]; default=0.35 para torneos no mapeados

def compute_rest_days(df_all, df_target, cap_days=365) -> pd.DataFrame
    # → añade home_days_rest y away_days_rest a df_target
    # → NOT incluida en FEATURE_COLS (ablation: no mejora RPS)
    # → disponible como utilidad para predict_live

def compute_current_form(df_all, teams=None, n=5) -> dict[str, dict[str, float]]
    # → retorna {team: {goals_scored: x, goals_conceded: y}} usando los últimos n partidos
    # → NO usa shift(1): incluye último partido (uso para serving, no entrenamiento)
```

---

## `src/model.py`

```python
FEATURE_COLS: list[str]
# = ["elo_diff", "elo_home", "elo_away",
#    "home_goals_scored_avg5", "home_goals_conceded_avg5",
#    "away_goals_scored_avg5", "away_goals_conceded_avg5",
#    "h2h_home_win_pct", "is_neutral", "wc_experience_diff"]

LABEL_MAP: dict[str, int]
# = {"home_win": 0, "draw": 1, "away_win": 2}

def temporal_split(df, test_year=2022, calib_year=2018) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]
    # → retorna (train, calib, test)
    # → train: year < calib_year
    # → calib: year == calib_year
    # → test: year == test_year (si test_year > calib_year, incluye calib en train)
    # → NUNCA mezcla futuro en train

def train(df_train, model_type="xgb_calibrated", df_calib=None) -> sklearn estimator
    # → model_type: "baseline" | "xgb" | "xgb_calibrated"
    # → xgb_calibrated requiere df_calib para calibración temporal

def evaluate(model, df_test, model_name="model") -> dict[str, dict]
    # → retorna {model_name: {accuracy, log_loss, brier_mean, rps, n_train, n_test}}

def rps_score(y_true_labels, y_proba) -> float
    # → Ranked Probability Score; lower = better; range [0, 0.5]
```

---

## `src/poisson_model.py`

```python
class PoissonModel:
    MAX_GOALS: int = 7

    def fit(self, df, weight_col="tournament_weight", n_iter=100) -> PoissonModel
        # → df debe tener: home_team, away_team, home_score, away_score
        # → modifica self.attack_, self.defense_, self.mean_goals_home, self.mean_goals_away

    def predict_goals(self, home, away, is_neutral=True, elo_diff=0.0) -> tuple[float, float]
        # → retorna (lambda_home, lambda_away); ambas > 0
        # → fallback para equipos desconocidos: mean_goals del dataset

    def scoreline_matrix(self, lam_h, lam_a) -> np.ndarray
        # → shape (MAX_GOALS+1, MAX_GOALS+1); suma = 1.0

    def aggregate_1x2(self, matrix) -> tuple[float, float, float]
        # → retorna (p_home, p_draw, p_away); suma = 1.0 ± 1e-4

    def top_scorelines(self, matrix, n=5) -> list[dict]
        # → lista de n dicts {"home": int, "away": int, "prob": float}
        # → ordenada por prob descendente
```

---

## `src/ensemble.py`

```python
DEFAULT_WEIGHTS: dict = {"elo": 0.35, "poisson": 0.35, "xgb": 0.30}

class EnsembleModel:
    def fit(self, df_train, df_all=None, xgb_model=None) -> EnsembleModel
        # → entrena Poisson; carga o entrena XGB; almacena pesos
        # → df_all necesario para Poisson (requiere home_score/away_score)

    def predict_proba_match(self, home, away, elo_home, elo_away, is_neutral,
                            xgb_features=None) -> tuple[float, float, float]
        # → retorna (p_home, p_draw, p_away); suma = 1.0 ± 1e-4
        # → si xgb_features es None y XGB disponible: usa XGB con ELO+form=defaults
```

---

## `src/agents/orchestrator.py`

```python
class Orchestrator:
    def predict(self, ctx: MatchContext) -> OrchestratorOutput
        # → llama máx 2 agentes determinados por _route(ctx)
        # → si CostGuard agotado: salta agentes LLM, usa solo determinísticos
        # → OrchestratorOutput.adjusted: probabilidades post-delta, suma = 1.0
        # → delta total clampeado a ±12% de shift máximo
        # → NUNCA lanza excepción: todos los agentes usan safe_analyze()
```

---

## `src/cost_guard.py`

```python
class CostGuard:
    def check_and_record(self, model, n_tokens, agent_name="", match="") -> None
        # → verifica límites ANTES de la llamada LLM
        # → lanza BudgetExceeded si daily/monthly/run limit alcanzado
        # → appenda entrada a logs/llm_costs.jsonl si pasa

    def run_calls_remaining(self) -> int
        # → cuántas llamadas LLM quedan en este run (se resetea al crear nueva instancia)

class BudgetExceeded(Exception): ...

def get_guard() -> CostGuard
    # → singleton de proceso; leer configs/budget.yaml al crear
```

---

## `src/pipeline_logger.py`

```python
def append_run(run_type, duration_s, status="ok", error=None,
               metrics=None, artifacts=None, meta=None) -> None
    # → appenda línea JSONL a logs/pipeline_runs.jsonl

@contextmanager
def run_context(run_type, artifacts=None, meta=None) -> Generator[dict, None, None]
    # → mide tiempo, captura excepciones, llama append_run al salir
    # → el bloque puede escribir ctx["metrics"] y ctx["meta"]
    # → si el bloque lanza, status="error", la excepción se re-lanza

def read_runs(last_n=20) -> list[dict]
    # → últimos N runs del ledger

def summary() -> None
    # → imprime tabla de últimos 10 runs en stdout
```
