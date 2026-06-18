"""Pre-computa narraciones para todos los partidos de grupo pendientes × 5 dialectos.

Corre una vez por día después de live_update.py:
    python scripts/precompute_narrations.py

Output: frontend/public/data/narrations.json
Formato de clave: "home_team|away_team|dialecto"

Costo estimado: ~52 partidos × 5 dialectos × ~1500 tokens = ~390k tokens ≈ $0.05 con deepseek-chat.
En la práctica solo regenera partidos pendientes (no jugados), ~8-12 por jornada.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("precompute_narrations")

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"

# Fase de grupos: solo bogotano para ahorrar tokens.
# Fase eliminatoria: todos los dialectos.
DIALECTS_GROUP    = ["bogotano"]
DIALECTS_KNOCKOUT = ["bogotano", "paisa", "boyaco", "costeño", "en"]

# ── Replica exacta del FULL_SYSTEM del narrator endpoint ─────────────────────
FULL_SYSTEM = """Actúa como **Narrator AI futbolero colombiano** para una app de predicción del Mundial 2026.

Tu trabajo NO es recalcular el modelo.
Tu trabajo es convertir el JSON compacto recibido en una narración futbolera, clara, jocosa y regional.

Usa únicamente los datos recibidos.
No inventes lesiones, jugadores, cuotas, clima, sanciones, historial ni resultados.

Si el JSON incluye `competitive_context`, usalo como fuente principal para explicar:
- presion de J2/J3 por puntos y partidos jugados
- si el partido es ganable, duro o minimo para empatar
- tabla del grupo y corte de mejores terceros
- partidos simultaneos del grupo en J3

## Dialectos disponibles

Usa el dialecto indicado en `dialecto`:

### bogotano
Tono urbano, irónico y futbolero.
Expresiones permitidas: "uy no", "parce", "qué visaje", "esto está pesado", "no den papaya", "se armó la vuelta", "pailas", "de alquilar balcón".

### paisa
Tono enérgico, competitivo y jocoso.
Expresiones permitidas: "parce", "pues", "home", "qué cosa tan brava", "esto está berraco", "ojo pues", "con verraquera", "no se pueden dormir".

### costeño
Tono alegre, sabroso y expresivo.
Expresiones permitidas: "eche", "mi llave", "compae", "ajá", "esa vaina", "se prendió esto", "le meten candela", "queda bailando con la más fea".

### boyacense
Tono noble, pícaro y campesino-jovial.
Expresiones permitidas: "sumercé", "ala", "mijitico", "la vaina está brava", "no se achante", "quedó viendo un chispero", "se le pone la ruana al revés".

### en
Tono sharp sports commentator. Analytical, bold, no fluff.

Regla: el dialecto debe sonar divertido, pero nunca ofensivo ni caricaturesco.

## Formato de salida obligatorio

Entrega solo Markdown. Usa esta estructura:

```
👑 **[Título jocoso del partido]**

⚙️ **Narrator AI — modo [dialecto]**

[Apertura narrativa de 2 a 4 párrafos cortos]

🏟️ **Sede**
[Estadio, ciudad y ambiente]

🔥 **Contexto competitivo**
[Explica grupo o eliminatoria con presión, clasificación o eliminación]

📊 **Probabilidades del modelo**
[Emoji home]: [prob_home]%
🤝 Empate: [prob_draw]%
[Emoji away]: [prob_away]%

[Interpretación jocosa de las probabilidades]

⚽ **Marcador más probable**
[Marcador score_prediction]

[Interpretación del marcador]

🧠 **Capa Multi-Agente**
[Resumen del consenso de agentes en lenguaje humano]

🎯 **Lectura de agentes**
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]

🧾 **Conclusión final**
[Predicción final, favorito, riesgo principal y frase regional de cierre]
```

## Reglas de ahorro de tokens

1. No repitas datos innecesarios.
2. No expliques fórmulas.
3. No menciones que eres un modelo de lenguaje.
4. No hagas análisis largo por agente.
5. Máximo 1 frase jocosa por sección.
6. Máximo 900 palabras.
7. Si agent_summary trae pocos agentes, trabaja solo con esos.
8. Si el consenso está dividido, dilo claramente.
9. Si el dialecto cambia, conserva el análisis y solo cambia el estilo narrativo.
10. No generes recomendaciones de apuestas ni manejo de dinero.

Genera la narración final lista para mostrarse en la app."""


def _load_env() -> None:
    for path in [ROOT / ".env", ROOT / "frontend" / ".env.local"]:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" not in line or line.startswith("#"):
                continue
            k, v = line.split("=", 1)
            k = k.strip(); v = v.strip().strip('"').strip("'")
            if k == "DEEPSEEK_API_KEY" and not os.environ.get(k):
                os.environ[k] = v


def _load_teams() -> dict:
    p = FRONTEND_DATA / "teams.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _load_live_predictions() -> list[dict]:
    p = FRONTEND_DATA / "live_predictions.json"
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def _load_group_matches() -> dict[str, list[dict]]:
    """Carga group_matches.json: {grupo: [{team1, team2, date, ...}]}"""
    p = FRONTEND_DATA / "group_matches.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _build_team_to_group(group_matches: dict[str, list[dict]]) -> dict[str, str]:
    """Devuelve {nombre_equipo: letra_grupo}."""
    mapping: dict[str, str] = {}
    for group, matches in group_matches.items():
        for m in matches:
            mapping[m["team1"]] = group
            mapping[m["team2"]] = group
    return mapping


def _compute_group_standings(
    live_results_path: Path,
    team_to_group: dict[str, str],
    group_letter: str,
) -> list[dict]:
    """
    Lee wc2026_live_results.csv y calcula la tabla del grupo indicado
    con los partidos ya jugados. Retorna lista ordenada por pts, DG, GF
    o lista vacía si el grupo no tiene partidos jugados aún.
    """
    import csv

    if not live_results_path.exists():
        return []

    # Acumular stats por equipo
    stats: dict[str, dict] = {}

    def ensure(team: str) -> None:
        if team not in stats:
            stats[team] = {"team": team, "P": 0, "W": 0, "D": 0, "L": 0, "GF": 0, "GA": 0}

    with live_results_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            home, away = row["home_team"], row["away_team"]
            # Solo partidos del grupo solicitado
            if team_to_group.get(home) != group_letter:
                continue
            try:
                hs, as_ = int(row["home_score"]), int(row["away_score"])
            except (ValueError, KeyError):
                continue  # partido sin marcador todavía

            ensure(home); ensure(away)
            stats[home]["P"] += 1; stats[away]["P"] += 1
            stats[home]["GF"] += hs; stats[home]["GA"] += as_
            stats[away]["GF"] += as_; stats[away]["GA"] += hs

            if hs > as_:
                stats[home]["W"] += 1; stats[away]["L"] += 1
            elif hs == as_:
                stats[home]["D"] += 1; stats[away]["D"] += 1
            else:
                stats[away]["W"] += 1; stats[home]["L"] += 1

    if not stats:
        return []

    # Calcular puntos y diferencia de goles
    rows = []
    for s in stats.values():
        s["pts"] = s["W"] * 3 + s["D"]
        s["GD"] = s["GF"] - s["GA"]
        rows.append(s)

    # Ordenar: pts desc, GD desc, GF desc
    rows.sort(key=lambda r: (-r["pts"], -r["GD"], -r["GF"]))
    return rows


def _build_user_payload(
    match: dict,
    teams: dict,
    lang: str,
    group_standings: list[dict],
) -> dict:
    """Construye el payload que el narrator frontend enviaría en modo FULL."""
    home = match["home_team"]
    away = match["away_team"]
    ht = teams.get(home, {})
    at = teams.get(away, {})

    agent_notes = match.get("agent_notes", {})
    agent_summary = [
        {"agent": k, "note": v}
        for k, v in agent_notes.items()
        if "error" not in v.lower()
    ]

    payload: dict = {
        "home": home,
        "away": away,
        "lang": lang,
        "dialecto": lang,
        "group": match.get("group", ""),
        "round": match.get("round", ""),
        "venue": match.get("venue", ""),
        "kickoff": match.get("kickoff", ""),
        "prob_home": round(match.get("p_home", 0.34) * 100, 1),
        "prob_draw": round(match.get("p_draw", 0.32) * 100, 1),
        "prob_away": round(match.get("p_away", 0.34) * 100, 1),
        "elo_home": round(ht.get("elo", 1500)),
        "elo_away": round(at.get("elo", 1500)),
        "wc_matches_home": ht.get("wc_matches", 0),
        "wc_matches_away": at.get("wc_matches", 0),
        "goals_home": round(ht.get("goals_scored", 1.3), 2),
        "goals_away": round(at.get("goals_scored", 1.3), 2),
        "agent_summary": agent_summary,
    }

    group_context = match.get("group_context", {})
    if group_context:
        payload["competitive_context"] = {
            "group_name": group_context.get("group_name"),
            "matchday": group_context.get("matchday"),
            "home_points": group_context.get("home_points"),
            "away_points": group_context.get("away_points"),
            "home_games_played": group_context.get("home_games_played"),
            "away_games_played": group_context.get("away_games_played"),
            "group_standings": group_context.get("group_standings"),
            "simultaneous_group_matches": group_context.get("simultaneous_group_matches"),
            "third_place_context": group_context.get("third_place_context"),
        }

    # Tabla real del grupo (solo si hay partidos jugados)
    if group_standings:
        payload["group_standings"] = [
            {
                "pos": i + 1,
                "team": r["team"],
                "pts": r["pts"],
                "P": r["P"], "W": r["W"], "D": r["D"], "L": r["L"],
                "GF": r["GF"], "GA": r["GA"], "GD": r["GD"],
            }
            for i, r in enumerate(group_standings)
        ]

    return payload


def _call_deepseek(client: OpenAI, payload: dict) -> str:
    user_msg = json.dumps(payload, ensure_ascii=False)
    response = client.chat.completions.create(
        model="deepseek-chat",
        max_tokens=1400,
        messages=[
            {"role": "system", "content": FULL_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )
    return response.choices[0].message.content or ""


def main() -> None:
    _load_env()
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        logger.error("DEEPSEEK_API_KEY no configurada")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    teams = _load_teams()
    live_preds = _load_live_predictions()
    group_matches = _load_group_matches()
    team_to_group = _build_team_to_group(group_matches)
    live_results_path = ROOT / "data" / "external" / "wc2026_live_results.csv"

    if not live_preds:
        logger.warning("live_predictions.json vacío o no existe. Corre predict_live.py --export primero.")
        sys.exit(0)

    # Ventana de generación: solo hoy y mañana (contexto válido)
    # Argumento opcional --days N para ampliar la ventana (default 2)
    days_ahead = 2
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--days" and i + 1 < len(sys.argv) - 1:
            try:
                days_ahead = int(sys.argv[i + 2])
            except ValueError:
                pass

    from datetime import datetime, timezone, timedelta
    today = datetime.now(timezone.utc).date()
    cutoff = today + timedelta(days=days_ahead)

    all_group = [m for m in live_preds if m.get("stage") == "group"]
    logger.info("%d partidos de grupo en live_predictions.json", len(all_group))

    # Filtrar solo partidos dentro de la ventana (hoy y mañana)
    pending = []
    for m in all_group:
        kickoff_str = m.get("kickoff", "")
        try:
            kickoff_date = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).date()
        except Exception:
            continue
        if today <= kickoff_date <= cutoff:
            pending.append(m)

    logger.info("Ventana %s → %s: %d partidos a narrar", today, cutoff, len(pending))

    # Cargar narrations.json existente
    narrations_path = FRONTEND_DATA / "narrations.json"
    narrations: dict[str, str] = {}
    if narrations_path.exists():
        try:
            narrations = json.loads(narrations_path.read_text(encoding="utf-8"))
        except Exception:
            narrations = {}
    logger.info("%d narraciones pre-existentes en narrations.json", len(narrations))

    # Forzar regeneración de partidos de HOY (contexto siempre fresco)
    for m in pending:
        kickoff_str = m.get("kickoff", "")
        try:
            kickoff_date = datetime.fromisoformat(kickoff_str.replace("Z", "+00:00")).date()
        except Exception:
            continue
        if today <= kickoff_date <= cutoff:
            is_group = m.get("stage", "group") == "group"
            dialects = DIALECTS_GROUP if is_group else DIALECTS_KNOCKOUT
            for lang in dialects:
                key = f"{m['home_team']}|{m['away_team']}|{lang}"
                narrations.pop(key, None)  # borra para que se regenere con contexto fresco

    generated = 0
    skipped = 0
    for match in pending:
        home = match["home_team"]
        away = match["away_team"]
        is_group = match.get("stage", "group") == "group"
        dialects = DIALECTS_GROUP if is_group else DIALECTS_KNOCKOUT
        group_letter = match.get("group", team_to_group.get(home, ""))
        standings = _compute_group_standings(live_results_path, team_to_group, group_letter)
        if standings:
            logger.info("Grupo %s: tabla con %d equipos con partidos jugados", group_letter, len(standings))
        for lang in dialects:
            key = f"{home}|{away}|{lang}"
            if key in narrations:
                skipped += 1
                continue
            logger.info("Generando: %s vs %s [%s]", home, away, lang)
            payload = _build_user_payload(match, teams, lang, standings)
            try:
                text = _call_deepseek(client, payload)
                narrations[key] = text
                generated += 1
                # Guardar incremental para no perder trabajo ante interrupciones
                narrations_path.write_text(
                    json.dumps(narrations, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                time.sleep(0.5)  # evitar rate limit en ráfaga
            except Exception as e:
                logger.error("Error en %s [%s]: %s", key, lang, e)

    logger.info("Listo: %d nuevas narraciones, %d ya existían → total %d", generated, skipped, len(narrations))
    if generated == 0:
        logger.info("Nada nuevo que generar.")


if __name__ == "__main__":
    main()
