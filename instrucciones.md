# Instrucciones Diarias — Mundial Predictor 2026

---

> ## ⚠️ Regla de oro: corré SIEMPRE desde la raíz del proyecto
>
> Todos los `python scripts/...` se ejecutan desde la **raíz**
> (`.../mundial-predictor-master`), **no** desde `frontend/`.
>
> El deploy lleva `cd frontend` adentro. Si lo corrés como `cd frontend && npx vercel --prod`,
> tu shell **queda dentro de `frontend/`** y la próxima corrida falla con:
> `can't open file '...\frontend\scripts\live_update.py': No such file or directory`.
>
> **Por eso el deploy va entre paréntesis** — `(cd frontend && npx vercel --prod)` — un
> subshell que despliega y **te deja en la raíz**. Si igual quedaste adentro, volvé con `cd ..`.
>
> Antes de empezar, confirmá dónde estás:
> ```bash
> pwd        # debe terminar en .../mundial-predictor-master
> ls scripts # debe listar live_update.py, predict_live.py, ...
> ```

---

## Ciclo base (todos los días con partidos)

```bash
# 0. Asegurate de estar en la raíz (NO en frontend/)
pwd        # → .../mundial-predictor-master

# 1. Descarga resultados de ayer, recalcula ELO, reentrena modelo (~90s)
python scripts/live_update.py

# 2. Recalcula predicciones con agentes
python scripts/predict_live.py --export

# 3. Genera narraciones para los partidos de HOY solamente
python scripts/precompute_narrations.py        # Default: --days 0

# 3.5 Opcional: Agent Debate (predicción sin ML) para partidos puntuales que quieras
#     analizar con los 3 agentes — no hay corrida masiva automática, se elige partido
#     por partido. Acumulativo: no pisa debates previos, omite si ya existe salvo --force.
python scripts/run_agent_debate.py "Mexico" "South Korea"
python scripts/export_frontend_data.py

# 4. Despliega a producción — el subshell (...) deja tu shell en la raíz al terminar
(cd frontend && npx vercel --prod)
```

---

## Ciclo ampliado — días con doble horario (MD2 / J2)

En los días de MD2, cada día tiene **4 partidos de 2 grupos distintos**, divididos en dos bloques horarios (tarde y noche). Los resultados del bloque de la tarde cambian la presión clasificatoria para los partidos de la noche del mismo día.

**Protocolo: correr dos veces (solo HOY, sin futuros).**

```bash
# --- MAÑANA (antes del primer partido del día) --- (desde la raíz)
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py        # Solo HOY (default: --days 0)
(cd frontend && npx vercel --prod)             # subshell: vuelve a la raíz

# --- TARDE (después de los 2 primeros partidos, antes de los 2 nocturnos) ---
python scripts/live_update.py                  # registra resultados de tarde
python scripts/predict_live.py --export        # recalcula ELO y presión (solo lo que cambió)
python scripts/precompute_narrations.py        # Regenera SOLO el grupo afectado por la tarde
(cd frontend && npx vercel --prod)             # ~30s, actualiza narrativa y vuelve a la raíz
```

**Por qué importa:** si México pierde el partido de las 3 PM, el partido de las 8 PM se convierte en eliminatoria de facto. La narración de la mañana no lo sabe; la de la tarde sí.

**La segunda corrida no recalcula todo.** Tanto `predict_live.py --export` como `precompute_narrations.py` usan **cache por contexto**: solo recalculan los partidos/narraciones cuyo grupo cambió de tabla o presión por los resultados de la tarde. Lo generado en la mañana que sigue vigente (otros grupos, partidos sin cambios) **se conserva tal cual, sin gastar tokens**. Ambas corridas trabajan **solo sobre hoy**.

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
# Solo una corrida, en la mañana antes del primer pitazo (HOY solamente). Desde la raíz.
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py        # Default: --days 0 (solo HOY)
(cd frontend && npx vercel --prod)             # subshell: vuelve a la raíz
```

**Nota:** El default es ahora `--days 0` (solo hoy). No uses `--days 6` o valores altos — consume tokens innecesarios en días sin partidos del torneo.

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
- **Cache por contexto:** solo vuelve a llamar a los agentes LLM de un partido si su
  contexto de grupo cambió desde la última corrida. Si nada cambió, reusa el resultado
  ya calculado (0 tokens). Por eso correrlo dos veces el mismo día solo recalcula los
  grupos que jugaron. Usa `--force-agents` para ignorar el cache y recalcular todo.
- Los agentes Travel y FIFARegs son determinísticos (siempre funcionan sin API key).
- IntMatch usa DeepSeek — si falla por saldo, los otros dos agentes igual corren.

**`precompute_narrations.py`**
- Genera narraciones y previas **solo para los partidos de HOY** (no toca días futuros).
- **Cache por contexto:** regenera una narración/previa solo si el contexto de ese
  grupo cambió desde la última corrida del día (tabla, puntos, presión, notas de
  agentes). Si nada cambió para ese grupo, **conserva lo ya generado y no gasta
  tokens**. Es lo que hace barata la segunda corrida de MD2 (ver más abajo).
  - Ejemplo: si en la mañana generaste los 4 partidos de hoy y en la tarde solo
    jugó un grupo, la corrida de la tarde regenera **solo ese grupo** (el que
    cambió de tabla/presión); las narraciones de la mañana de los otros grupos se
    quedan intactas.
- La vigencia se guarda en `data/processed/narrations_sig.json` y
  `group_narratives_sig.json` (internos, gitignored). Bórralos si querés forzar
  una regeneración total.
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
| `can't open file '...\frontend\scripts\live_update.py': No such file or directory` | Tu shell quedó **dentro de `frontend/`** (por un `cd frontend` previo). Volvé a la raíz con `cd ..` y verificá con `pwd` (debe terminar en `mundial-predictor-master`). Para que no vuelva a pasar, desplegá con `(cd frontend && npx vercel --prod)` entre paréntesis. |
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
| Agent Debate (1 partido, 3 agentes × 3 rondas, deepseek-reasoner) | ~$0.08–0.10 |

Con $5 en DeepSeek se cubre holgadamente todo el torneo. El Agent Debate es notablemente más caro por partido que el resto del ciclo (usa `deepseek-reasoner`, no `deepseek-chat`, y corre 9 llamadas por partido) — por eso no se corre masivamente para todos los partidos de una jornada, sino partido por partido cuando se quiere comparar contra el modelo ML.

> **Nota:** Durante fase de grupos solo se genera dialecto **bogotano**. Al arrancar la fase eliminatoria (Round of 32, ~Jul 1), el script genera automáticamente los 5 dialectos sin cambiar nada.
