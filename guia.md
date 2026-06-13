# guia.md — Roadmap de Empalme: Mundial Predictor 2026 × prompt.md (WorldCupPredictor 2026)

> **Fecha:** 2026-06-12
> **Propósito:** Definir cómo empalmar la visión de `prompt.md` (contratos, agentes LangGraph, FinOps, Poisson, ensemble) con el proyecto existente **sin reescribir lo que ya funciona**.

---

## 1. Diagnóstico inicial

### 1.1 Lo que el proyecto YA tiene (y prompt.md pide)

| Requisito de prompt.md | Estado actual | Ubicación |
|---|---|---|
| Motor ML tradicional (no LLM) | ✅ XGBoost + CalibratedClassifierCV | `src/model.py` |
| ELO baseline | ✅ Mejorado: K por torneo (WC=60, amistoso=20), margen `log(1+GD)`, home advantage +100 | `src/features.py` |
| Anti-leakage temporal | ✅ Split 3-way (train<2018 / calib=2018 / test=WC2022) + tests | `src/model.py`, `tests/test_model.py` |
| Walk-forward validation | ✅ Script con folds 2006→2022 + métrica RPS vs baseline ELO | `scripts/walk_forward_validation.py` |
| Monte Carlo | ✅ Doble: Python (validación) + TypeScript (5,000 sims client-side) | `src/simulator.py`, `frontend/src/lib/simulator.ts` |
| Bracket oficial 2026 | ✅ R32 slots FIFA + backtracking de mejores terceros | `src/simulator.py`, `simulator.ts` |
| Sistema multi-agente | ✅ Orchestrator (máx 2 agentes) + 6 especialistas, fail-safe sin API key | `src/agents/` |
| Tests | ✅ 58 tests (features, model, simulator, integrity, agents) | `tests/` |
| Dashboard | ✅ Superior a lo pedido: Next.js 15 + React 19 (multi-idioma, live tracking) + Streamlit demo | `frontend/`, `src/app.py` |
| Pesos por torneo | ✅ `tournament_weight` como sample_weight (WC=1.0, amistoso=0.20) | `src/features.py` |
| Datos históricos | ✅ `results.csv` (49,765 internacionales), shootouts, goalscorers | `data/raw/` |
| Fixture 2026 | ✅ JSON (48 equipos, 12 grupos) | `data/external/wc2026_fixture.json` |

### 1.2 Lo que prompt.md aporta y NO existe aún

| Componente | Valor | Esfuerzo |
|---|---|---|
| **Contratos formales** (`/contracts`: data, features, models, agents) | Alto — gobernanza y trazabilidad | Bajo (documentación) |
| **Modelo Poisson de goles** (scorelines, top-5 marcadores) | Alto — es el estándar para predicción de fútbol | Medio |
| **Ensemble calibrado** (ELO + Poisson + XGB con pesos configurables) | Alto — robustez y mejor RPS | Medio |
| **CostGuard + budget.yaml** (presupuesto LLM ≤ $50/mes) | Alto — los agentes LLM hoy no tienen control de gasto | Bajo |
| **Contratos Pydantic** para agentes (I/O validado) | Medio — hoy son dataclasses sin validación | Bajo |
| **Datos faltantes**: `fifa_ranking.csv`, `qualified_teams_2026.csv` | Medio — nuevas features (rank diff, qualification score) | Medio (conseguir datos) |
| **Modo B (predicción en vivo)**: cutoff = kickoff − ε por partido | Alto durante el Mundial | Medio |
| **Observabilidad JSONL** (`logs/*.jsonl`: runs, métricas, costos) | Medio — hoy solo logging a consola | Bajo |
| **HumanGateAgent** (aprobación humana ante leakage/degradación) | Bajo-Medio | Bajo |
| **LiteLLM + modelos baratos** (DeepSeek/Qwen local vía Ollama) | Medio — reduce costo de agentes LLM | Medio |
| **LangGraph** como orquestador de pipeline | Opcional — ver decisión D3 | Alto |
| **Features nuevas**: `days_since_last_match`, `confederation`, `fifa_rank_diff`, `qualification_score` | Medio — señal adicional para XGB | Medio |

### 1.3 Conflictos arquitectónicos y decisiones

| # | Conflicto | Decisión recomendada |
|---|---|---|
| **D1** | prompt.md: "LLM ≠ motor de predicción" vs. agentes actuales que ajustan probabilidades con `delta_P` | **Mantener ambos mundos separados.** El pipeline core (entrenar→evaluar→simular→exportar) NUNCA depende del LLM (ya es así: fail-safe delta=0). El `delta_P` queda como **capa opcional de enriquecimiento** (clamp 12%), desactivada por defecto en producción y activable por flag. El reporte siempre muestra prior vs adjusted. |
| **D2** | prompt.md pide estructura bronze/silver/gold + DuckDB | **Adoptar el concepto, no la reescritura.** Mapeo: `data/raw/` = bronze, `data/processed/` = silver+gold. Añadir metadatos de versión (hash, fecha, `dataset_version`) sin mover archivos. DuckDB: postergar — Parquet + pandas cubre el volumen actual (~50k filas). |
| **D3** | prompt.md pide LangGraph para orquestar el pipeline | **Postergar a Fase 6 (opcional).** El pipeline actual es un script secuencial simple que funciona; LangGraph aporta valor si se quiere el flujo condicional (validator→human gate, fallbacks). Adoptar primero lo barato: contratos Pydantic + estado compartido (`RunState`). Si se implementa, es para aprendizaje/portfolio, no por necesidad técnica. |
| **D4** | prompt.md pide Streamlit con 7 páginas | **No duplicar.** El frontend Next.js ya supera lo pedido. Añadir las vistas faltantes (métricas del modelo, data quality, FinOps) como tabs del Next.js. Streamlit queda como demo interna. |
| **D5** | prompt.md pide DeepSeek/Qwen local; el proyecto usa Claude API | **Abstraer el proveedor con LiteLLM.** Los agentes llaman `call_llm()` configurable vía `configs/litellm.yaml`. Default: modelo barato (Haiku o DeepSeek); local (Ollama+Qwen) como opción sin costo. CostGuard decide en runtime. |
| **D6** | prompt.md pide reestructurar `src/` (ingestion/validation/features/...) | **No reestructurar.** Los módulos actuales (`extractor`, `features`, `model`, `simulator`, `agents`) ya cumplen esos roles. Solo añadir: `src/validation.py` (contratos + anti-leakage) y `src/reporting.py`. |

### 1.4 Pendientes inmediatos (deuda de la Fase 2 — hacer antes que todo)

- [ ] **Re-ejecutar `python scripts/run_pipeline.py`**: las métricas en `data/processed/metrics.json` son previas al ELO mejorado y no incluyen RPS.
- [ ] **Ejecutar `python scripts/walk_forward_validation.py`** por primera vez: genera `walk_forward_results.json` (baseline de comparación para todo lo que sigue).
- [ ] **Re-ejecutar `python scripts/export_frontend_data.py`**: los JSONs del frontend usan el ELO viejo.
- [ ] Registrar las métricas resultantes en la sección 4 (Baseline) de esta guía.

---

## 2. Roadmap por fases

> Las Fases 0–2 (git, datos, calibración sin leakage, bracket oficial, ELO mejorado, walk-forward, multi-agente) están **completadas**. Esta guía continúa desde la Fase 3.

### Fase 3 — Gobernanza, contratos y FinOps *(prioridad: alta, esfuerzo: ~2-3 sesiones)*

Objetivo: trazabilidad y control de costos antes de añadir complejidad.

- [ ] **3.1 Contratos de datos** — `contracts/data_contracts.md`
  - Documentar schemas de bronze (`data/raw/*.csv`), silver (`wc_clean.csv`, `features.parquet`) y gold (`metrics.json`, JSONs del frontend).
  - Añadir a `run_pipeline.py`: guardar `data/processed/run_metadata.json` con `run_id`, hash de inputs, `dataset_version`, `feature_version`, `training_cutoff_date`.
- [ ] **3.2 Contratos de features** — `contracts/feature_contracts.md`
  - Documentar las 10 features actuales + reglas anti-leakage (rolling solo hacia atrás, ELO pre-match).
  - Listar las features candidatas de la Fase 4 con su contrato.
- [ ] **3.3 Contratos de modelos** — `contracts/model_contracts.md`
  - Documentar I/O y métricas de: ELO baseline, LogReg, XGB calibrado.
  - Definir contrato del Poisson y el ensemble (Fase 5) ANTES de implementarlos.
- [ ] **3.4 Contratos de agentes con Pydantic** — `contracts/agent_contracts.md` + `src/agents/contracts.py`
  - Migrar `MatchContext`/`AgentResult` de dataclasses a modelos Pydantic con validadores (`deltas suman 0`, `confidence ∈ [0,1]`, probabilidades ∈ [0,1]).
  - Los tests existentes de `tests/test_agents.py` deben seguir pasando sin cambios de API.
- [ ] **3.5 CostGuard + presupuesto** — `configs/budget.yaml` + `src/agents/cost_guard.py`
  - Reglas: `monthly_budget_usd: 50`, `daily_budget_usd: 2`, `max_llm_calls_per_pipeline: 5`, `max_tokens_per_request: 12000`.
  - El Orchestrator consulta CostGuard ANTES de cada llamada LLM; si bloquea → el agente usa su fallback determinístico o retorna delta=0.
  - Persistir gasto acumulado en `logs/llm_costs.jsonl`.
- [ ] **3.6 Observabilidad JSONL** — `src/observability.py`
  - `logs/pipeline_runs.jsonl`: run_id, timestamp, cutoff, versiones, métricas, warnings.
  - `logs/llm_costs.jsonl`: provider, model, tokens, costo estimado.
  - `logs/data_quality.jsonl`: nulos, duplicados, filas por capa.
- [ ] **3.7 Validación anti-leakage explícita** — `src/validation.py`
  - Función `assert_no_leakage(df_features, cutoff_date)` reutilizable: `feature_date <= cutoff < match_date`.
  - Integrarla en `run_pipeline.py` y `walk_forward_validation.py` (hoy el split es correcto pero implícito).
- [ ] **Tests nuevos**: contratos Pydantic rechazan deltas inválidos; CostGuard bloquea al superar presupuesto; leakage detectado → excepción.

### Fase 4 — Datos nuevos y features adicionales *(prioridad: alta, esfuerzo: ~2-3 sesiones)*

Objetivo: más señal para los modelos. Cada feature nueva se valida con walk-forward (entra solo si mejora RPS).

- [ ] **4.1 FIFA ranking** — `data/raw/fifa_ranking.csv` (Kaggle: ranking histórico FIFA)
  - Features: `fifa_rank_diff`, `fifa_points_diff` (rank vigente ANTES del partido — merge_asof por fecha).
- [ ] **4.2 Equipos clasificados 2026** — `data/external/qualified_teams_2026.csv`
  - Campos: team, confederation, qualification_method, points, GF/GC, host_flag, playoff_flag.
  - Features: `qualification_score` (puntos/partido en eliminatorias), `same_confederation`.
  - Si el dato no existe público aún → crear placeholder con schema + README de carga (regla 18 de prompt.md: no inventar datos).
- [ ] **4.3 Features de calendario** — derivables de `results.csv`, costo cero de datos:
  - `days_since_last_match_a/b` (descanso), `is_friendly/is_qualifier/is_world_cup` (one-hot del torneo).
- [ ] **4.4 Validación**: correr walk-forward con/sin cada grupo de features → tabla comparativa de RPS en `reports/feature_ablation.md`. Descartar lo que no mejore.

### Fase 5 — Poisson + Ensemble calibrado *(prioridad: alta, esfuerzo: ~3-4 sesiones)*

Objetivo: predicción de marcadores y ensemble robusto. **Es el mayor salto de calidad esperado.**

- [ ] **5.1 Modelo Poisson** — `src/poisson_model.py`
  - `fit_poisson_model`: fuerzas de ataque/defensa por equipo (regresión Poisson sobre goles, con peso temporal y por torneo).
  - `predict_expected_goals(team_a, team_b)` → `lambda_a, lambda_b`.
  - `build_scoreline_matrix(lambda_a, lambda_b)` → matriz P(marcador exacto) hasta 6×6.
  - `get_top_scorelines(n=5)` y agregación a 1X2 (suma de la matriz).
  - Mejora opcional: corrección Dixon-Coles para empates 0-0/1-1 (subestimados por Poisson independiente).
- [ ] **5.2 Ensemble** — `src/ensemble.py` + `configs/models.yaml`
  - `combine_model_probabilities(probs_elo, probs_poisson, probs_xgb, weights)` — pesos iniciales 40/30/30, configurables por YAML.
  - Re-calibración del ensemble en el holdout 2018 (sigmoid).
  - `compute_confidence_level` + `explain_prediction_drivers` (top features que empujan la predicción).
- [ ] **5.3 Evaluación cuatro-vías** en walk-forward: ELO vs Poisson vs XGB vs Ensemble → seleccionar por **log_loss + brier + RPS + calibración**, no por accuracy (regla 12 de prompt.md).
- [ ] **5.4 Integrar al simulador**: Monte Carlo puede muestrear marcadores exactos del Poisson (mejora tiebreakers por diferencia de gol, que hoy se aproximan).
- [ ] **5.5 Exportar al frontend**: top-5 marcadores probables por partido en el Predictor.
- [ ] **Tests**: lambdas > 0, matriz de marcadores suma ~1, ensemble suma 1, pesos desde config.

### Fase 6 — Agentic upgrade: LiteLLM, HumanGate y LangGraph opcional *(prioridad: media, esfuerzo: ~2-3 sesiones)*

- [ ] **6.1 LiteLLM como capa de proveedor** — refactor de `src/agents/specialists/_llm.py`
  - `call_llm(system, payload, tier)` donde tier ∈ {local, cheap, premium} se resuelve vía `configs/litellm.yaml`.
  - Soportar: Ollama+Qwen (local, $0), DeepSeek (barato), Claude Haiku/Sonnet (actual). El CostGuard fuerza downgrade de tier al acercarse al presupuesto.
- [ ] **6.2 HumanGateAgent** — `src/agents/human_gate.py`
  - Dispara ante: leakage detectado, degradación de métricas > umbral vs run anterior, sobrescritura de modelos, presupuesto excedido.
  - MVP: bloquea el pipeline y escribe `logs/human_gate_pending.json` con evento + acción recomendada; CLI `--approve` para continuar.
- [ ] **6.3 (Opcional) LangGraph** — `src/agents/graph.py`
  - Grafo: CostGuard → Collector → Validator → FeatureEngineer → Validator → Trainer → Simulator → Report → HumanGate.
  - Fallbacks del prompt.md: Trainer falla → ELO baseline; Simulator sin memoria → reducir n_sims; Report falla → reporte mínimo.
  - Justificación: aprendizaje/portfolio. El pipeline secuencial actual seguiría siendo el camino por defecto.
- [ ] **6.4 ReportAgent** — `src/reporting.py`
  - Genera `reports/prediction_report_<run_id>.md`: predicciones + drivers + incertidumbre + fecha de corte + modelo usado.
  - Lenguaje responsable (regla 13): "El modelo estima...", nunca "ganará seguro". LLM solo redacta sobre números ya calculados — no inventa.

### Fase 7 — Modo live y producto final *(prioridad: alta cuando empiece el Mundial, esfuerzo: ~2-3 sesiones)*

- [ ] **7.1 Modo B (predicción en vivo)** — `scripts/predict_live.py`
  - Por partido: `cutoff = kickoff − ε`; re-computa ELO/forma incluyendo partidos YA jugados del Mundial 2026; valida anti-leakage con `src/validation.py`.
  - Re-export incremental de JSONs del frontend tras cada jornada.
- [ ] **7.2 Vistas faltantes en Next.js** (no Streamlit — decisión D4):
  - Tab "Modelo": métricas, calibración, comparativa ensemble vs baselines.
  - Tab "Data Quality": filas por capa, nulos, fecha de corte, versión del dataset.
  - Tab "FinOps": gasto LLM acumulado vs presupuesto (lee `llm_costs.jsonl`).
- [ ] **7.3 Documentación final**:
  - `reports/methodology.md` — metodología completa (ELO mejorado, split temporal, walk-forward, ensemble).
  - `reports/model_card.md` — modelo, datos, métricas, limitaciones, uso responsable.
  - README actualizado con todos los comandos.

---

## 3. Qué NO hacer (descartado deliberadamente de prompt.md)

| Ítem de prompt.md | Razón del descarte |
|---|---|
| Reestructurar repo a `src/ingestion`, `src/validation/`, etc. | Los módulos actuales cumplen esos roles; mover archivos rompe imports, tests e historial sin ganancia funcional. |
| Streamlit con 7 páginas | El frontend Next.js ya lo supera; duplicar UI es deuda de mantenimiento. |
| DuckDB en el MVP | 50k filas en Parquet+pandas no lo justifican. Revisitar si el volumen crece 100×. |
| Renombrar datasets (`international_results.csv` → ya existe como `results.csv`) | Mismo dataset de Kaggle; el contrato de datos (3.1) documenta el mapeo de nombres. |
| Notebooks 01–06 nuevos | Existen `01_eda` y `02_features`; los análisis nuevos (Poisson, ensemble) van como scripts reproducibles + secciones en methodology.md (prioridad de prompt.md: scripts > notebooks). |
| LLM como parte obligatoria del pipeline | Regla central de prompt.md y diseño actual: todo corre sin API key. Se mantiene. |

---

## 4. Baseline de métricas (para medir progreso)

> Actualizar esta tabla tras cada fase. Métrica primaria: **RPS** (menor = mejor).

| Hito | Modelo | Accuracy | Log-loss | Brier | RPS | Fecha |
|---|---|---|---|---|---|---|
| Etapa A — ELO mejorado (test WC 2022, 64 partidos) | logistic_regression | 0.500 | 1.063 | 0.2045 | **0.2202** | 2026-06-12 |
| Etapa A — ELO mejorado (test WC 2022, 64 partidos) | xgb_v1 | 0.484 | 1.018 | 0.2013 | **0.2148** | 2026-06-12 |
| Etapa A — ELO mejorado (test WC 2022, 64 partidos) | xgb_calibrated | 0.484 | 1.025 | 0.2029 | **0.2167** | 2026-06-12 |
| **Walk-forward GLOBAL (5 Mundiales, 320 partidos)** | **XGB** | — | — | — | **0.1986** | **2026-06-12** |
| **Walk-forward GLOBAL (5 Mundiales, 320 partidos)** | **ELO-only baseline** | — | — | — | **0.1979** | **2026-06-12** |
| ⚠️ GATE A2 ACTIVADO: XGB -0.4% vs ELO-only → ensemble parte de ELO como componente dominante | | | | | | |
| **Etapa B — Walk-forward 4 modelos (5 Mundiales, 320 partidos)** | **ELO-only** | — | — | — | **0.1966** | **2026-06-12** |
| **Etapa B — Walk-forward 4 modelos** | **Poisson** | — | — | — | **0.2065** | **2026-06-12** |
| **Etapa B — Walk-forward 4 modelos** | **XGBoost** | — | — | — | **0.1986** | **2026-06-12** |
| **🏆 Etapa B — Walk-forward 4 modelos** | **Ensemble (35%ELO+35%Poisson+30%XGB)** | — | — | — | **0.1958 ← MEJOR** | **2026-06-12** |
| Etapa B — Poisson (test WC 2022, 64 partidos) | poisson_model | 0.484 | 1.063 | — | **0.2179** | 2026-06-12 |
| Etapa B — features nuevas (ablation) | *pendiente* | | | | | |

---

## 5. Riesgos

1. **Datos 2026 no disponibles**: `qualified_teams_2026.csv` con stats de eliminatorias puede no existir consolidado → plan: construirlo desde `results.csv` filtrando torneos de clasificación 2024-2025.
2. **Overfitting al test de 64 partidos**: WC 2022 es pequeño; toda decisión de features/modelos debe validarse con walk-forward (5 mundiales, ~320 partidos), no solo con el test final.
3. **Delta_P de agentes LLM sin validación histórica**: no hay forma de backtest de los ajustes de agentes → mantenerlos opt-in y con clamp 12% (decisión D1); registrar prior vs adjusted en logs para auditoría futura.
4. **Presupuesto LLM**: 2,256 pares × agentes LLM rompería los $50 → los agentes solo se invocan on-demand (partido por partido en UI/CLI), nunca en batch del pipeline. CostGuard (3.5) lo garantiza.
5. **Drift entre simulador Python y TypeScript**: dos implementaciones del mismo Monte Carlo → añadir test de paridad (mismas probs de entrada → distribuciones equivalentes) en Fase 5.4.

---

## 6. Orden de ejecución recomendado

```text
AHORA      → Pendientes 1.4 (re-correr pipeline + walk-forward + export)
Fase 3     → Contratos + CostGuard + observabilidad        (gobernanza barata, alto valor)
Fase 4     → FIFA ranking + features calendario            (señal nueva, validada por walk-forward)
Fase 5     → Poisson + Ensemble                            (mayor salto de calidad esperado)
Fase 6     → LiteLLM + HumanGate (+ LangGraph opcional)    (madurez agentic)
Fase 7     → Modo live + vistas Next.js + docs finales     (listo para el Mundial)
```

**Criterio de aceptación global** (de prompt.md §21): ejecutable 100% local sin LLM pago, contratos documentados, presupuesto ≤ $50 protegido, predicción basada en ML/estadística, cero leakage temporal, trazabilidad completa de datasets/features/modelos/simulaciones, tests en verde.
