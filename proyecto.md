# proyecto.md — Mundial Predictor 2026: Definición, Calificación y Plan de Foco

> **Fecha:** 2026-06-12 · **Contexto crítico:** el Mundial 2026 empezó AYER (11 jun) y termina el 19 de julio. El proyecto tiene 37 días de ventana de relevancia.
> **Documentos hermanos:** `guia.md` (roadmap técnico de empalme), `CLAUDE.md` (arquitectura para desarrollo).

---

## 1. ¿Qué es este proyecto?

**Mundial Predictor 2026** es un sistema de predicción probabilística para la Copa del Mundo 2026: un pipeline de ML en Python que entrena sobre 49,765 partidos internacionales históricos (1872–2026) y produce probabilidades calibradas de resultado (1X2) para cada partido del torneo, más una simulación Monte Carlo del torneo completo que estima la probabilidad de cada selección de avanzar por ronda y salir campeona.

### ¿Qué hace, concretamente?

```text
Datos históricos (Kaggle) ──► ELO custom (K por torneo, margen, localía)
                          ──► Features (forma, H2H, experiencia mundialista)
                          ──► XGBoost calibrado (split temporal, sin leakage)
                          ──► 2,256 pares de equipos pre-calculados
                                  ├──► Web Next.js: predictor + simulador Monte Carlo en el navegador
                                  └──► Simulación de torneo: bracket oficial FIFA, mejores terceros, penales
```

### ¿Para qué sirve? (en orden de prioridad)

1. **Producto**: una web que durante el torneo muestra probabilidades **honestas y calibradas** por partido y proyecciones de campeón actualizadas jornada a jornada — la alternativa con método frente a la opinología de TV.
2. **Portfolio técnico**: demuestra dominio de ML temporal (anti-leakage, calibración, walk-forward), arquitectura local-first de bajo costo, y diseño agentic con control de gasto.
3. **Laboratorio de aprendizaje**: banco de pruebas para técnicas del stack moderno (ensembles, Poisson, agentes LLM, FinOps).

### ¿Qué NO es?

- ❌ No es una herramienta de apuestas ni recomienda apostar.
- ❌ No usa LLMs como motor de predicción (el LLM solo enriquece contexto y redacta reportes).
- ❌ No es un SaaS multiusuario ni necesita infraestructura cloud compleja.

---

## 2. Entregables

### E1 — Núcleo predictivo *(estado: funcional, calidad por validar)*
| Artefacto | Criterio de aceptación | Estado |
|---|---|---|
| Pipeline reproducible (`run_pipeline.py`) | 1 comando → datos→features→modelos→métricas | ✅ |
| Modelo XGBoost calibrado | RPS mejor que ELO-only en walk-forward 2006–2022 | ⚠️ **sin medir** — pendiente correr walk-forward |
| ELO custom | K por torneo + margen + localía, tests en verde | ✅ |
| Validación walk-forward | `walk_forward_results.json` con 5 folds | ⚠️ script listo, **nunca ejecutado** |

### E2 — Producto web *(estado: funcional, desactualizado)*
| Artefacto | Criterio de aceptación | Estado |
|---|---|---|
| Web Next.js (predictor, grupos, simulador, live) | Desplegada y consultable durante el torneo | ✅ código / ⚠️ JSONs con ELO viejo |
| Simulador Monte Carlo client-side | Bracket oficial 2026, 5,000 sims < 1s | ✅ |
| Modo live (jornada a jornada) | Probs re-calculadas con partidos ya jugados del torneo, cutoff por partido | ❌ **no existe — es el entregable más urgente** |

### E3 — Calidad de marcadores *(estado: no iniciado — Fase 5 de guia.md)*
| Artefacto | Criterio de aceptación |
|---|---|
| Modelo Poisson | Top-5 marcadores probables por partido; lambdas > 0; matriz suma 1 |
| Ensemble calibrado | RPS ≤ mejor modelo individual en walk-forward |

### E4 — Gobernanza y confianza *(estado: parcial — Fase 3 de guia.md)*
| Artefacto | Criterio de aceptación | Estado |
|---|---|---|
| Tests | Suite en verde | ✅ 58/58 |
| Contratos (datos/features/modelos/agentes) | `/contracts` documentado | ❌ |
| CostGuard | Gasto LLM ≤ $50/mes garantizado por código | ❌ |
| Model card + metodología | Limitaciones y uso responsable publicados | ❌ |

### E5 — Sistema multi-agente *(estado: construido, congelado como opt-in)*
| Artefacto | Criterio de aceptación | Estado |
|---|---|---|
| Orchestrator + 6 especialistas | Fail-safe sin API key; clamp 12%; prior siempre visible | ✅ |
| Backtest de delta_P | — imposible de validar históricamente | ⚠️ riesgo aceptado, opt-in |

---

## 3. Mesa de expertos: calificación

> Revisión simulada con dos perfiles senior, calificando **lógica del proyecto** y **propuestas de AI Solution Architecture**. Se les pidió brutalidad honesta.

### 3.1 Veredicto del AI Solution Architect

| Dimensión | Nota | Comentario |
|---|---|---|
| Stack y costos | **9/10** | Local-first impecable: Parquet+pandas para 50k filas, Monte Carlo en el navegador (cero costo de servidor), LLM opcional con fail-safe. No hay sobre-ingeniería de infra. |
| Decisiones de arquitectura | **7/10** | Separación pipeline/serving correcta; pre-cálculo de 2,256 pares es elegante. PERO: dos simuladores (Python+TS) sin test de paridad, y dos frontends (Next.js+Streamlit) sin jerarquía declarada. |
| **Coherencia objetivo→sistema** | **4/10** | **El problema central.** El sistema no sabe qué es: ¿producto web? ¿portfolio? ¿laboratorio agentic? Cada sesión añadió una capa (agentes, prompt.md, LangGraph propuesto) sin que nadie preguntara *"¿esto acerca el entregable principal?"*. El multi-agente se construyó ANTES de validar que el modelo base tenga ventaja medible — eso es resume-driven development. |
| Foco y priorización | **3/10** | El torneo YA EMPEZÓ y el modo live no existe, las métricas publicadas son de un modelo viejo, y el walk-forward jamás se ejecutó. Mientras tanto hay 6 agentes LLM funcionando. La prioridad estuvo invertida. |

**Cita del arquitecto:** *"Tienen un Ferrari de piezas y ningún chasis. La decisión más valiosa ahora no es técnica, es de producto: declarar UN entregable norte y congelar todo lo que no lo sirva. Con el torneo en curso, cada día sin modo live es valor que se evapora."*

### 3.2 Veredicto del ML Engineer / Sports Prediction Specialist

| Dimensión | Nota | Comentario |
|---|---|---|
| Rigor temporal | **9/10** | Split 3-way, TimeSeriesSplit para calibrar, tests anti-leakage, forma desde timeline completo. Mejor que la mayoría de proyectos profesionales que he auditado. |
| Ingeniería de features | **6/10** | ELO mejorado es sólido. Pero faltan las features que más señal dan en fútbol internacional: ranking FIFA, descanso entre partidos, valor de plantilla. Y ninguna feature ha pasado por ablation. |
| **Validación de la ventaja del modelo** | **3/10** | **Inaceptable a esta altura:** accuracy 0.469 vs 0.484 de la regresión logística — el XGBoost NO ha demostrado ser mejor que el baseline trivial. El RPS (métrica primaria declarada) nunca se midió. El walk-forward (la única validación estadísticamente seria con ~320 partidos) nunca corrió. Todo el edificio descansa sobre una ventaja no demostrada. |
| Modelado de marcadores | **2/10** | Sin Poisson no hay marcadores probables, y los tiebreakers por diferencia de gol del simulador son aproximados. Es el gap técnico más grande. |
| Capa agentic (delta_P) | **5/10** | Bien diseñada (clamp, pesos, confianza, fail-safe) pero epistemológicamente frágil: los ajustes no son backtesteables. Correcto mantenerla opt-in. No invertir más ahí hasta que el core pruebe su valor. |

**Cita del ML engineer:** *"El proyecto tiene la disciplina de validación de un paper y los resultados de validación de una servilleta. Ejecuten el walk-forward HOY. Si el XGB no le gana al ELO-only en RPS, toda la conversación cambia — y mejor saberlo ahora que en la final."*

### 3.3 Nota consolidada

| Dimensión | Nota |
|---|---|
| Stack, costos, FinOps | 9 |
| Rigor anti-leakage y testing | 9 |
| Arquitectura de solución | 7 |
| Features y modelado | 5 |
| Validación de ventaja predictiva | 3 |
| Foco, contexto y coherencia de producto | 3 |
| **GLOBAL** | **5.5/10** |

La intuición del dueño del proyecto (5/10: "muy bien en stack y ahorros, mal en contexto") **coincide con la mesa**. El problema no es capacidad técnica — es que la energía técnica no está apuntada a un objetivo declarado.

---

## 4. Diagnóstico: por qué está en 5 y no en 8

1. **Sin entregable norte declarado.** Tres identidades compitiendo (producto/portfolio/laboratorio) → cada decisión técnica fue localmente razonable y globalmente dispersa.
2. **Prioridad invertida.** Se construyó la capa más especulativa (agentes LLM) antes de validar la capa fundamental (¿el modelo predice mejor que un ELO simple?).
3. **Trabajo terminado pero no cosechado.** ELO mejorado sin re-correr pipeline; walk-forward escrito sin ejecutar; frontend sirviendo datos viejos. Es como cocinar y no servir.
4. **Superficie creciente sin jerarquía.** Next.js + Streamlit + agentes + prompt.md con LangGraph/DuckDB/contracts → el roadmap crece más rápido que lo terminado.
5. **El reloj de producto no gobernaba.** El torneo (única ventana donde esto importa) empezó sin modo live.

---

## 5. Plan 5 → 10

### Decisión de foco (se declara aquí y gobierna todo)

> **Entregable norte:** *"Una web desplegada que durante el Mundial 2026 publica probabilidades calibradas por partido y proyecciones de campeón, actualizadas tras cada jornada, con metodología transparente."*
>
> Todo lo que no acerque esto se **congela** (no se borra): Streamlit (demo interna), LangGraph (descartado para el torneo), nuevos agentes (cero inversión), DuckDB (no), reestructuras (no).

### Etapa A — De 5 a 7: cosechar y enfocar *(días 1–4, antes de la jornada 2)*

| # | Acción | Cierra el gap de |
|---|---|---|
| A1 | Correr `run_pipeline.py` + `walk_forward_validation.py` + `export_frontend_data.py`; registrar RPS en `guia.md` §4 | Validación (3→6) |
| A2 | **Gate de honestidad:** si XGB no gana al ELO-only en RPS walk-forward → el ensemble parte del ELO y el XGB pasa a ser un componente más, no el centro | Validación, lógica |
| A3 | **Modo live MVP** (`scripts/predict_live.py`): ingestar resultados jugados del torneo, recalcular ELO/forma con cutoff por partido, re-exportar JSONs | Foco/contexto (3→6) |
| A4 | Desplegar el frontend con datos frescos; pipeline manual de actualización por jornada documentado en README | Producto |
| A5 | Test de paridad Python↔TypeScript del simulador (mismas probs → distribuciones equivalentes ±tolerancia) | Arquitectura (7→8) |

### Etapa B — De 7 a 9: la ventaja predictiva real *(días 5–14, durante fase de grupos)*

| # | Acción | Cierra el gap de |
|---|---|---|
| B1 | **Modelo Poisson** + top-5 marcadores + tiebreakers por GD reales en el simulador (guia.md Fase 5.1) | Modelado (2→7) |
| B2 | **Ensemble calibrado** ELO+Poisson+XGB, pesos por config, seleccionado por RPS en walk-forward | Validación (6→9) |
| B3 | Features de calendario (descanso) + ranking FIFA, cada una con ablation: entra solo si mejora RPS | Features (5→8) |
| B4 | CostGuard + budget.yaml (los agentes quedan opt-in pero ahora con candado de gasto) | Gobernanza |

### Etapa C — De 9 a 10: confianza pública *(días 15–37, knockout)*

| # | Acción |
|---|---|
| C1 | Actualización por jornada operando sin fricción (idealmente cron/Action) |
| C2 | `model_card.md` + `methodology.md` publicados: datos, métricas walk-forward, limitaciones, lenguaje responsable ("el modelo estima...", nunca certezas) |
| C3 | Tabs de transparencia en Next.js: métricas del modelo, calibración, fecha de corte por predicción |
| C4 | Contratos `/contracts` + observabilidad JSONL (guia.md Fase 3 completa) |
| C5 | Retrospectiva post-torneo: RPS real del Mundial 2026 vs walk-forward — el cierre del portfolio |

### Definición medible de 10/10

```text
□ Walk-forward ejecutado: ensemble con RPS mejor que ELO-only y que XGB solo
□ Web desplegada actualizándose tras cada jornada del torneo real
□ Marcadores probables (Poisson) visibles en el predictor
□ Paridad simulador Python↔TS testeada
□ Gasto LLM ≤ $50 garantizado por CostGuard
□ Model card + metodología públicas, lenguaje probabilístico responsable
□ Suite de tests en verde, incluyendo anti-leakage del modo live
□ Cero dependencia obligatoria de LLM para predecir
```

---

## 6. Riesgos del plan

1. **El gate A2 puede doler:** si el XGB no supera al ELO, hubo meses invertidos en un modelo sin ventaja. Mitigación: es exactamente para eso que existe el gate — el ensemble absorbe el golpe y el proyecto gana honestidad (que en portfolio vale más que un modelo inflado).
2. **Resultados del torneo en curso como fuente:** se necesita ingesta confiable de marcadores (API football-data.org ya integrada en `/api/live`); fallback manual por CSV si la API falla.
3. **37 días de ventana:** etapas B y C compiten con el calendario; si hay que cortar, B1–B2 (Poisson+ensemble) tienen prioridad sobre C4 (contratos) — el valor predictivo manda sobre la gobernanza documental.
4. **Tentación de re-expandir:** cualquier idea nueva durante el torneo entra a un `backlog.md`, no al código, salvo que sirva al entregable norte.
