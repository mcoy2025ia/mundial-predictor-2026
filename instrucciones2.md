1# Instrucciones Diarias — Mundial Predictor 2026

---

## ⚙️ Lo más importante: el ciclo YA está automatizado

`.github/workflows/wc2026-live-update.yml` corre por cron **varias veces por jornada**
(timeado ~90 min después de la hora estimada de cada partido) durante todo el torneo,
hasta el 28 de junio. Cada corrida del CI hace, en este orden:

1. `live_update.py --force` (fetch resultados + retrain)
2. `predict_live.py --export`
3. `precompute_narrations.py`
4. `ci_debate_targets.py` → detecta partidos de grupo que arrancan en las próximas
   **36 horas** (`debate_window_hours`, configurable en `workflow_dispatch`) y corre
   `run_agent_debate.py` automáticamente para esos partidos
5. `export_frontend_data.py`
6. **commit + push** de `data/` + `frontend/public/data/` + `models/`
7. `npx vercel --prod` (deploy)

**Por defecto no necesitás correr nada a mano.** El ciclo manual de abajo es para:
- Forzar una actualización antes de que dispare el próximo cron (ej. querés ver un
  resultado ya mismo).
- Debatir con Agent Debate un partido que está **fuera de la ventana de 36h** del CI,
  o re-generar (`--force`) un debate puntual tras cambiar un prompt.
- Probar cambios en scripts/prompts antes de que el CI los corra con datos reales.
- Recuperar el sistema si el CI falló (ver tabla de errores).

> Mirá los cron schedules en el workflow para saber cuándo es la próxima corrida
> automática del día antes de decidir si vale la pena correr a mano.

---

## ⚠️ Regla de oro #1: sincronizá ANTES de correr nada a mano

El CI puede haber corrido (y pusheado) minutos antes de que vos arranques. Si no
sincronizás primero, vas a:
- Regenerar narraciones/debates que el CI ya generó (gasto de tokens duplicado).
- Terminar con contenido **distinto** para el mismo partido en local vs remoto
  (cada corrida de un agente LLM produce texto distinto aunque sea el mismo partido).
- Que tu `git push` final sea rechazado (`! [rejected] ... fetch first`).

```bash
git fetch origin
git log --oneline master..origin/master   # ¿hay commits nuevos del bot?
git pull origin master                     # si hay, traelos ANTES de correr scripts
```

Si ya corriste algo en local sin sincronizar y el push es rechazado, **no hagas
`git push --force`**. Resolución segura:

```bash
git reset --hard origin/master   # te alinea con lo que ya está en prod
```

y después rehacés a mano solo lo que el CI todavía no tiene (típicamente fusionar
`frontend/public/data/agent_debate_results.json` entrada por entrada si generaste
debates que el CI no había cubierto — ver "Conflictos de Agent Debate" abajo).

---

## ⚠️ Regla de oro #2: corré SIEMPRE desde la raíz del proyecto

> Todos los `python scripts/...` se ejecutan desde la **raíz**
> (`.../mundial-predictor-master`), **no** desde `frontend/`.
>
> El deploy lleva `cd frontend` adentro. Si lo corrés como `cd frontend && npx vercel --prod`,
> tu shell **queda dentro de `frontend/`** y la próxima corrida falla con:
> `can't open file '...\frontend\scripts\live_update.py': No such file or directory`.
>
> **Por eso el deploy va entre paréntesis** — `(cd frontend && npx vercel --prod)` — un
> subshell que despliega y **te deja en la raíz**. Si igual quedaste adentro, volvé con `cd ..`.

```bash
pwd        # debe terminar en .../mundial-predictor-master
ls scripts # debe listar live_update.py, predict_live.py, ...
```

---

## Ciclo manual (excepción — ver arriba cuándo usarlo)

```bash
# 0. Sincronizá con el remoto primero (regla de oro #1)
git fetch origin && git pull origin master

# 1. Confirmá que estás en la raíz
pwd        # → .../mundial-predictor-master

# 2. Descarga resultados, recalcula ELO, reentrena modelo (~90s)
python scripts/live_update.py

# 3. Recalcula predicciones con agentes
python scripts/predict_live.py --export

# 4. Genera narraciones para los partidos de HOY solamente
python scripts/precompute_narrations.py        # Default: --days 0

# 5. Opcional: Agent Debate para un partido puntual fuera de la ventana de 36h
#    del CI, o para regenerar uno con --force. Acumulativo: no pisa debates
#    previos, omite si ya existe salvo --force.
python scripts/run_agent_debate.py "Mexico" "South Korea"
python scripts/export_frontend_data.py

# 6. Commit + push de los datos generados — NO te olvides este paso, si no
#    lo hacés tus cambios solo viven en local y el próximo cron del CI los
#    va a pisar igual sin que tu trabajo quede registrado.
git add data/raw/results.csv data/external/wc2026_live_results.csv frontend/public/data/*.json
git commit -m "data: actualización manual ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
git push origin master

# 7. Despliega a producción — el subshell (...) deja tu shell en la raíz al terminar
(cd frontend && npx vercel --prod)
```

Si el `git push` del paso 6 es rechazado porque el CI corrió mientras vos trabajabas,
volvé a "Regla de oro #1" antes de seguir.

---

## Conflictos de Agent Debate (cuando generaste un partido que el CI también generó)

Cada corrida de `run_agent_debate.py` usa `deepseek-reasoner` con texto libre — el mismo
partido debatido dos veces (una en local, otra por el CI) da contenido **distinto**, no
un duplicado idéntico. Git no puede mezclar eso línea por línea de forma segura.

Reconciliación manual:

```bash
python - <<'EOF'
import json

with open('frontend/public/data/agent_debate_results.json', encoding='utf-8') as f:
    remote = json.load(f)
with open('data/processed/agent_debate_results.json', encoding='utf-8') as f:
    local = json.load(f)

mis_partidos = {"Home vs Away", "..."}  # los que generaste a mano

kept_remote = [x for x in remote if x['match'] not in mis_partidos]
mine = [x for x in local if x['match'] in mis_partidos]
merged = kept_remote + mine

with open('frontend/public/data/agent_debate_results.json', 'w', encoding='utf-8') as f:
    json.dump(merged, f, ensure_ascii=False, indent=2)
EOF
git add frontend/public/data/agent_debate_results.json
git commit -m "data: fusiona Agent Debate manual con el del CI"
git push origin master
```

Para evitar esto en primer lugar: revisá el `debate_window_hours` del workflow (default 36)
antes de debatir un partido a mano — si está dentro de esa ventana, el CI probablemente ya
lo va a cubrir solo en su próxima corrida.

---

## MD2 — días con doble horario (ya cubierto por el CI)

En los días de MD2, cada día tiene **4 partidos de 2 grupos distintos**, en dos bloques
horarios. Los crons del workflow están timeados para disparar después de cada bloque
(normalmente 2-4 corridas por día de MD2), así que la actualización de presión
clasificatoria para los partidos nocturnos ya ocurre sola. Solo te conviene correr a
mano si necesitás verla **antes** de que dispare el próximo cron.

| Fecha | Grupos | Partidos |
|---|---|---|
| Jun 18 | A + B | Czech R. vs S.Africa · Mexico vs S.Korea · Switzerland vs Bosnia · Canada vs Qatar |
| Jun 19 | C + D | Scotland vs Morocco · Brazil vs Haiti · USA vs Australia · Turkey vs Paraguay |
| Jun 20 | E + F | Germany vs Ivory Coast · Ecuador vs Curazao · Netherlands vs Sweden · Tunisia vs Japan |
| Jun 21 | G + H | Belgium vs Iran · New Zealand vs Egypt · Spain vs Saudi Arabia · Uruguay vs Cape Verde |
| Jun 22 | I + J | France vs Iraq · Norway vs Senegal · Argentina vs Austria · Jordan vs Algeria |
| Jun 23 | K + L | Portugal vs Uzbekistan · Colombia vs DR Congo · England vs Ghana · Panama vs Croatia |

---

## MD3 — partidos simultáneos + actualización de terceros (3x diarias)

En la tercera jornada de cada grupo, los dos partidos se juegan a la misma hora (regla
FIFA anti-amaño). Se corren **3 actualizaciones por día** para refrescar probabilidades
de terceros, **pero SIN regenerar narraciones** (ahorran tokens, no cambian).

**Flujo:** `update_third_place_probs.py` (Monte Carlo ~5s) en lugar de full cycle.

### Horarios de J3 (Terceros actualizables 3x/día)

| Fecha | Grupo(s) | Primer bloque | Segundo bloque | Tercer bloque |
|-------|----------|---|---|---|
| Jun 24 | A, B, C | 18:00 UTC | 00:30 UTC | 03:00 UTC |
| Jun 25 | D, E, F | 20:00 UTC | 02:00 UTC | 04:00 UTC |
| Jun 26 | G, H, I | 19:00 UTC | 04:00 UTC | 05:00 UTC |
| Jun 27 | J, K, L | 02:00 UTC | 04:30 UTC | 06:00 UTC |

**Ejecución manual (si hace falta antes del CI):**
```bash
git pull origin master
python scripts/update_third_place_probs.py  # 5 segundos, no toca narrations
git add frontend/public/data/group_standings.json
git commit -m "data: terceros actualizado ($(date -u +%Y-%m-%dT%H:%M:%SZ))"
git push origin master
(cd frontend && npx vercel --prod)
```

| Fecha | Grupos |
|---|---|
| Jun 24 | A, B, C |
| Jun 25 | D, E, F |
| Jun 26 | G, H, I |
| Jun 27 | J, K, L |

---

## Notas operativas

**`live_update.py`**
- Si no hay partidos nuevos desde la última corrida, imprime "Sin cambios" y no reentrena. Normal.
- En CI siempre usa `--force` porque `models/` está gitignored y no persiste entre runs —
  sin `--force`, una corrida de CI "sin cambios" deja a `predict_live.py` sin modelo para cargar.
- Si falla con error de conexión, esperar 5 min y reintentar.

**`predict_live.py --export`**
- Genera `frontend/public/data/live_predictions.json` con probabilidades ajustadas por agentes.
- **Este paso es el que actualiza la pestaña Proyecciones.** Sin él, las probabilidades de
  los partidos no jugados son las del último deploy.
- **Cache por contexto:** solo vuelve a llamar a los agentes LLM de un partido si su
  contexto de grupo cambió desde la última corrida. `--force-agents` ignora el cache.
- Los agentes Travel y FIFARegs son determinísticos (siempre funcionan sin API key).
- IntMatch usa DeepSeek — si falla por saldo, los otros dos agentes igual corren.

**`precompute_narrations.py`**
- Genera narraciones y previas **solo para los partidos de HOY** (no toca días futuros).
- **Cache por contexto:** regenera una narración/previa solo si el contexto de ese grupo
  cambió desde la última corrida del día. Si nada cambió, conserva lo ya generado.
- La vigencia se guarda en `data/processed/narrations_sig.json` y
  `group_narratives_sig.json` (internos, gitignored). Bórralos para forzar regeneración total.
- Argumento `--days N` para ampliar la ventana más allá de hoy (default 0 días adicionales).

**`run_agent_debate.py`**
- **El CI ya lo corre automáticamente** para partidos de grupo dentro de las próximas
  36h (`ci_debate_targets.py`, configurable con `debate_window_hours` en `workflow_dispatch`).
- Corrida manual: forward-only, acumulativo, idempotente (omite partidos ya debateados
  salvo `--force`). Usalo para partidos fuera de esa ventana o para regenerar uno puntual.
- Costo: ~$0.08–0.10 por partido (3 agentes × 3 rondas, `deepseek-reasoner`) — no lo
  corras masivamente para una jornada completa sin necesidad.

**`vercel --prod`**
- Tarda ~30 segundos.
- URL de producción: https://frontend-three-black-wib8friwwy.vercel.app
- El CI lo corre automáticamente al final de cada corrida exitosa — un deploy manual
  extra está bien pero quedará reemplazado por el próximo cron del CI igual.

---

## Si algo falla

| Problema | Solución |
|---|---|
| `git push` rechazado (`fetch first`) | El CI corrió mientras trabajabas en local. Ver "Regla de oro #1". No forzar el push. |
| Mismo partido con contenido distinto en Agent Debate (local vs remoto) | Ver "Conflictos de Agent Debate" arriba — fusionar por clave de partido, no por diff de línea. |
| `can't open file '...\frontend\scripts\live_update.py'` | Tu shell quedó dentro de `frontend/`. Volvé con `cd ..`, verificá con `pwd`. Desplegá siempre con `(cd frontend && npx vercel --prod)` entre paréntesis. |
| `live_update.py` → error football-data.org | Reintentar en 5 min. La API tiene límite de llamadas. |
| `predict_live.py` → IntMatch error 402 | Saldo DeepSeek agotado. Recargar en platform.deepseek.com |
| `precompute_narrations.py` → 0 partidos | Normal si no hay partidos hoy. No hace nada. |
| El workflow de GitHub Actions falló | Revisar el run en GitHub Actions → logs del step que falló. Si fue `live_update.py` por la API caída, el próximo cron lo reintenta solo. |
| Vercel falla el build | Correr `npm run build` en `frontend/` para ver el error. |
| Narración tarde no refleja resultado de tarde | Verificar que `live_update.py` corrió (manual o CI) antes de `precompute_narrations.py`. |

---

## Costo estimado por jornada

| Operación | Costo |
|---|---|
| `predict_live.py` (IntMatch, ~8 partidos) | < $0.01 |
| `precompute_narrations.py` fase grupos (~8 partidos × 1 dialecto × 1500 tokens) | ~$0.003 |
| `precompute_narrations.py` fase eliminatoria (~4 partidos × 5 dialectos) | ~$0.015 |
| Chat (cache absorbe ~70-80%) | < $0.01/día |
| Agent Debate, ventana automática de 36h del CI (~4-8 partidos/día en fase de grupos) | ~$0.30–0.80/día |
| Agent Debate manual puntual (1 partido, 3 agentes × 3 rondas, `deepseek-reasoner`) | ~$0.08–0.10 |
| **Total día fase grupos (incluyendo CI con Agent Debate automático)** | **~$0.35–0.85** |
| **Total día eliminatoria** | **~$0.03–0.05** (Agent Debate típicamente manual y selectivo en esta fase) |

Con $5 en DeepSeek se cubre holgadamente todo el torneo, pero el Agent Debate automático
del CI es el rubro más caro del día en fase de grupos — si el presupuesto ajusta, reducí
`debate_window_hours` en el `workflow_dispatch` o pausá ese step puntualmente.

> **Nota:** Durante fase de grupos solo se genera dialecto **bogotano**. Al arrancar la
> fase eliminatoria (Round of 32, ~Jul 1), el script genera automáticamente los 5
> dialectos sin cambiar nada.
