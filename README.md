# ⚽ Mundial Predictor 2026

Predictor de resultados del **Mundial FIFA 2026** con Machine Learning: XGBoost calibrado, sistema ELO propio y simulación Monte Carlo del torneo completo — con resultados reales integrados en vivo y el modelo aprendiendo de cada partido jugado.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0-EB5E28)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![Tests](https://img.shields.io/badge/tests-151%20passed%2C%201%20skipped-2ea44f)

> 🇨🇦🇺🇸🇲🇽 El torneo está **en juego** (11 jun – 19 jul 2026). La web integra los resultados oficiales al final de cada partido: el modelo recalcula los ELO y actualiza todas las probabilidades con los datos reales de la copa.

---

## ¿Qué hace?

- **En Vivo · Modelo vs Realidad** — marcadores del torneo, veredicto del modelo por partido terminado, posiciones por grupo y próximos partidos con pronóstico
- **Predictor de partido** — probabilidades victoria/empate/derrota para cualquier cruce entre las 48 selecciones, con **Narrator AI** que genera una narración futbolera regional pre-computada una vez por día, sin costo por usuario
- **Stats WC 2026** — dashboard en tiempo real: goles totales, promedio por partido, equipos más goleadores, partidos más goleadores, marcadores frecuentes y mayores sorpresas del torneo
- **Rendimiento del modelo** — precisión por jornada interna (J1/J2/J3) con flecha de mejora, desglose por grupo con columna FG (total del grupo + conteo + delta vs J1), y top sorpresas donde el modelo erró; incluye la misma vista para el **Agent Debate** lado a lado
- **Agent Debate** — predicción alternativa sin ML: 3 agentes (analista de grupo, scout táctico, lector de sentimiento) debaten en 3 rondas con DeepSeek Reasoner razonando solo desde presión de clasificación, estado real del grupo y momentum de la jornada anterior; genera **4 predicciones por partido** (3 individuales + 1 consenso) para evaluar cuál razonamiento es más predictivo; aparece en el Predictor y en "En Vivo → Próximos"
- **Fase de grupos** — predicción de los 72 partidos, posiciones finales de cada grupo (5.000 simulaciones Monte Carlo) y previas narrativas por grupo con tabla, presión, localía, resultado anterior, dependencia y lectura por selección
- **Proyecciones del torneo** — probabilidad de cada selección de llegar a cada ronda y de ser campeona; se actualiza con el ciclo diario (`predict_live.py --export`)
- **Chat IA** — pregunta sobre partidos del día, tabla de grupos, predicciones; usa contexto real del torneo + DeepSeek, con filtro de temas, caché y límite por IP

---

## ¿Cómo funciona el modelo?

### 🎯 Núcleo Predictivo (Determinístico, Siempre Disponible)

El sistema comienza con un **Ensemble calibrado** que combina tres modelos complementarios:

```
Datos históricos (49k+ partidos, 1872–2026)
   ├─► Normalización de nombres (Zaïre→DR Congo, etc.)
   └─► Cálculo de ELO (K por torneo, margen, localía)
        ├─► Modelo 1: ELO determinístico (22% del weight)
        ├─► Modelo 2: Poisson bivariado (distribución de goles, 58%)
        └─► Modelo 3: XGBoost (patrones no-lineales, 20%)
             └─► ENSEMBLE: (0.22×ELO + 0.58×Poisson + 0.20×XGB)
                  └─► Output: (p_home, p_draw, p_away) normalizadas
                       └─► JSONs estáticos → frontend + simulador Monte Carlo
```

**Garantía:** El Ensemble funciona sin API keys, sin agentes LLM, sin internet. RPS = 0.1958 (walk-forward validado).

| Decisión | Por qué |
|---|---|
| ELO propio | Calculado solo sobre resultados, sin sesgos de confederación |
| Split temporal (test = 2022) | Series temporales requieren validación temporal; cero leakage |
| Calibración isotónica | Las probabilidades importan más que accuracy en simulación |
| Ensemble 22/58/20 | Poisson aporta señal de distribución de goles; XGB no supera ELO globalmente |
| Monte Carlo en navegador | 5,000 sims en 300ms; sin carga al servidor |
| Re-entrenamiento diario | Después de cada jornada: ELO + probs se actualizan con datos reales |

**Métricas en Qatar 2022 (64 partidos, never seen):**
- Accuracy: 0.50–0.52
- Log-loss: 1.08
- RPS: 0.1958 ✨
- Baseline (random): 0.25 RPS
- Casas de apuestas: 0.55–0.58 accuracy

---

### 🔧 Capa Opcional: Enriquecimiento Multi-Agente

**Importante:** Los agentes son un ENRIQUECIMIENTO opcional. El Ensemble predice con precisión completa sin ellos.

Cada agente recibe **evidencia real derivada gratis** (`src/agents/match_intel.py`): forma reciente con marcadores y calidad del rival (elite/strong/mid/weak), tendencias de goles, momentum, head-to-head, resultados del torneo, fuente de goles (dependencia de un goleador vs profundidad) y la **matemática exacta de mejor tercero** (corte cross-group en puntos + diferencia de gol). Así razonan sobre datos concretos, no sobre el nombre del equipo.

Si habilitado + presupuesto disponible:
```
Ensemble prior (p_home, p_draw, p_away)
   ├─► MatchIntel: computa evidencia real (forma, goleadores, terceros…)
   ├─► Orchestrator: evalúa contexto del partido
   └─► Selecciona hasta 5 agentes especializados (3-5 en fase de grupos)
        ├─ IntMatch-Analytics-Pro: tácticas desde forma/tendencias/H2H/goleadores
        ├─ GroupScenario-Reasoner: presión de clasificación + matemática de terceros
        ├─ Roster-Data-Scout: dependencia de goleador + fatiga/congestión
        ├─ Media-Sentiment-Parser: moral derivada de resultados reales (euforia/crisis)
        ├─ Travel-Logistics-Quant: fatiga, viaje inter-sede, calor, altitud
        ├─ FinOps-Market-Calibration-Validator: odds vs. modelo (si hay odds)
        └─ FIFA-Regs-Strategist: bracket, presión de clasificación, altitud
             └─► Cada agente produce delta_P (ajuste a prior)
                  └─► Blend: suma ponderada × confianza, clamped ±12%
                       └─► Output final: (p_home', p_draw', p_away') = prior + deltas
```

**Coste:** $2–$5/día (configurable). **Si agotado:** sistema cae back a Ensemble (sin degradación).

> **Nota de diseño:** los agentes que dependen de feeds externos que no tenemos (tarjetas/suspensiones, odds de casas) quedan inactivos con `delta=0` salvo que se inyecte esa data. El resto corre con señales gratis computadas de `results.csv`, `wc2026_live_results.csv` y `goalscorers.csv`.

---

### 🧭 Decisión de Diseño: Core vs. Enrichment

**¿Por qué separar?**
1. El Ensemble es **probado, validado, reproducible** — funciona siempre
2. Los agentes son **experimentales, cost-gated** — impacto no medido históricamente
3. Transparencia: usuarios ven prior siempre; deltas son labeled como "enriquecimiento"
4. Fallback graceful: sin API keys → Ensemble intacto; sin presupuesto → Ensemble intacto

**Ver:** `contracts/core_model_contracts.md` y `contracts/agent_enrichment_contracts.md` para especificación completa.

---

## Ciclo diario durante el torneo

El ciclo se corre cada mañana antes de los partidos del día. En J2/MD2 hay una segunda corrida en la tarde cuando ya terminaron los primeros dos partidos, para que los partidos de la noche y las previas de grupo incorporen la presión real de puntos, diferencia de gol y mejores terceros. En J3/MD3 (partidos simultáneos por grupo) se corre `update_third_place_probs.py` **3 veces al día** según los horarios del fixture: recalcula solo las probabilidades de mejor tercero (Monte Carlo ~5s) sin regenerar narraciones, ya que estas no cambian con resultados simultáneos.

```bash
# 1. Descarga resultados de ayer, recalcula ELO, reentrena (~90s)
python scripts/live_update.py

# 2. Recalcula predicciones live con Ensemble + agentes multi-especialista
python scripts/predict_live.py --export

# Variante sin gasto LLM: Ensemble determinístico, sin agentes
python scripts/predict_live.py --export --no-agents

# 3. Genera narraciones de partidos y previas de grupos (DeepSeek)
python scripts/precompute_narrations.py

# Solo recalcular previas de grupos (útil después de ajustar prompts o contexto J2/J3)
python scripts/precompute_narrations.py --groups-only --days 1

# Opcional: Agent Debate para partidos puntuales (no retroactivo, solo hacia adelante)
python scripts/run_agent_debate.py "Mexico" "South Korea"
python scripts/export_frontend_data.py

# 4. Despliega
cd frontend && npx vercel --prod
```

- **Fase de grupos**: narración solo en español bogotano/neutro por ahora; los dialectos quedan pausados hasta estabilizar el flujo
- **Fase eliminatoria**: 5 dialectos activados automáticamente (~$0.025/día)
- `narrations.json` alimenta el predictor partido a partido; `group_narratives.json` alimenta las tarjetas y el detalle de grupos
- Las previas de grupo analizan cada selección: puntos, resultado anterior, fuerza del rival anterior, calidad del resultado, estado de ánimo, presión, dependencia, nivel de peligro y rival siguiente
- El contexto de la narración incluye tabla real del grupo, localía, horarios Colombia/Bogotá, probabilidades del predictor y presión de clasificación desde MD2 en adelante
- Los archivos JSON públicos deben escribirse siempre como UTF-8. Evita reescribirlos con `Get-Content | Set-Content` en PowerShell; usa los scripts Python del proyecto para no producir texto tipo `MÃ©xico` o `arrancÃ³`

---

## Correr en local

```bash
# 1. Pipeline de datos + modelos (Python 3.11)
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python scripts/run_pipeline.py          # raw → ELO → features → modelos → métricas
python scripts/export_frontend_data.py  # genera los JSON del frontend

# 2. Frontend (Next.js 15)
cd frontend
npm install
cp .env.example .env.local              # agrega las keys (ver tabla abajo)
npm run dev                             # http://localhost:3000

# Tests
pytest          # 152 tests
```

**Variables de entorno** (`frontend/.env.local` y Vercel):

| Variable | Obtención | Uso |
|---|---|---|
| `FOOTBALL_DATA_TOKEN` | [football-data.org](https://www.football-data.org/) (gratis) | Resultados en vivo del torneo |
| `DEEPSEEK_API_KEY` | [platform.deepseek.com](https://platform.deepseek.com/) | Chat IA + Narrator AI (primario) |
| `ANTHROPIC_API_KEY` | [console.anthropic.com](https://console.anthropic.com/) | Fallback LLM si DeepSeek no responde |
| `DASHSCOPE_API_KEY` | [dashscope.aliyuncs.com](https://dashscope.aliyuncs.com/) | Embeddings RAG — opcional |

> El dataset histórico se descarga de Kaggle ([martj42/international-football-results](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017)) vía `kagglehub` — los CSV no se versionan.

---

## Estructura

```
├── src/                  # Python: extractor, ELO/features, modelo XGBoost, Poisson, simulador
│   ├── agent_debate.py          # Agent Debate System: debate de 3 agentes en 3 rondas (DeepSeek Reasoner)
│   └── agents/
│       ├── match_intel.py       # Evidencia derivada gratis (forma, H2H, goleadores, terceros) para los agentes
│       ├── orchestrator.py      # Routing (hasta 5 en grupos), blend de deltas
│       └── specialists/         # IntMatch, GroupScenario, Roster, Media, Travel, FinOps, FIFA-Regs
├── scripts/
│   ├── live_update.py           # Ciclo completo: fetch → retrain → export (~90s)
│   ├── predict_live.py          # Predicciones con agentes + anti-leakage por partido
│   ├── update_third_place_probs.py # Solo recalcula terceros (Monte Carlo ~5s, sin narraciones) — J3 3x/día
│   ├── precompute_narrations.py # Narraciones diarias + previas de grupo → narrations.json / group_narratives.json
│   ├── run_agent_debate.py      # Corre el Agent Debate para partidos puntuales (acumulativo, idempotente)
│   ├── run_pipeline.py          # Pipeline completo desde cero
│   └── export_frontend_data.py  # Exporta todos los JSONs al frontend
├── frontend/             # Next.js 15 + React 19 + Tailwind + Recharts + Framer Motion
│   ├── src/app/api/live/    # Proxy football-data.org
│   ├── src/app/api/chat/    # Chat IA: contexto del torneo + DeepSeek/Anthropic + caché
│   ├── src/app/api/narrator/# Sirve narrations.json; LLM solo si la narración no está pre-computada
│   ├── src/components/      # Predictor (dialecto), Groups, ModelTab (J1/J2/J3/FG), StatsTab, etc.
│   └── public/data/         # JSONs: teams, predictions, narrations, group_matches, standings…
├── tests/                # 152 tests: pipeline, agentes, integridad, simulador
├── data/
│   ├── raw/              # results.csv, shootouts.csv, goalscorers.csv (gitignored)
│   └── external/         # wc2026_fixture.json · wc2026_live_results.csv
├── instrucciones.md      # Ciclo operativo diario: MD1/MD2/MD3 + doble corrida
└── models/               # Modelos entrenados (gitignored, regenerables)
```

---

## Fuentes de datos

- [International football results 1872–2026](https://www.kaggle.com/datasets/martj42/international-football-results-from-1872-to-2017) (Kaggle, martj42)
- [football-data.org](https://www.football-data.org/) — resultados oficiales WC 2026 (tier gratuito, proxy cacheado)
- [openfootball/worldcup.json](https://github.com/openfootball/worldcup.json) — fallback de fixture sin API key

---

## Autor

**Manuel Coy** — Data & Analytics Engineering

*Proyecto de portafolio. No afiliado a la FIFA.*
