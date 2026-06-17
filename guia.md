# Mundial Predictor 2026 — Guía Técnica Completa

> Documento de referencia para entender en profundidad cómo funciona el sistema: arquitectura, modelos, agentes, predicciones, retroalimentación y frontend. Diseñado para que una IA lo convierta en una página HTML con diagramas interactivos.

---

## 1. Visión General

**Mundial Predictor 2026** es un sistema de predicción de fútbol que combina Machine Learning clásico, sistemas ELO personalizados, simulación Monte Carlo y agentes de IA especializados para predecir resultados del Mundial FIFA 2026 (Canadá, México y EE.UU., 11 jun – 19 jul 2026).

**No es un modelo estático.** Se retroalimenta con cada partido jugado: actualiza los ratings ELO, reentrena los modelos y recalcula todas las probabilidades del torneo con los datos reales de la copa en curso.

### Capas del sistema

```
┌─────────────────────────────────────────────────────────────────┐
│                     USUARIO (navegador)                         │
│  En Vivo · Predictor · Stats · Modelo · Grupos · Proyecciones   │
└───────────────────────┬─────────────────────────────────────────┘
                        │  JSON estáticos (CDN Vercel)
┌───────────────────────▼─────────────────────────────────────────┐
│                  FRONTEND Next.js 15                            │
│  Monte Carlo client-side · Narrator AI · Chat IA · Dialectos    │
└───────────────────────┬─────────────────────────────────────────┘
                        │  API Routes (serverless)
┌───────────────────────▼─────────────────────────────────────────┐
│              BACKEND PYTHON (pipeline diario)                   │
│  Extractor → ELO → Features → XGBoost/Poisson/Ensemble          │
│  → Agentes IA → live_predictions.json → Vercel deploy           │
└─────────────────────────────────────────────────────────────────┘
```

---

## 2. Arquitectura Completa del Sistema

```
┌──────────────────────────────────────────────────────────────────────────┐
│  FUENTES DE DATOS                                                        │
│                                                                          │
│  results.csv ──────────────────────────────────────────────────────────► │
│  (49.477 partidos internacionales, 1872–2026)                            │
│                                                                          │
│  football-data.org API ─────────────────────────────────────────────►   │
│  (resultados WC 2026 en vivo, actualización post-partido)               │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  PIPELINE DE DATOS (scripts/live_update.py, ~90s por ejecución)         │
│                                                                          │
│  1. update_wc_results.py                                                 │
│     └─ Llena los NA en results.csv con marcadores reales WC 2026         │
│                                                                          │
│  2. run_pipeline.py                                                      │
│     ├─ extractor.py   → normaliza nombres, filtra Mundiales              │
│     ├─ features.py    → calcula ELO cronológico + features               │
│     ├─ model.py       → entrena XGBoost + calibración                    │
│     └─ poisson_model.py → ajusta modelo de Poisson bivariado             │
│                                                                          │
│  3. export_frontend_data.py                                              │
│     └─ Genera todos los JSONs en frontend/public/data/                   │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  SISTEMA DE PREDICCIÓN (scripts/predict_live.py)                        │
│                                                                          │
│  EnsembleModel ──────────────────────────────────────────────────────►  │
│  (ELO 22% + Poisson 58% + XGBoost 20%)                                  │
│         │                                                                │
│         ▼                                                                │
│  Orchestrator ──► máx. 3 agentes en grupos / 2 en knockout ──────────►  │
│         │                                                                │
│         ▼                                                                │
│  live_predictions.json (partidos pendientes, ajustados por agentes)     │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  FRONTEND (Vercel CDN)                                                   │
│                                                                          │
│  narrations.json ◄── precompute_narrations.py (DeepSeek, 1×/día)        │
│  live_predictions.json ◄── predict_live.py --export                     │
│  group_standings.json ◄── export_frontend_data.py (Monte Carlo 5k sims) │
│                                                                          │
│  Cliente:                                                                │
│  ├─ Simulator.ts → Monte Carlo 5.000 simulaciones en el navegador        │
│  ├─ live.ts → marcadores reales cada 5 min (football-data.org proxy)     │
│  └─ Chat /api/chat → DeepSeek + RAG + contexto del torneo               │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 3. El Pipeline de Datos

### 3.1 Dataset histórico

El sistema arranca con **49.477 partidos internacionales** (1872–2026). El archivo `results.csv` incluye el fixture completo del Mundial 2026 con `home_score` / `away_score` = NA para los partidos no jugados. Cuando se juega un partido, ese NA se rellena con el marcador real.

### 3.2 Normalización de nombres

```
Zaïre → DR Congo
Czechoslovakia → Czech Republic
Korea Republic → South Korea
Bosnia-Herzegovina → Bosnia and Herzegovina
Côte d'Ivoire → Ivory Coast
```

Hay más de 1.391 sustituciones aplicadas automáticamente para que los nombres históricos casen con los nombres modernos del fixture.

### 3.3 Estrategia de split temporal

```
Timeline ──────────────────────────────────────────────────────────►

  1872          2014          2018          2022          2026
   │             │             │             │             │
   ├─── TRAIN ──────────────────┤             │             │
   │    (< 2018)                │             │             │
   │                             ├── CALIB ───┤             │
   │                             │  (= 2018)  │             │
   │                                           ├─── TEST ───┤
   │                                           │ (WC 2022)  │
   │                                                         ├── LIVE
   │                                                         │  (WC 2026)
```

**Por qué no K-Fold:** los datos son series temporales. Un partido de 2022 no puede estar en el entrenamiento si el partido de 2018 ya ocurrió. La validación cruzada aleatoria filtraría el futuro al pasado → leakage.

**Qatar 2022 = 64 partidos que el modelo nunca vio** durante el entrenamiento. Es el benchmark real de rendimiento.

---

## 4. Los Tres Modelos

### 4.1 Sistema ELO

ELO es un sistema de rating que mide la "fortaleza relativa" de cada equipo en función de victorias y derrotas históricas. El sistema ELO propio del proyecto es más sofisticado que el ELO estándar:

```
Actualización ELO por partido:
─────────────────────────────

  Nuevo_ELO = ELO_anterior + K × (Resultado_real - Resultado_esperado) × MarginMult

  Donde:
  ┌──────────────────────────────────────────────────────────────────┐
  │  K (factor de actualización por tipo de torneo):                 │
  │    Mundial FIFA     → K = 60  (mayor impacto)                    │
  │    Copa continental → K = 50                                     │
  │    Clasificatorio   → K = 40                                     │
  │    Amistoso         → K = 20  (menor impacto)                    │
  │                                                                  │
  │  Ventaja local: +100 puntos ELO al equipo local (sede no neutral)│
  │                                                                  │
  │  MarginMult = log(1 + |diferencia_de_goles|)                     │
  │  → Una victoria 4-0 actualiza más que una victoria 1-0           │
  └──────────────────────────────────────────────────────────────────┘

  Resultado_esperado = 1 / (1 + 10^((ELO_rival - ELO_propio - ventaja_local) / 400))

  Ejemplo:
    Argentina ELO 2100 vs Marruecos ELO 1800 en sede neutral
    → Resultado_esperado_Argentina = 1 / (1 + 10^(-300/400)) = 0.85
    → Si Argentina gana, gana pocos puntos (ya era favorito)
    → Si Marruecos gana, gana MUCHOS puntos (sorpresa)
```

**¿Por qué ELO propio en lugar del ranking FIFA?**
El ranking FIFA incluye sesgos de confederación y criterios subjetivos. El ELO se calcula puramente sobre resultados, reflejando la fortaleza real medida en el campo.

**ELO actual de selecciones top:**
```
Brasil        ≈ 2.120   Alemania      ≈ 2.050
Argentina     ≈ 2.095   Portugal      ≈ 2.000
Francia       ≈ 2.085   España        ≈ 1.985
Inglaterra    ≈ 2.060   Colombia      ≈ 1.840
```

### 4.2 Modelo de Poisson Bivariado

El modelo de Poisson predice el **marcador exacto** de cada partido, no solo el resultado. Esto permite calcular probabilidades más ricas que el ELO simple.

```
Cómo funciona:
─────────────

Cada equipo tiene dos ratings aprendidos del histórico de Mundiales:
  • Ataque_i  → cuántos goles tiende a marcar
  • Defensa_i → cuántos goles tiende a conceder

Para un partido Home vs Away:
  λ_home = exp(Ataque_home - Defensa_away + ventaja_local)
  λ_away = exp(Ataque_away - Defensa_home)

  λ = goles esperados (Poisson)
  P(goles = k) = e^(-λ) × λ^k / k!

Ejemplo:
  España (ataque=1.8, defensa=0.9) vs Bolivia (ataque=0.8, defensa=1.4)
  λ_España ≈ exp(1.8 - 1.4 + 0.1) = 1.67 goles esperados
  λ_Bolivia ≈ exp(0.8 - 0.9) = 0.91 goles esperados

  Genera una matriz de probabilidad para cada marcador posible:
  ┌────┬─────┬─────┬─────┬─────┐
  │    │  0  │  1  │  2  │  3  │  ← goles Bolivia
  ├────┼─────┼─────┼─────┼─────┤
  │  0 │ 5.4%│ 4.9%│ 2.2%│ 0.7%│
  │  1 │ 9.0%│ 8.2%│ 3.7%│ 1.1%│
  │  2 │ 7.5%│ 6.9%│ 3.1%│ 0.9%│
  │  3 │ 4.2%│ 3.8%│ 1.7%│ 0.5%│
  └────┴─────┴─────┴─────┴─────┘
    ↑ goles España

  Suma de celdas donde España > Bolivia = P(España gana)
  Suma diagonal = P(empate)
  Suma donde Bolivia > España = P(Bolivia gana)
```

El modelo también extrae el **marcador más probable** (la celda con mayor valor de la matriz), que se muestra en el Predictor.

### 4.3 XGBoost + Calibración Isotónica

XGBoost es un modelo de árboles de decisión con boosting. Aprende patrones no lineales entre features y el resultado del partido.

#### Features utilizadas

```
Feature                    │ Descripción
───────────────────────────┼─────────────────────────────────────────────
elo_diff                   │ ELO local - ELO visitante (diferencia)
elo_home                   │ Rating ELO absoluto del equipo local
elo_away                   │ Rating ELO absoluto del visitante
home_goals_scored_avg5     │ Promedio de goles anotados en últimos 5 partidos
away_goals_scored_avg5     │ Promedio de goles anotados visitante (últimos 5)
home_goals_conceded_avg5   │ Promedio de goles recibidos local (últimos 5)
away_goals_conceded_avg5   │ Promedio de goles recibidos visitante (últimos 5)
h2h_home_win_pct           │ % histórico de victorias del local en H2H
is_neutral                 │ 1 = sede neutral, 0 = partido en casa
wc_experience_diff         │ Diferencia en apariciones en Mundiales
```

#### Entrenamiento

```
Datos: todos los partidos históricos (< 2018)
  ├── Ponderación: WC = 1.0, amistosos = 0.20
  ├── Target: {home_win=0, draw=1, away_win=2}
  ├── XGBoost multi:softprob → probabilidades directas
  └── CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)
       └── Ajusta que si el modelo dice 70%, realmente gana ~70% de las veces

Métricas en WC Qatar 2022 (test set — 64 partidos):
  Accuracy:   0.484–0.502
  Log-loss:   1.025
  Brier:      0.203
  RPS:        0.2166
  (Baseline ELO-only RPS: 0.220 — el ensemble mejora el baseline)
```

#### ¿Por qué XGBoost tiene solo 20% de peso en el ensemble?

El walk-forward validation (validación en múltiples torneos históricos) mostró que XGBoost no supera consistentemente al ELO puro en todos los torneos. Poisson aporta señal independiente (distribución de goles), ELO es más robusto en datos escasos. El blend final es conservador.

---

## 5. El Ensemble

El Ensemble combina las tres señales en una predicción final:

```
FLUJO DE PREDICCIÓN ENSEMBLE
──────────────────────────────────────────────────────────────────

        Input: Argentina vs Francia, ELO_Arg=2095, ELO_Fra=2085
                                      is_neutral=True
                                      form, H2H, experiencia
                │
                ▼
┌───────────────────────────────────────────────────────────────┐
│              TRES MODELOS EN PARALELO                         │
│                                                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │     ELO       │  │   Poisson    │  │    XGBoost       │   │
│  │               │  │              │  │                  │   │
│  │  H: 42.1%     │  │  H: 39.8%    │  │  H: 40.5%        │   │
│  │  D: 25.3%     │  │  D: 28.1%    │  │  D: 26.2%        │   │
│  │  A: 32.6%     │  │  A: 32.1%    │  │  A: 33.3%        │   │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────────┘   │
│         │                 │                  │               │
│      w=0.22            w=0.58             w=0.20             │
└─────────┼─────────────────┼──────────────────┼───────────────┘
          │                 │                  │
          └─────────────────┼──────────────────┘
                            │  BLEND PONDERADO
                            ▼
                    H: 40.4%  D: 27.6%  A: 32.0%
                    (renormalizado a suma = 100%)
```

**Pesos del Ensemble** (calibrados tras walk-forward validation):
```
ELO     → 22%  (robusto, siempre disponible, base histórica sólida)
Poisson → 58%  (mayor peso: añade distribución de goles independiente)
XGBoost → 20%  (menor peso: bueno pero no consistentemente superior)
```

**Walk-forward RPS (5 Mundiales, ~320 partidos):**
```
ELO-only  → RPS 0.1979
Poisson   → RPS 0.2065
XGBoost   → RPS 0.1986
Ensemble  → RPS 0.1958  ← MEJOR
```

---

## 6. El Sistema Multi-Agente

### 6.1 Arquitectura del sistema

```
SISTEMA MULTI-AGENTE
────────────────────────────────────────────────────────────────────────

                    ┌─────────────────────────────┐
                    │   predict_live.py            │
                    │   (llamado por cada partido) │
                    └──────────────┬──────────────┘
                                   │
                                   ▼
                    ┌──────────────────────────────┐
                    │  EnsembleModel               │
                    │  H: 40.4% D: 27.6% A: 32.0% │  ← PRIOR
                    └──────────────┬───────────────┘
                                   │
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    ORCHESTRATOR                                      │
│            WorldCup2026-Core-Orchestrator                           │
│                                                                      │
│  • Lee el MatchContext (lesiones, odds, altitud, historial)         │
│  • Selecciona MÁX. 3 agentes en grupos / MÁX. 2 en knockout        │
│  • Envía solo el payload comprimido a cada agente (sin contexto     │
│    innecesario para minimizar tokens)                               │
│  • Recibe delta_P de cada agente                                    │
│  • Aplica blend ponderado por (peso × confianza) del agente        │
│  • Clampea el ajuste total a ±12%                                  │
│  • Renormaliza a suma = 100%                                        │
└────────────┬─────────────────────────────────────────────┬──────────┘
             │                                             │
     hasta 3 agentes                               blend ponderado
             │                                             │
   ┌─────────▼──────────────────────────────────────┐    │
   │  POOL DE 6 AGENTES ESPECIALIZADOS              │    │
   └────────────────────────────────────────────────┘    │
             │                                            │
             ▼                                            ▼
       (ver tabla)                         PREDICCIÓN FINAL AJUSTADA
                                           H: 42.1% D: 26.8% A: 31.1%
```

### 6.2 Los 6 Agentes Especializados

#### Agente 1: IntMatch-Analytics-Pro
```
┌───────────────────────────────────────────────────────────────────┐
│  INTMATCH-ANALYTICS-PRO                                           │
│  Rol: Analista táctico principal                                  │
│  Tipo: LLM (DeepSeek → Anthropic fallback)                       │
│  Peso en blend: 25%                                               │
│                                                                   │
│  Qué analiza:                                                     │
│  • Estilo táctico de cada equipo (contragolpe vs posesión alta)  │
│  • Forma actual en WC 2026 (no clasifs, sino el torneo en curso)  │
│  • Ventaja de sede para EE.UU., México y Canadá                   │
│  • Demografía del estadio (si hay masa de fans del visitante)     │
│  • Tarjetas acumuladas / suspensiones inminentes                  │
│  • Impacto térmico (Miami, Monterrey = calor/humedad en 2da parte)│
│                                                                   │
│  Output: delta_P = {"home": +0.02, "draw": +0.01, "away": -0.03}│
│  Siempre se activa en fase de grupos                              │
└───────────────────────────────────────────────────────────────────┘
```

#### Agente 2: Roster-Data-Scout
```
┌───────────────────────────────────────────────────────────────────┐
│  ROSTER-DATA-SCOUT                                                │
│  Rol: Analista de plantilla y lesiones                            │
│  Tipo: LLM (DeepSeek → Anthropic fallback)                       │
│  Peso en blend: 30%  ← mayor impacto (datos concretos)           │
│                                                                   │
│  Qué analiza:                                                     │
│  • Lesiones y bajas confirmadas del partido                       │
│  • Impacto táctico de ausencias (Player Centrality Index)        │
│  • Métricas avanzadas de la convocatoria (xG, xA, pases prog.)   │
│  • Estadística WAR (Wins Above Replacement) por jugador:          │
│    ΔR = Métrica_Titular - Métrica_Sustituto                      │
│  • Saturación de minutos en clubes (riesgo de fatiga acumulada)  │
│                                                                   │
│  Solo se activa si ctx.injuries contiene datos reales de bajas   │
│  Output: mayor delta_P de todos los agentes cuando hay lesiones  │
└───────────────────────────────────────────────────────────────────┘
```

#### Agente 3: FinOps-Bookmaker-Alpha
```
┌───────────────────────────────────────────────────────────────────┐
│  FINOPS-BOOKMAKER-ALPHA                                           │
│  Rol: Analista de mercados de apuestas                            │
│  Tipo: DETERMINÍSTICO (sin LLM)                                   │
│  Peso en blend: 20%                                               │
│                                                                   │
│  Qué analiza:                                                     │
│  • Cuotas de casas de apuestas → extrae probabilidad implícita:   │
│    P_impl = (1/cuota) / Σ(1/cuota_i)                             │
│    Margen = Σ(1/cuota_i) - 1                                      │
│  • Detecta value si: P_modelo > P_mercado + 5%                   │
│  • Monitorea "dinero inteligente" (caída brusca de cuotas =      │
│    profesionales apostando al resultado → señal informativa)      │
│  • Modelos alternativos: Hándicap Asiático, Over/Under           │
│                                                                   │
│  Solo se activa si ctx.odds tiene cuotas disponibles              │
│  Output: delta_P proporcional a la discrepancia modelo vs mercado│
└───────────────────────────────────────────────────────────────────┘
```

#### Agente 4: Media-Sentiment-Parser
```
┌───────────────────────────────────────────────────────────────────┐
│  MEDIA-SENTIMENT-PARSER                                           │
│  Rol: Analista de sentimiento y psicología de grupo               │
│  Tipo: LLM (DeepSeek → Anthropic fallback)                       │
│  Peso en blend: 10%                                               │
│                                                                   │
│  Qué analiza:                                                     │
│  • Presión mediática (crisis pública = baja resiliencia)          │
│  • Cohesión interna del equipo (filtraciones, conflictos)         │
│  • Efecto "underdog": equipos sin presión mediática pueden        │
│    rendir por encima del ELO (Arabia Saudita vs Argentina 2022)  │
│  • Psicología en penales (equipos con historial de colapso)      │
│                                                                   │
│  Output: "Termómetro Psicológico" 0-100 + delta_P                │
│  Solo se activa si ctx.media_notes contiene información           │
└───────────────────────────────────────────────────────────────────┘
```

#### Agente 5: Travel-Logistics-Quant
```
┌───────────────────────────────────────────────────────────────────┐
│  TRAVEL-LOGISTICS-QUANT                                           │
│  Rol: Analista de fatiga y logística de desplazamiento           │
│  Tipo: HÍBRIDO (determinístico haversine + LLM para contexto)    │
│  Peso en blend: 10%                                               │
│                                                                   │
│  Qué analiza:                                                     │
│  • Distancia real entre ciudades sedes (fórmula haversine):      │
│    Penaliza +1km/1000km sin descanso extendido                   │
│  • Jet lag: cruce de zonas horarias con < 48h de adaptación      │
│    (Pacífico → Este = -4h → impacto en reacción y pase largo)   │
│  • Altitud: Ciudad de México (2.250m), Guadalajara (1.560m)      │
│    → equipos de nivel del mar pierden capacidad aeróbica         │
│    en los últimos 30 min del partido                              │
│                                                                   │
│  Siempre se activa (determinístico, sin costo LLM)               │
│  Output: multiplicador de stamina + delta_P por fatiga           │
└───────────────────────────────────────────────────────────────────┘
```

#### Agente 6: FIFA-Regs-Strategist
```
┌───────────────────────────────────────────────────────────────────┐
│  FIFA-REGS-STRATEGIST                                             │
│  Rol: Ingeniero de formato y desempates del torneo               │
│  Tipo: DETERMINÍSTICO (sin LLM)                                   │
│  Peso en blend: 5%  ← el menor (ajuste estructural puntual)      │
│                                                                   │
│  Qué analiza:                                                     │
│  • Tabla de 3eros de cada grupo: calcula puntos necesarios        │
│  • Presión de clasificación: ¿este partido es "o gano o estoy    │
│    eliminado"? → la presión modifica la probabilidad de un        │
│    equipo desesperado de atacar más (más goles, más varianza)    │
│  • Bracket optimization: ¿terminar 2do en lugar de 1ro da        │
│    un camino más fácil en la fase de eliminación?                │
│  • Altitud de la sede del partido (determinístico, sin LLM)      │
│                                                                   │
│  Siempre se activa (determinístico, sin costo LLM)               │
│  Output: ajuste estructural de bracket + delta_P                 │
└───────────────────────────────────────────────────────────────────┘
```

### 6.3 Tabla resumen de agentes

| Agente | Tipo | Peso | Se activa cuando | Señal principal |
|---|---|---|---|---|
| Roster-Data-Scout | LLM | 30% | ctx.injuries disponible | Lesiones clave, impacto WAR |
| IntMatch-Analytics-Pro | LLM | 25% | Siempre (grupos) | Táctica, clima, suspensiones |
| FinOps-Bookmaker-Alpha | Determinístico | 20% | ctx.odds disponible | Discrepancia modelo vs mercado |
| Media-Sentiment-Parser | LLM | 10% | ctx.media_notes disponible | Presión mediática, cohesión |
| Travel-Logistics-Quant | Híbrido | 10% | Siempre | Fatiga, altitud, jet lag |
| FIFA-Regs-Strategist | Determinístico | 5% | Siempre | Presión clasificatoria, bracket |

### 6.4 Cómo el Orchestrator combina los agentes

```
PROCESO DE BLENDING
────────────────────────────────────────────────────────────────────

PRIOR del Ensemble:  H=40.4%  D=27.6%  A=32.0%

Agentes llamados (ejemplo fase de grupos):
  IntMatch:   delta = {H: +2.0%, D: +0.5%, A: -2.5%}  conf=0.85  peso=0.25
  Travel:     delta = {H: 0.0%,  D: 0.0%,  A: 0.0%}   conf=0.10  peso=0.10
  FIFA-Regs:  delta = {H: +0.5%, D: 0.0%,  A: -0.5%}  conf=0.10  peso=0.05

Blend ponderado por confianza × peso:
  delta_H = (2.0×0.85×0.25) + (0.0×0.10×0.10) + (0.5×0.10×0.05)
          = 0.425 + 0 + 0.0025 = 0.427

Clampeo:
  Total shift máximo = ±12%
  Si el delta total supera 12%, se escala proporcionalmente

RESULTADO FINAL:
  H: 40.4% + ajuste → ~42.1%
  D: 27.6% + ajuste → ~26.8%
  A: 32.0% + ajuste → ~31.1%
  ────────────────────────────
  TOTAL: 100.0%  ✓
```

---

## 7. Flujo Completo de Predicción por Partido

```
EJEMPLO: Colombia vs Alemania, Fase de grupos, Ciudad de México

INPUT
─────
  • Colombia ELO: 1.840
  • Alemania ELO: 2.050
  • Sede: Ciudad de México (altitud 2.250m, neutral)
  • Forma reciente Colombia: 1.4 goles/partido
  • Forma reciente Alemania: 1.8 goles/partido
  • H2H: Colombia 20% victorias históricas vs Alemania
  • Partido sin lesiones relevantes reportadas

                           │
                           ▼
PASO 1 — ENSEMBLE
─────────────────
  ELO:     H=28.4% D=24.1% A=47.5%
  Poisson: H=30.1% D=25.8% A=44.1%
  XGBoost: H=29.2% D=24.9% A=45.9%
  ─────────────────────────────────
  Blend:   H=29.6% D=25.4% A=45.0%   ← PRIOR para agentes

                           │
                           ▼
PASO 2 — AGENTES (fase de grupos → máx. 3)
───────────────────────────────────────────
  Orchestrator selecciona: IntMatch + Travel + FIFA-Regs

  IntMatch (LLM):
    Detecta: Ciudad de México, calor → Alemania (equipo de alta presión)
    sufre en min 60+ en altitud. Colombia juega en bloque bajo.
    delta = {H: +1.5%, D: +0.8%, A: -2.3%}  conf=0.78

  Travel (determinístico):
    Alemania llegó de Guadalajara (vuelo corto, OK)
    Altitud: ambos llevan 10 días en México, aclimatados
    delta = {H: 0%, D: 0%, A: 0%}  conf=0.10

  FIFA-Regs (determinístico):
    Colombia necesita ganar para asegurar clasificación
    → ligera presión clasificatoria a favor de Colombia
    delta = {H: +0.5%, D: 0%, A: -0.5%}  conf=0.15

  Blend ponderado + clampeo ±12%:
    Final delta: H +1.8%, D +0.7%, A -2.5%

                           │
                           ▼
RESULTADO FINAL
───────────────
  Colombia gana:  31.4%
  Empate:         26.1%
  Alemania gana:  42.5%

  Marcador más probable: 1-2 (Poisson)
  Narración: generada por DeepSeek en dialecto bogotano
             "Uy parce, Alemania llega mandando, pero en la
              altura del DF, quién sabe..."
```

---

## 8. El Sistema de Retroalimentación

El modelo **no hace online learning** (no actualiza sus parámetros durante el torneo). Lo que sí se actualiza continuamente es el **sistema ELO**, que es la señal más importante del Ensemble:

```
CICLO DE RETROALIMENTACIÓN
───────────────────────────────────────────────────────────────────

  ANTES del partido:
    Colombia ELO = 1.840 │ Alemania ELO = 2.050
    Predicción: Colombia 31.4% │ Empate 26.1% │ Alemania 42.5%
                    │
                    │ partido se juega
                    ▼
  RESULTADO REAL:  Colombia 2 - Alemania 1  (SORPRESA)
                    │
                    ▼
  UPDATE ELO:
    Colombia ganó siendo el underdog → ELO_Colombia += grande
    K = 60 (Mundial) × MarginMult = log(1+1) = 0.693
    ELO_Colombia_nuevo ≈ 1.840 + 60 × (1 - 0.296) × 0.693 ≈ 1.869
    ELO_Alemania_nuevo ≈ 2.050 - 60 × 0.704 × 0.693 ≈ 2.021
                    │
                    ▼
  RETRAIN XGBoost:
    El nuevo ELO de Colombia se incluye en las features
    XGBoost se reentrena desde cero (~1s de entrenamiento)
    Las predicciones de los próximos partidos de Colombia
    reflejan que acaba de vencer a Alemania
                    │
                    ▼
  EXPORT:
    live_predictions.json actualizado
    Colombia vs Marruecos: ya no es Colombia 31% sino ~35%
    (Colombia sube, sus próximos rivales "sienten" que subió)
```

### Ciclo operativo diario

```
CADA MAÑANA CON PARTIDOS:

  football-data.org
        │
        ▼
  update_wc_results.py  →  results.csv (NA → marcadores reales)
        │
        ▼
  run_pipeline.py       →  ELO recalculado + XGBoost reentrenado
        │
        ▼
  export_frontend_data.py → predictions.json / group_standings.json
        │
        ▼
  predict_live.py --export → live_predictions.json (+ agentes IA)
        │
        ▼
  precompute_narrations.py → narrations.json (DeepSeek, 1×/partido)
        │
        ▼
  vercel --prod           → frontend actualizado en producción (~30s)

DURACIÓN TOTAL: ~90 segundos
```

---

## 9. Monte Carlo — Proyecciones del Torneo

El Monte Carlo convierte probabilidades de partido individuales en probabilidades de torneo completo.

```
ALGORITMO DE SIMULACIÓN
────────────────────────────────────────────────────────────────────

INPUT: 1.128 pares de equipos con sus probabilidades H/D/A pre-calculadas

Por cada simulación (×5.000):
  ┌─────────────────────────────────────────────────────────────┐
  │  FASE DE GRUPOS (72 partidos)                               │
  │                                                             │
  │  Para cada partido del grupo:                               │
  │    random_roll = random() en [0, 1]                         │
  │    if random_roll < p_home → team1 gana                    │
  │    elif random_roll < p_home + p_draw → empate             │
  │    else → team2 gana                                        │
  │                                                             │
  │    Desempate en tabla: GD → GF → H2H → azar                │
  │                                                             │
  │  Top 2 de cada grupo + mejores 8 terceros → 32 equipos     │
  └──────────────────────┬──────────────────────────────────────┘
                         │
  ┌──────────────────────▼──────────────────────────────────────┐
  │  FASE ELIMINATORIA (ronda de 32 → final)                    │
  │                                                             │
  │  Bracket oficial WC 2026 (64 equipos → 32 → 16 → 8 → 4 → 2)│
  │  Empates en 90': penales (tasas históricas por equipo)      │
  │  Host advantage: EE.UU., México, Canadá tienen +100 ELO    │
  └──────────────────────┬──────────────────────────────────────┘
                         │
                         ▼
  CONTADOR:
    Por cada simulación, registrar cuántas veces llegó
    cada equipo a: Grupos → R32 → R16 → QF → SF → Final → Campeón

RESULTADO (5.000 simulaciones):
  Argentina campeón:  18.3% (918 de 5.000 simulaciones)
  Francia campeón:    14.1%
  Brasil campeón:     12.7%
  ...
```

**¿Por qué client-side?** Con 1.128 pares pre-calculados en el JSON, el navegador puede correr las 5.000 simulaciones en ~200ms. No se necesita ninguna llamada al servidor. Esto también permite al usuario fijar resultados manualmente y ver cómo cambian las proyecciones en tiempo real.

---

## 10. Narrator AI — Narración Regional Sin Costo Por Usuario

```
SISTEMA DE NARRACIÓN
────────────────────────────────────────────────────────────────────

FASE DE GENERACIÓN (una vez al día, servidor Python):

  precompute_narrations.py
        │
        ├─ Carga live_predictions.json (probabilidades + agentes)
        ├─ Carga teams.json (ELO, historial, goles promedio)
        ├─ Computa tabla del grupo desde wc2026_live_results.csv
        │    → si hay partidos jugados, incluye pts/GD/GF reales
        │
        ├─ Para cada partido de HOY:
        │    ├─ FASE DE GRUPOS: solo dialecto bogotano
        │    └─ FASE ELIMINATORIA: 5 dialectos (auto)
        │
        └─ Llama a DeepSeek (1 llamada × partido × dialectos)
             → guarda en narrations.json con clave "Home|Away|dialecto"

EJEMPLO DE PAYLOAD ENVIADO A DEEPSEEK:
{
  "home": "Colombia",
  "away": "Alemania",
  "dialecto": "bogotano",
  "prob_home": 31.4,
  "prob_draw": 26.1,
  "prob_away": 42.5,
  "elo_home": 1840,
  "elo_away": 2050,
  "group_standings": [
    {"pos": 1, "team": "Brasil", "pts": 3, "GD": +2},
    {"pos": 2, "team": "Colombia", "pts": 3, "GD": +1}
  ],
  "agent_summary": [
    {"agent": "IntMatch", "note": "Altitud favorece a Colombia..."}
  ]
}

FASE DE CONSUMO (usuario en el navegador):

  page.tsx carga narrations.json al inicio (JSON estático, CDN)
        │
        ▼
  Usuario selecciona partido en Predictor
        │
        ▼
  UnifiedNarration busca clave "Colombia|Alemania|bogotano"
        │
        ├─ ENCONTRADA → muestra texto pre-generado (costo: $0)
        └─ NO ENCONTRADA → llama /api/narrator → DeepSeek en vivo

DIALECTOS DISPONIBLES:
  bogotano  → "uy parce, qué visaje, esto está pesado, pailas"
  paisa     → "qué cosa tan brava, con verraquera, ojo pues"
  costeño   → "eche compae, esa vaina, se prendió esto"
  boyacense → "sumercé, ala, la vaina está brava, no se achante"
  en        → sharp analytical commentator, no fluff
```

**Costo por usuario: $0** (el texto ya está calculado)
**Costo diario: ~$0.003** durante fase de grupos (bogotano × ~8 partidos)

---

## 11. Chat IA — Tres Capas de Protección de Costos

```
FLUJO DEL CHAT
────────────────────────────────────────────────────────────────────

  Usuario pregunta: "¿Quién gana hoy?"
                    │
                    ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  CAPA 1: TOPIC FILTER                                          │
  │  Regex de términos de fútbol (español/inglés/portugués)        │
  │  ¿La pregunta es sobre fútbol/mundial?                         │
  │  NO → respuesta canned: "Solo respondo sobre el Mundial"       │
  │  SÍ → continúa                                  (costo: $0)   │
  └────────────────────────────────────────┬───────────────────────┘
                                           │
                                           ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  CAPA 2: RESPONSE CACHE                                        │
  │  SHA-256 de la pregunta normalizada                            │
  │  ¿Respuesta cacheada y < 2h de antigüedad?                    │
  │  SÍ → devuelve caché                            (costo: $0)   │
  │  NO → continúa        (max 400 entradas, TTL 2h)              │
  └────────────────────────────────────────┬───────────────────────┘
                                           │
                                           ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  CAPA 3: RATE LIMIT                                            │
  │  Sliding window: 20 requests/hora por IP                      │
  │  Excedido → HTTP 429, Retry-After: 3600                        │
  └────────────────────────────────────────┬───────────────────────┘
                                           │
                                           ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  TOURNAMENT CONTEXT INJECTION (siempre, sin RAG)               │
  │  • Partidos de hoy (filtro UTC sobre group_matches.json)       │
  │  • Tabla de grupos actual (group_standings.json)               │
  │  Garantiza que el chat siempre sabe qué se juega hoy           │
  └────────────────────────────────────────┬───────────────────────┘
                                           │
                                           ▼
  ┌────────────────────────────────────────────────────────────────┐
  │  RAG (opcional, si DASHSCOPE_API_KEY configurada)             │
  │  • Embedding de la pregunta (Qwen3 text-embedding-v3, 512d)   │
  │  • Similitud coseno sobre rag_index.json                       │
  │  • Top-5 chunks inyectados en el system prompt                │
  └────────────────────────────────────────┬───────────────────────┘
                                           │
                                           ▼
  DeepSeek streaming → respuesta al usuario
  (Anthropic claude-sonnet-4-6 como fallback si DeepSeek falla)
```

---

## 12. Frontend — Pestañas y Qué Muestra Cada Una

```
ARQUITECTURA FRONTEND
────────────────────────────────────────────────────────────────────

  Next.js 15 · React 19 · Tailwind CSS · Recharts · Framer Motion

  JSON estáticos (CDN, sin servidor):
    teams.json           → ratings ELO, banderas, historial
    predictions.json     → 2.256 probabilidades (1.128 pares × 2)
    live_predictions.json → predicciones ajustadas por agentes
    narrations.json      → narración pre-generada por partido × dialecto
    group_matches.json   → fixture de grupos con probabilidades
    group_standings.json → proyecciones Monte Carlo de posiciones
    goalscorers.json     → histórico de goleadores

  Actualizaciones en vivo (cada 5 min):
    /api/live → proxy football-data.org → marcadores WC 2026
```

### Las 7 Pestañas

| Pestaña | Qué muestra | Fuente de datos |
|---|---|---|
| **En Vivo** | Marcadores del día, veredicto modelo vs resultado, tabla en vivo | liveMatches + predictions.json |
| **Predictor** | Probabilidades de cualquier cruce, narración regional, marcador probable | live_predictions.json + narrations.json |
| **Grupos** | Fixture de los 12 grupos, posiciones actuales, proyección clasificación | group_matches.json + liveScores |
| **Proyecciones** | % de cada selección por ronda (Knockout) + simulador manual (Monte Carlo) | live_predictions.json + liveMatches |
| **Stats** | Goles del torneo, equipos goleadores, partidos más goleadores, sorpresas | liveMatches (calculado en cliente) |
| **Modelo** | Precisión por jornada J1/J2/J3/FG, desglose por grupo, top errores | groupMatches + liveScores (cliente) |
| **Chat IA** | Preguntas libres sobre el mundial con contexto real del torneo | /api/chat → DeepSeek + RAG |

---

## 13. Observabilidad y Control de Costos

```
SISTEMA DE COSTOS Y LOGS
────────────────────────────────────────────────────────────────────

  configs/budget.yaml
  ├── daily_limit_usd: 2.00
  ├── monthly_limit_usd: 50.00
  └── per_run_limit_calls: 5

  CostGuard (src/cost_guard.py):
    Antes de CADA llamada LLM:
      ├─ Lee logs/llm_costs.jsonl
      ├─ Suma gasto del día / mes
      ├─ Si excede límite → raise BudgetExceeded
      └─ Orchestrator atrapa BudgetExceeded → fallback determinístico

  Logs:
    logs/llm_costs.jsonl   → una entrada por llamada LLM
    logs/pipeline_runs.jsonl → una entrada por corrida del pipeline

COSTO ESTIMADO COMPLETO DEL TORNEO (36 días):
  Fase grupos (MD1+MD2+MD3):
    narrations.json: ~$0.003/día × 30 días = ~$0.09
    predict_live.py (agentes): < $0.01/día × 30 días = ~$0.30
  Fase eliminatoria:
    narrations.json: ~$0.015/día × 6 días = ~$0.09
    predict_live.py: < $0.01/día × 6 días = ~$0.06
  Chat (70-80% cache hit rate): ~$0.01/día × 36 días = ~$0.36
  ─────────────────────────────────────────────────────────────────
  TOTAL ESTIMADO: ~$0.90 para cubrir TODO el torneo con $5 DeepSeek
```

---

## 14. Métricas de Rendimiento del Modelo

### Benchmark: Qatar 2022 (test set — nunca visto por el modelo)

```
COMPARACIÓN DE MODELOS
────────────────────────────────────────────────────────────────────

  Métrica         │ Aleatorio │ ELO solo │ Poisson  │ XGBoost  │ Ensemble
  ────────────────┼───────────┼──────────┼──────────┼──────────┼──────────
  Accuracy        │   33.3%   │  50.0%   │  48.4%   │  48.4%   │  50.0%
  Log-loss        │   1.099   │  1.063   │  1.062   │  1.025   │  ~1.04
  RPS             │   0.333   │  0.220   │  0.218   │  0.217   │  ~0.216
  Brier score     │   0.222   │  0.205   │  0.204   │  0.203   │  ~0.204
  ────────────────┴───────────┴──────────┴──────────┴──────────┴──────────

  RPS = Ranked Probability Score (métrica principal)
  Menor RPS = mejor predicción de probabilidades (calibración)
  Las casas de apuestas rondan RPS 0.195-0.200 con información en tiempo real
```

### ¿Qué significa accuracy 50%?

```
En un partido de fútbol hay 3 resultados posibles (casa, empate, visitante).
Un modelo aleatorio acierta 33.3%.
Las casas de apuestas en predicción pura rondan 55-58%.
Nuestro modelo: 50-52% → una mejora real sobre el azar.

El modelo es más valioso en la CALIBRACIÓN de probabilidades que en el
"ganador" único, porque el simulador Monte Carlo necesita probabilidades
correctas para proyectar el torneo completo.
```

---

## 15. Modelos de IA Utilizados

El sistema usa **un solo modelo DeepSeek activo** (`deepseek-chat`) para todo, con Anthropic como fallback. Hay un segundo modelo DeepSeek reservado pero aún no activo.

### Mapa completo

```
┌────────────────────────────────────────────────────────────────────────────────┐
│  USO               │ MODELO              │ DÓNDE               │ TEMPERATURA  │
├────────────────────┼─────────────────────┼─────────────────────┼──────────────┤
│ Agentes IA         │ deepseek-chat        │ Python: _llm.py     │ default      │
│ (IntMatch, Roster, │                      │                     │ max_tok: 512 │
│  Media)            │                      │                     │              │
├────────────────────┼─────────────────────┼─────────────────────┼──────────────┤
│ Narrations diarias │ deepseek-chat        │ Python:             │ default      │
│ pre-computadas     │                      │ precompute_         │ max_tok: 1400│
│                    │                      │ narrations.py       │              │
├────────────────────┼─────────────────────┼─────────────────────┼──────────────┤
│ Chat IA            │ deepseek-chat        │ TypeScript:         │ 0.65         │
│ (preguntas usuario)│                      │ /api/chat/route.ts  │ max_tok: 700 │
│                    │                      │ streaming=true      │              │
├────────────────────┼─────────────────────┼─────────────────────┼──────────────┤
│ Narrator fallback  │ deepseek-chat        │ TypeScript:         │ 0.90         │
│ (narración en vivo │                      │ /api/narrator/      │ max_tok: 400 │
│ si no hay caché)   │                      │ route.ts            │              │
└────────────────────┴─────────────────────┴─────────────────────┴──────────────┘
```

### deepseek-chat — el modelo principal

**¿Qué es?** DeepSeek-V3, modelo de lenguaje general de 671B parámetros (MoE). Equivalente en capacidad a GPT-4o pero **~20× más barato**.

**¿Por qué se eligió?**
- Costo: $0.14/MTok vs $5–15/MTok de modelos similares de OpenAI/Anthropic
- API compatible con el SDK de OpenAI (base_url = `https://api.deepseek.com`) → cambiar de proveedor es cambiar una URL
- Suficiente para las 4 tareas que hace: análisis táctico, narración regional, chat de preguntas, respuestas de agentes
- Razonamiento sólido en español con jerga futbolera regional

**Costo estimado por uso:**
```
Narrations fase grupos (~8 partidos/día):   ~$0.003/día
Agentes IA por partido:                     < $0.001/partido
Chat (70-80% cache hit):                    < $0.01/día
────────────────────────────────────────────────────────
Total torneo completo (36 días):            ~$0.90
```

### deepseek-reasoner — reservado, NO activo

**¿Qué es?** DeepSeek-R1, modelo con razonamiento en cadena (chain-of-thought interno). Piensa antes de responder, mejor en problemas complejos con múltiples pasos.

**Estado actual:** declarado en `configs/budget.yaml` con su costo ($0.55/MTok, ~4× más caro que deepseek-chat) pero **ningún lugar del código lo llama**. Es una reserva para futuras tareas que lo justifiquen.

**Caso de uso potencial:** análisis de escenarios de clasificación complejos (MD3, "¿qué necesita X para avanzar si Y gana?") donde el razonamiento paso a paso reduce errores lógicos. Hoy ese cálculo lo hace `FIFA-Regs-Strategist` de forma determinística.

### Fallback: Anthropic Claude

Si `DEEPSEEK_API_KEY` no está configurada o falla (error 402 = saldo agotado, error 5xx), el sistema cae automáticamente a:

```
Python (agentes):    claude-haiku-4-5-20251001  (más barato de Anthropic)
TypeScript (chat):   claude-sonnet-4-6           (mejor calidad, para chat)
```

Los alias de Claude en los agentes Python (`"claude-haiku-4-5-20251001"`, `"claude-sonnet-4-6"`) se redirigen automáticamente a `deepseek-chat` en `_MODEL_MAP` — así los agentes no necesitan saber qué proveedor está activo.

### Por qué el Narrator usa temperatura 0.90 y el Chat usa 0.65

```
Narrator (0.90):  narración futbolera — se quiere variedad, colorido,
                  frases con personalidad. La exactitud factual la
                  imponen los datos del payload (probabilidades, ELO).

Chat (0.65):      preguntas sobre el torneo — se quiere respuesta
                  coherente y precisa. Más determinismo, menos varianza.

Agentes (default ≈ 1.0):  delta_P se extrae del JSON que retorna el
                  agente, no del texto libre — la temperatura alta no
                  importa porque solo se parsea el bloque JSON.
```

---

## 16. Stack Tecnológico Completo

```
PYTHON (backend / pipeline)
  pandas         → manipulación de datos
  numpy          → álgebra lineal, Monte Carlo interno
  xgboost        → modelo de boosting
  scikit-learn   → calibración, métricas, validación cruzada
  scipy          → distribución de Poisson
  joblib         → serialización de modelos (.pkl)
  openai         → cliente DeepSeek (compatible con OpenAI SDK)
  anthropic      → fallback LLM
  requests       → fetch football-data.org

JAVASCRIPT / TYPESCRIPT (frontend)
  Next.js 15     → App Router, Server Components, API Routes
  React 19       → UI reactiva, hooks
  Tailwind CSS   → diseño utility-first
  Framer Motion  → animaciones
  Recharts       → gráficos (barras, líneas)

INFRAESTRUCTURA
  Vercel         → hosting frontend + serverless API routes
  football-data.org → resultados WC 2026 en vivo (API REST)
  DeepSeek       → LLM primario (narrations, agentes, chat)
  Anthropic      → LLM fallback
  DashScope      → embeddings RAG (Qwen3 text-embedding-v3)
```

---

## 16. Glosario de Términos Clave

| Término | Definición |
|---|---|
| **ELO** | Sistema de rating que mide la fortaleza relativa de un equipo basado en victorias/derrotas históricas. Actualización: K × (resultado - esperado) |
| **RPS** | Ranked Probability Score — métrica de calibración de probabilidades. Menor = mejor. El azar = 0.333 |
| **delta_P** | Ajuste porcentual que un agente aplica al prior del Ensemble. Ej: +2% a H, -2% a A |
| **prior** | Probabilidad base calculada por el Ensemble antes de la corrección de agentes |
| **posterior** | Probabilidad final tras el ajuste de agentes |
| **anti-leakage** | El ELO se calcula con un cutoff de 60s antes del kickoff. No incluye el resultado del partido que se está prediciendo |
| **Monte Carlo** | Técnica estadística que corre miles de simulaciones aleatorias para estimar probabilidades complejas |
| **Poisson bivariado** | Distribución estadística que modela el número esperado de goles de cada equipo como variables independientes |
| **isotonic calibration** | Técnica que asegura que si el modelo dice 70%, el equipo gana ~70% de las veces en el histórico |
| **walk-forward validation** | Validación temporal: entrena hasta año N, testea en N+1, avanza. Evita leakage de series temporales |
| **temporal split** | División train/test respetando el orden cronológico (no aleatorio) |
| **narrations.json** | Archivo JSON pre-generado con narración de cada partido × dialecto. Costo por usuario: $0 |
| **live_predictions.json** | Probabilidades ajustadas por agentes para los partidos WC 2026 pendientes. Se actualiza diariamente |
| **CostGuard** | Módulo Python que lee budget.yaml y bloquea llamadas LLM antes de exceder límites diarios/mensuales |
| **Ensemble** | Combinación ponderada de ELO (22%) + Poisson (58%) + XGBoost (20%) para máxima robustez |
