# ⚽ Mundial Predictor 2026

Predictor de resultados del **Mundial FIFA 2026** con Machine Learning: XGBoost calibrado, sistema ELO propio y simulación Monte Carlo del torneo completo — con resultados reales integrados en vivo y el modelo aprendiendo de cada partido jugado.

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![XGBoost](https://img.shields.io/badge/XGBoost-2.0-EB5E28)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)
![Tests](https://img.shields.io/badge/tests-122%20passed-2ea44f)

> 🇨🇦🇺🇸🇲🇽 El torneo está **en juego** (11 jun – 19 jul 2026). La web integra los resultados oficiales al final de cada partido: el modelo recalcula los ELO y actualiza todas las probabilidades con los datos reales de la copa.

---

## ¿Qué hace?

- **En Vivo · Modelo vs Realidad** — marcadores del torneo, veredicto del modelo por partido terminado, posiciones por grupo y próximos partidos con pronóstico
- **Predictor de partido** — probabilidades victoria/empate/derrota para cualquier cruce entre las 48 selecciones, con **Narrator AI** que genera una narración futbolera regional (dialecto bogotano/paisa/boyacense/costeño/EN) pre-computada una vez por día, sin costo por usuario
- **Stats WC 2026** — dashboard en tiempo real: goles totales, promedio por partido, equipos más goleadores, partidos más goleadores, marcadores frecuentes y mayores sorpresas del torneo
- **Rendimiento del modelo** — precisión por jornada interna (J1/J2/J3) con flecha de mejora, desglose por grupo con columna FG (total del grupo + conteo + delta vs J1), y top sorpresas donde el modelo erró
- **Fase de grupos** — predicción de los 72 partidos y posiciones finales de cada grupo (5.000 simulaciones Monte Carlo)
- **Proyecciones del torneo** — probabilidad de cada selección de llegar a cada ronda y de ser campeona; se actualiza con el ciclo diario (`predict_live.py --export`)
- **Chat IA** — pregunta sobre partidos del día, tabla de grupos, predicciones; usa contexto real del torneo + DeepSeek, con filtro de temas, caché y límite por IP

---

## ¿Cómo funciona el modelo?

```
results.csv (49k+ partidos, 1872–2026, incluye fixture WC 2026)
   └─► normalización de nombres históricos (Zaïre→DR Congo, Czechoslovakia→Czech Republic…)
        └─► ELO propio (K por tipo de torneo, cronológico, pre-match)
             └─► feature matrix: ELO diff + forma reciente + H2H + experiencia mundialista
                  └─► XGBoost multi:softprob + CalibratedClassifierCV (isotónica)
                       └─► Ensemble: ELO 22% + Poisson 58% + XGBoost 20%
                            └─► JSONs estáticos → frontend Next.js + Monte Carlo client-side
```

| Decisión | Por qué |
|---|---|
| ELO propio en vez de ranking FIFA | calculado solo sobre resultados, sin sesgos de confederación |
| Split temporal (test = Qatar 2022) | nada de KFold aleatorio en series temporales — cero leakage |
| Calibración isotónica | las probabilidades importan más que el accuracy en un simulador |
| Monte Carlo en el navegador | 5.000 simulaciones sobre 1.128 pares pre-calculados, sin carga al servidor |
| Re-entrenamiento por jornada | cada partido termina → ELO actualizado → predicciones recalibradas |

**Métricas en Qatar 2022 (64 partidos, nunca vistos por el modelo):** accuracy 0.50–0.52 · log-loss 1.08 · calibración con error < 0.02 por clase. Un modelo aleatorio da 0.33; las casas de apuestas rondan 0.55–0.58.

---

## Ciclo diario durante el torneo

El ciclo se corre cada mañana antes de los partidos del día. Los días de MD2 hay una segunda corrida en la tarde (ver `instrucciones.md`).

```bash
# 1. Descarga resultados de ayer, recalcula ELO, reentrena (~90s)
python scripts/live_update.py

# 2. Recalcula predicciones live con Ensemble + agentes multi-especialista
python scripts/predict_live.py --export

# Variante sin gasto LLM: Ensemble determinístico, sin agentes
python scripts/predict_live.py --export --no-agents

# 3. Genera narraciones para los partidos de HOY (DeepSeek, 1 llamada/partido)
python scripts/precompute_narrations.py

# 4. Despliega
cd frontend && npx vercel --prod
```

- **Fase de grupos**: narración solo en dialecto bogotano (~$0.015/día)
- **Fase eliminatoria**: 5 dialectos activados automáticamente (~$0.025/día)
- El contexto de la narración incluye la tabla real del grupo (puntos, GD) desde MD2 en adelante

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
pytest          # 122+ tests
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
├── scripts/
│   ├── live_update.py           # Ciclo completo: fetch → retrain → export (~90s)
│   ├── predict_live.py          # Predicciones con agentes + anti-leakage por partido
│   ├── precompute_narrations.py # Narraciones diarias × dialectos → narrations.json
│   ├── run_pipeline.py          # Pipeline completo desde cero
│   └── export_frontend_data.py  # Exporta todos los JSONs al frontend
├── frontend/             # Next.js 15 + React 19 + Tailwind + Recharts + Framer Motion
│   ├── src/app/api/live/    # Proxy football-data.org
│   ├── src/app/api/chat/    # Chat IA: contexto del torneo + DeepSeek/Anthropic + caché
│   ├── src/app/api/narrator/# Sirve narrations.json; LLM solo si la narración no está pre-computada
│   ├── src/components/      # Predictor (dialecto), Groups, ModelTab (J1/J2/J3/FG), StatsTab, etc.
│   └── public/data/         # JSONs: teams, predictions, narrations, group_matches, standings…
├── tests/                # 122+ tests: pipeline, agentes, integridad, simulador
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
