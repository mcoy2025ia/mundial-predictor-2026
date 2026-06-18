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


GROUP_NARRATIVE_SYSTEM = """# Rol
Eres GroupNarrative-Preview, un analista narrativo de futbol internacional especializado en fases de grupos del Mundial 2026.

# Objetivo
Convierte standings, partidos de jornada, localia, probabilidades del predictor y contexto competitivo en una previa clara de grupo.

# Reglas
- Usa unicamente la informacion entregada en el JSON.
- No inventes lesiones, estados animicos, sanciones, clima, cuotas ni resultados.
- Si falta un dato, dilo como incertidumbre.
- No recalcules probabilidades ni des probabilidades exactas que no vengan en el input.
- Recuerda que clasifican los dos primeros de cada grupo y tambien los mejores terceros.
- Diferencia "depende de si mismo" de "depende de otros resultados".
- No digas que una seleccion esta matematicamente eliminada salvo que el input lo demuestre de forma explicita.
- Si el input entrega hora Bogota, nombrala como hora Colombia/Bogota; no la llames hora local de la sede.
- No inventes banderas, emojis de paises ni nacionalidades si no vienen en el input.
- No uses preambulos tipo "aca tienes", "te presento" o "aqui va"; empieza directo con "## Panorama general de la jornada".
- No uses voseo ni expresiones ajenas al espanol colombiano bogotano normal.
- En J2 pesa mas la urgencia de sumar y no quedar contra la pared.
- En J3 pesa mas la clasificacion directa, diferencia de gol y pelea por mejores terceros.
- El analisis debe hacerse por cada seleccion del grupo, no solo para el grupo completo.
- Para cada equipo evalua puntos actuales, resultado anterior, rival anterior, fuerza del rival anterior, calidad del resultado, estado de animo probable, presion siguiente, dependencia, dificultad actual y cambio de peligrosidad frente al proximo rival.
- No clasifiques a un equipo solo por nombre historico. Clasificalo por evidencia reciente entregada en team_profiles.
- Si no hay resultado anterior para un equipo, dilo como falta de evidencia reciente y evita convertirlo en "Favorito solido" solo por historia.
- Si un equipo chico empato contra una favorita, sube su nivel de peligro.
- Si una favorita empato contra un rival menor, marca mas presion.
- Si un equipo gano contra el rival mas debil del grupo, no lo infles demasiado.
- Si un equipo perdio por poco contra una potencia, no lo trates automaticamente como debil.
- Si un equipo perdio por goleada, marcalo como golpeado o vulnerable.
- Si juega de local, aumenta su impulso emocional y presion competitiva.
- Si llega con 0 puntos, puede ser vulnerable, pero tambien desesperado y peligroso.

# Categorias obligatorias de nivel de peligro
Asigna una categoria a cada seleccion:
- Favorito solido
- Favorito presionado
- Rival peligroso
- Rival incomodo
- Rival accesible
- Rival desesperado
- Rival trampa

# Salida
Entrega solo Markdown en espanol colombiano, tono analitico, futbolero y narrativo.

## Panorama general de la jornada
1 o 2 parrafos.

## Grupo [LETRA]

### Tabla actual
Resume posiciones, puntos y diferencia de gol. Si no hay tabla real, dilo.

### Partidos de la jornada
Lista partidos, horario, sede/localia si esta disponible.

### Narrativa del grupo
Que esta en juego emocional y competitivamente.

### Quien depende de quien
Seleccion por seleccion: que pasa si gana, empata o pierde, y si depende de si misma o de otros.

### Analisis por seleccion
Para cada seleccion usa exactamente este formato:

#### [Nombre del equipo]
- Puntos:
- Resultado anterior:
- Calidad del resultado:
- Estado de animo:
- Presion:
- Dependencia:
- Nivel de peligro:
- Lectura narrativa:

### Rival mas dificil
Equipo mas dificil de ganarle segun datos entregados.

### Rival mas accesible
Equipo mas accesible segun datos entregados, sin decir que es facil si no hay evidencia.

### Partido clave
Partido que puede romper el grupo.

## Frase final para narrador
Frase corta, potente y lista para video, transmision o post."""


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


def _group_letter(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip()
    if value.lower().startswith("group "):
        return value.split()[-1].strip()
    return value


def _kickoff_date(match: dict) -> str:
    kickoff = match.get("kickoff") or match.get("date") or ""
    if not kickoff:
        return ""
    if "T" in kickoff:
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo

            dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo("UTC"))
            return dt.astimezone(ZoneInfo("America/Bogota")).date().isoformat()
        except Exception:
            pass
    return kickoff.split("T", 1)[0]


def _kickoff_bogota(match: dict) -> str:
    kickoff = match.get("kickoff") or ""
    if not kickoff:
        return ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo

        dt = datetime.fromisoformat(kickoff.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(ZoneInfo("America/Bogota")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return kickoff


def _matchday_from_round(round_name: str | None) -> int | None:
    if not round_name:
        return None
    digits = "".join(ch for ch in round_name if ch.isdigit())
    if not digits:
        return None
    number = int(digits)
    if number <= 7:
        return 1
    if number <= 13:
        return 2
    return 3


def _teams_for_group(group_letter: str, group_matches: dict[str, list[dict]] | None) -> list[str]:
    teams: list[str] = []
    for match in (group_matches or {}).get(_group_letter(group_letter), []):
        for team in [match.get("team1"), match.get("team2")]:
            if team and team not in teams:
                teams.append(team)
    return teams


def _fixture_for_pair(group_letter: str, home: str, away: str, group_matches: dict[str, list[dict]] | None) -> dict:
    pair = {home, away}
    for match in (group_matches or {}).get(_group_letter(group_letter), []):
        if {match.get("team1"), match.get("team2")} == pair:
            return match
    return {}


def _team_win_probability(team: str, fixture: dict) -> float | None:
    if not fixture:
        return None
    if fixture.get("team1") == team:
        return fixture.get("t1_win")
    if fixture.get("team2") == team:
        return fixture.get("t2_win")
    return None


def _rival_strength(probability: float | None) -> str:
    if probability is None:
        return "desconocido"
    if probability >= 0.40:
        return "favorito/fuerte"
    if probability >= 0.34:
        return "medio"
    return "debil o accesible"


def _result_quality(outcome: str, goals_for: int, goals_against: int, rival_strength: str) -> str:
    margin = goals_for - goals_against
    if margin <= -3:
        return "preocupante: derrota amplia"
    if outcome == "win" and "favorito" in rival_strength:
        return "muy alta: victoria contra rival fuerte"
    if outcome == "draw" and "favorito" in rival_strength:
        return "muy alta: empate contra rival fuerte"
    if outcome == "loss" and "favorito" in rival_strength and margin == -1:
        return "competitiva: derrota corta contra rival fuerte"
    if outcome == "win" and "debil" in rival_strength:
        return "normal: gano contra rival accesible, sin inflarlo de mas"
    if outcome == "draw" and "debil" in rival_strength:
        return "preocupante: dejo puntos contra rival accesible"
    if outcome == "loss":
        return "preocupante"
    if outcome == "draw":
        return "normal o positiva segun contexto"
    return "positiva"


def _outcome_label(outcome: str) -> str:
    return {"win": "gano", "draw": "empato", "loss": "perdio"}.get(outcome, "sin resultado")


def _load_group_results(
    live_results_path: Path,
    team_to_group: dict[str, str],
    group_letter: str,
) -> list[dict]:
    import csv

    if not live_results_path.exists():
        return []

    rows = []
    with live_results_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            home, away = row.get("home_team", ""), row.get("away_team", "")
            if team_to_group.get(home) != _group_letter(group_letter):
                continue
            try:
                row["home_score"] = int(row["home_score"])
                row["away_score"] = int(row["away_score"])
            except (ValueError, KeyError, TypeError):
                continue
            rows.append(row)
    return rows


def _build_team_profiles(
    group_letter: str,
    group_matches: dict[str, list[dict]] | None,
    actual_standings: list[dict],
    played_results: list[dict],
    upcoming_matches: list[dict] | None = None,
) -> list[dict]:
    standing_map = {row["team"]: row for row in actual_standings}
    teams = _teams_for_group(group_letter, group_matches)
    for row in actual_standings:
        if row["team"] not in teams:
            teams.append(row["team"])

    profiles = []
    for team in teams:
        standing = standing_map.get(team, {})
        team_results = [
            row for row in played_results
            if row.get("home_team") == team or row.get("away_team") == team
        ]
        team_results.sort(key=lambda row: row.get("date", ""))
        previous = team_results[-1] if team_results else None

        previous_payload = None
        if previous:
            is_home = previous["home_team"] == team
            opponent = previous["away_team"] if is_home else previous["home_team"]
            gf = previous["home_score"] if is_home else previous["away_score"]
            ga = previous["away_score"] if is_home else previous["home_score"]
            outcome = "win" if gf > ga else "draw" if gf == ga else "loss"
            fixture = _fixture_for_pair(group_letter, previous["home_team"], previous["away_team"], group_matches)
            opponent_prob = _team_win_probability(opponent, fixture)
            strength = _rival_strength(opponent_prob)
            previous_payload = {
                "date": previous.get("date"),
                "opponent": opponent,
                "score": f"{gf}-{ga}",
                "outcome": outcome,
                "result_label": f"{_outcome_label(outcome)} {gf}-{ga} contra {opponent}",
                "opponent_pre_match_win_probability": round(opponent_prob * 100, 1) if opponent_prob is not None else None,
                "opponent_strength": strength,
                "result_quality_hint": _result_quality(outcome, gf, ga, strength),
            }

        next_match = next(
            (
                match for match in (upcoming_matches or [])
                if match.get("home_team") == team or match.get("away_team") == team
            ),
            {},
        )
        next_opponent = ""
        if next_match:
            next_opponent = next_match.get("away_team") if next_match.get("home_team") == team else next_match.get("home_team")

        profiles.append(
            {
                "team": team,
                "points": standing.get("pts", 0),
                "played": standing.get("P", 0),
                "goal_difference": standing.get("GD", 0),
                "previous_result": previous_payload,
                "next_opponent": next_opponent,
                "analysis_required": {
                    "points": True,
                    "previous_result": True,
                    "previous_opponent_strength": True,
                    "result_quality": True,
                    "mood": True,
                    "pressure": True,
                    "dependency": True,
                    "danger_level_category": [
                        "Favorito solido",
                        "Favorito presionado",
                        "Rival peligroso",
                        "Rival incomodo",
                        "Rival accesible",
                        "Rival desesperado",
                        "Rival trampa",
                    ],
                },
            }
        )
    return profiles


def _model_for_group_narrative(payload: dict) -> str:
    matchday = payload.get("matchday")
    competitive = payload.get("competitive_context") or {}
    if matchday == 3:
        return "deepseek-reasoner"
    if competitive.get("third_place_context") or competitive.get("simultaneous_group_matches"):
        return "deepseek-reasoner"
    return "deepseek-chat"


def _build_group_narrative_payload(
    group_letter: str,
    jornada_date: str,
    matches: list[dict],
    actual_standings: list[dict],
    group_matches: dict[str, list[dict]] | None = None,
    played_results: list[dict] | None = None,
) -> dict:
    """Build the JSON input for GroupNarrative-Preview."""
    normalized_group = _group_letter(group_letter)
    ordered_matches = sorted(matches, key=lambda m: m.get("kickoff", ""))
    first_context = next((m.get("group_context") for m in ordered_matches if m.get("group_context")), {})
    matchday = first_context.get("matchday")
    if matchday is None and ordered_matches:
        matchday = _matchday_from_round(ordered_matches[0].get("round"))

    fixtures = []
    for match in ordered_matches:
        fixtures.append(
            {
                "home": match.get("home_team"),
                "away": match.get("away_team"),
                "kickoff_utc": match.get("kickoff"),
                "kickoff_bogota": _kickoff_bogota(match),
                "venue": match.get("venue"),
                "round": match.get("round"),
                "prob_home": round(match.get("p_home", 0) * 100, 1) if "p_home" in match else None,
                "prob_draw": round(match.get("p_draw", 0) * 100, 1) if "p_draw" in match else None,
                "prob_away": round(match.get("p_away", 0) * 100, 1) if "p_away" in match else None,
                "model": match.get("model"),
                "localia": "home" if match.get("is_neutral") is False else "neutral_or_unknown",
                "agent_notes": match.get("agent_notes", {}),
            }
        )

    standings = [
        {
            "pos": i + 1,
            "team": row["team"],
            "pts": row["pts"],
            "P": row["P"],
            "W": row["W"],
            "D": row["D"],
            "L": row["L"],
            "GF": row["GF"],
            "GA": row["GA"],
            "GD": row["GD"],
        }
        for i, row in enumerate(actual_standings)
    ]

    return {
        "agent": "GroupNarrative-Preview",
        "dialecto": "bogotano",
        "group": normalized_group,
        "jornada_date": jornada_date,
        "matchday": matchday,
        "qualification_rules": "Top 2 qualify directly; best third-place teams can also qualify.",
        "actual_standings": standings,
        "matches": fixtures,
        "team_profiles": _build_team_profiles(
            normalized_group,
            group_matches,
            actual_standings,
            played_results or [],
            ordered_matches,
        ),
        "competitive_context": {
            "group_name": first_context.get("group_name") or f"Group {normalized_group}",
            "matchday": matchday,
            "group_standings": first_context.get("group_standings"),
            "simultaneous_group_matches": first_context.get("simultaneous_group_matches"),
            "third_place_context": first_context.get("third_place_context"),
        },
        "timezone_note": "kickoff_bogota is America/Bogota. Venue local timezone is not provided; do not call it local time.",
        "missing_data_policy": "If emotional momentum, injuries or exact standings are missing, state that uncertainty instead of assuming it.",
    }


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


def _call_group_narrative(client: OpenAI, payload: dict) -> str:
    user_msg = json.dumps(payload, ensure_ascii=False)
    response = client.chat.completions.create(
        model=_model_for_group_narrative(payload),
        max_tokens=1600,
        messages=[
            {"role": "system", "content": GROUP_NARRATIVE_SYSTEM},
            {"role": "user", "content": user_msg},
        ],
    )
    return _sanitize_group_narrative(response.choices[0].message.content or "")


def _sanitize_group_narrative(text: str) -> str:
    return (
        text
        .replace("淘汰", "la eliminacion")
        .replace("Acá tenés", "")
        .replace("aca tienes", "")
        .strip()
    )


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
    groups_only = "--groups-only" in sys.argv[1:]
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

    # Cargar resultados ya jugados para filtrar partidos pendientes
    played_set = set()
    if live_results_path.exists():
        import csv
        with live_results_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                home, away = row.get("home_team", ""), row.get("away_team", "")
                if home and away:
                    try:
                        home_score = int(row.get("home_score", -1))
                        away_score = int(row.get("away_score", -1))
                        if home_score >= 0 and away_score >= 0:
                            played_set.add((home, away))
                    except (ValueError, TypeError):
                        pass

    # Filtrar solo partidos dentro de la ventana (hoy y mañana) que TODAVIA NO SE HAN JUGADO
    pending = []
    for m in all_group:
        home, away = m.get("home_team"), m.get("away_team")
        if (home, away) in played_set:
            continue  # Este partido ya se jugó, no incluir en pendientes
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

    group_narratives_path = FRONTEND_DATA / "group_narratives.json"
    group_narratives: dict[str, str] = {}
    if group_narratives_path.exists():
        try:
            group_narratives = json.loads(group_narratives_path.read_text(encoding="utf-8"))
        except Exception:
            group_narratives = {}
    logger.info("%d previas de grupo pre-existentes en group_narratives.json", len(group_narratives))

    # Forzar regeneración de partidos de HOY (contexto siempre fresco)
    for m in ([] if groups_only else pending):
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

    group_batches: dict[tuple[str, str], list[dict]] = {}
    for m in pending:
        group_letter = _group_letter(m.get("group") or team_to_group.get(m.get("home_team", ""), ""))
        jornada_date = _kickoff_date(m)
        if group_letter and jornada_date:
            group_batches.setdefault((group_letter, jornada_date), []).append(m)

    refresh_start = today.isoformat()
    refresh_end = cutoff.isoformat()
    for group_letter, jornada_date in group_batches:
        group_narratives.pop(f"{group_letter}|{jornada_date}|bogotano", None)
        for existing_key in list(group_narratives):
            parts = existing_key.split("|")
            if len(parts) == 3 and parts[0] == group_letter and refresh_start <= parts[1] <= refresh_end:
                group_narratives.pop(existing_key, None)

    generated = 0
    skipped = 0
    for match in ([] if groups_only else pending):
        home = match["home_team"]
        away = match["away_team"]
        is_group = match.get("stage", "group") == "group"
        dialects = DIALECTS_GROUP if is_group else DIALECTS_KNOCKOUT
        group_letter = _group_letter(match.get("group") or team_to_group.get(home, ""))
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
    group_generated = 0
    group_skipped = 0
    for (group_letter, jornada_date), group_pending in sorted(group_batches.items()):
        key = f"{group_letter}|{jornada_date}|bogotano"
        if key in group_narratives:
            group_skipped += 1
            continue

        standings = _compute_group_standings(live_results_path, team_to_group, group_letter)
        played_results = _load_group_results(live_results_path, team_to_group, group_letter)
        payload = _build_group_narrative_payload(
            group_letter,
            jornada_date,
            group_pending,
            standings,
            group_matches,
            played_results,
        )
        model = _model_for_group_narrative(payload)
        logger.info("Generando previa de grupo: %s %s [%s]", group_letter, jornada_date, model)
        try:
            text = _call_group_narrative(client, payload)
            group_narratives[key] = text
            group_generated += 1
            group_narratives_path.write_text(
                json.dumps(group_narratives, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            time.sleep(0.5)
        except Exception as e:
            logger.error("Error en previa %s: %s", key, e)

    logger.info(
        "Previas de grupo: %d nuevas, %d ya existian -> total %d",
        group_generated,
        group_skipped,
        len(group_narratives),
    )
    if generated == 0:
        logger.info("Nada nuevo que generar.")


if __name__ == "__main__":
    main()
