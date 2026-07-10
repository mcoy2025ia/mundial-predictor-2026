# Instructivo: activar el workflow automático de GitHub Actions

El workflow `.github/workflows/wc2026-live-update.yml` ya está en el repo (commit `f360c09`, ya pusheado a `master`). Le falta un único paso manual: cargar 6 secrets en GitHub. Sin esto, las corridas programadas van a fallar.

---

## 1. Conseguir cada valor

### `FOOTBALL_DATA_TOKEN`
Ya lo tenés. Está en `frontend/.env.local`. Abrí ese archivo y copiá el valor de esa variable.

### `DEEPSEEK_API_KEY`
Ya lo tenés. Está en `.env` (raíz del proyecto). Copiá el valor.

### `ANTHROPIC_API_KEY` (opcional, fallback de los agentes)
Ya lo tenés si lo usás. Está en `.env` y/o `frontend/.env.local`. Si no lo tenés configurado, podés omitir este secret — los agentes LLM simplemente devuelven `delta=0` sin él.

### `VERCEL_TOKEN`
1. Entrá a https://vercel.com/account/tokens
2. "Create Token" → ponele un nombre (ej. `github-actions-wc2026`)
3. Si te deja elegir scope/proyecto, restringilo al proyecto `frontend` (más seguro que un token de toda la cuenta)
4. Copiá el token apenas se genera — Vercel no te lo vuelve a mostrar después

### `VERCEL_ORG_ID` y `VERCEL_PROJECT_ID`
Ya los tengo identificados del repo:
- `VERCEL_ORG_ID` = `team_xuZsmaSFFJlEiYy46IchOZi3`
- `VERCEL_PROJECT_ID` = `prj_gxnAXHIznI3BxViy5eH8sVbw0lLe`

(Salen de `frontend/.vercel/project.json`, que está en tu máquina local pero no se sube al repo por `.gitignore`.)

---

## 2. Cargar los secrets en GitHub

1. Entrá a: `https://github.com/mcoy2025ia/mundial-predictor-2026/settings/secrets/actions`
2. Click en **"New repository secret"**
3. Repetí esto 6 veces (Name exacto + Value):

| Name | Value |
|---|---|
| `FOOTBALL_DATA_TOKEN` | (de `frontend/.env.local`) |
| `DEEPSEEK_API_KEY` | (de `.env`) |
| `ANTHROPIC_API_KEY` | (de `.env`, opcional) |
| `VERCEL_TOKEN` | (el que generaste en el paso 1) |
| `VERCEL_ORG_ID` | `team_xuZsmaSFFJlEiYy46IchOZi3` |
| `VERCEL_PROJECT_ID` | `prj_gxnAXHIznI3BxViy5eH8sVbw0lLe` |

El nombre tiene que ser idéntico (mayúsculas y guiones bajos exactos) porque el workflow los referencia como `${{ secrets.NOMBRE }}`.

---

## 3. Probar que funciona

1. Entrá a la pestaña **Actions** del repo: `https://github.com/mcoy2025ia/mundial-predictor-2026/actions`
2. Click en el workflow **"WC 2026 Live Update"** (panel izquierdo)
3. Click en **"Run workflow"** (botón a la derecha, dropdown) → rama `master` → **Run workflow**
4. Esperá ~1-2 min y entrá a la corrida para ver los logs paso a paso

Si todos los pasos quedan en verde, está funcionando. Si falla en "Live update" o "Live predictions export", revisá que el nombre del secret coincida exacto. Si falla en "Deploy frontend to Vercel", revisá `VERCEL_TOKEN`.

---

## 4. Qué hace solo a partir de ahora

- Corre automáticamente ~90 min después de cada partido de fase de grupos (60 disparadores programados, ya calculados con los horarios reales del fixture).
- Si el resultado todavía no está en el feed, el run no hace nada (no gasta tokens ni tiempo de cómputo de más).
- Si hay resultado nuevo: actualiza ELO/modelo, recalcula predicciones, genera narraciones, corre el Agent Debate para el próximo partido (si entra en la ventana de 36h), comitea los JSON al repo y despliega a Vercel — todo sin que tengas que tocar nada.

No necesitás volver a correr nada de esto a mano salvo que quieras forzar algo puntual (`Run workflow` manual) o seguir usando `run_agent_debate.py` para partidos que el automatismo no haya cubierto.
