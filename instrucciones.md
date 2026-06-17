# Instrucciones Diarias — Mundial Predictor 2026

---

## Ciclo base (todos los días con partidos)

```bash
# 1. Descarga resultados de ayer, recalcula ELO, reentrena modelo (~90s)
python scripts/live_update.py

# 2. Recalcula predicciones con agentes
python scripts/predict_live.py --export

# 3. Genera narraciones para los partidos de HOY
python scripts/precompute_narrations.py

# 4. Despliega a producción
cd frontend && npx vercel --prod
```

---

## Ciclo ampliado — días con doble horario (MD2)

En los días de MD2, cada día tiene **4 partidos de 2 grupos distintos**, divididos en dos bloques horarios (tarde y noche). Los resultados del bloque de la tarde cambian la presión clasificatoria para los partidos de la noche del mismo día.

**Protocolo: correr dos veces.**

```bash
# --- MAÑANA (antes del primer partido del día) ---
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py        # cubre los 4 partidos del día
cd frontend && npx vercel --prod

# --- TARDE (después de los 2 primeros partidos, antes de los 2 nocturnos) ---
python scripts/live_update.py                  # registra resultados de tarde
python scripts/predict_live.py --export        # recalcula ELO y presión
python scripts/precompute_narrations.py        # regenera solo los 2 partidos nocturnos
cd frontend && npx vercel --prod               # ~30s, actualiza la narrativa
```

**Por qué importa:** si México pierde el partido de las 3 PM, el partido de las 8 PM se convierte en eliminatoria de facto. La narración generada en la mañana no lo sabe; la de la tarde sí.

### Calendario MD2 (doble corrida)

| Fecha | Grupos | Partidos |
|---|---|---|
| Jun 18 | A + B | Czech R. vs S.Africa · Mexico vs S.Korea · Switzerland vs Bosnia · Canada vs Qatar |
| Jun 19 | C + D | Scotland vs Morocco · Brazil vs Haiti · USA vs Australia · Turkey vs Paraguay |
| Jun 20 | E + F | Germany vs Ivory Coast · Ecuador vs Curazao · Netherlands vs Sweden · Tunisia vs Japan |
| Jun 21 | G + H | Belgium vs Iran · New Zealand vs Egypt · Spain vs Saudi Arabia · Uruguay vs Cape Verde |
| Jun 22 | I + J | France vs Iraq · Norway vs Senegal · Argentina vs Austria · Jordan vs Algeria |
| Jun 23 | K + L | Portugal vs Uzbekistan · Colombia vs DR Congo · England vs Ghana · Panama vs Croatia |

---

## MD3 — Partidos simultáneos (corrida única)

En la tercera jornada de cada grupo, **los dos partidos del grupo se juegan a la misma hora** (regla FIFA anti-amaño). No hay resultados de un partido que afecten al otro. Una sola corrida matutina es suficiente.

```bash
# Solo una corrida, en la mañana antes del primer pitazo
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py
cd frontend && npx vercel --prod
```

La narración de MD3 ya incluye el análisis de clasificación completo (tabla actual + escenarios posibles) gracias a que `group_standings` está en el payload y el modelo conoce los 6 posibles resultados que determinan quién avanza.

### Calendario MD3 (corrida única)

| Fecha | Grupos | Nota |
|---|---|---|
| Jun 24 | A, B, C | 6 partidos simultáneos por franjas |
| Jun 25 | D, E, F | 6 partidos simultáneos |
| Jun 26 | G, H, I | 6 partidos simultáneos |
| Jun 27 | J, K, L | 6 partidos simultáneos |

---

## Notas operativas

**`live_update.py`**
- Si no hay partidos nuevos desde la última corrida, imprime "Sin cambios" y no reentrena. Normal.
- Si falla con error de conexión, esperar 5 min y reintentar.

**`predict_live.py --export`**
- Genera `frontend/public/data/live_predictions.json` con probabilidades ajustadas por agentes.
- **Este paso es el que actualiza la pestaña Proyecciones** (por ronda y simulador). Sin él, las probabilidades de los partidos no jugados son las del último deploy.
- Los agentes Travel y FIFARegs son determinísticos (siempre funcionan sin API key).
- IntMatch usa DeepSeek — si falla por saldo, los otros dos agentes igual corren.

**`precompute_narrations.py`**
- Borra y regenera SIEMPRE las narraciones de los partidos de HOY (contexto fresco).
- No toca partidos de días futuros — su contexto se genera cuando llegue ese día.
- A partir de MD2: incluye la tabla real del grupo (puntos, GD, GF) en el payload a DeepSeek.
- Para MD1: la tabla está vacía (primer partido del grupo), comportamiento correcto.
- Argumento `--days N` para ampliar la ventana más allá de hoy (default 0 días adicionales).

**`vercel --prod`**
- Tarda ~30 segundos.
- URL de producción: https://frontend-three-black-wib8friwwy.vercel.app

---

## Si algo falla

| Problema | Solución |
|---|---|
| `live_update.py` → error football-data.org | Reintentar en 5 min. La API tiene límite de llamadas. |
| `predict_live.py` → IntMatch error 402 | Saldo DeepSeek agotado. Recargar en platform.deepseek.com |
| `precompute_narrations.py` → 0 partidos | Normal si no hay partidos hoy. No hace nada. |
| Vercel falla el build | Correr `npm run build` en `frontend/` para ver el error. |
| Narración tarde no refleja resultado de tarde | Verificar que `live_update.py` de tarde corrió antes de `precompute_narrations.py`. |

---

## Costo estimado por jornada

| Operación | Costo |
|---|---|
| `predict_live.py` (IntMatch, ~8 partidos) | < $0.01 |
| `precompute_narrations.py` fase grupos (~8 partidos × **1 dialecto** × 1500 tokens) | ~$0.003 |
| Segunda corrida de tarde MD2 (~4 partidos × 1 dialecto) | ~$0.002 |
| `precompute_narrations.py` fase eliminatoria (~4 partidos × **5 dialectos**) | ~$0.015 |
| Chat (cache absorbe ~70-80%) | < $0.01/día |
| **Total día fase grupos** | **~$0.015** |
| **Total día MD2 con doble corrida** | **~$0.017** |
| **Total día eliminatoria** | **~$0.025** |

Con $5 en DeepSeek se cubre holgadamente todo el torneo.

> **Nota:** Durante fase de grupos solo se genera dialecto **bogotano**. Al arrancar la fase eliminatoria (Round of 32, ~Jul 1), el script genera automáticamente los 5 dialectos sin cambiar nada.
