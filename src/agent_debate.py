"""Sistema de debate multi-agente para predicciones de marcadores.

3 agentes expertos debaten para llegar a predicción consensuada de marcador.
Usa deepseek-reasoner para análisis profundo sin modelos ML.
"""

import json
import logging
from pathlib import Path
from typing import Optional
import os

import httpx

ROOT = Path(__file__).parent.parent
logger = logging.getLogger(__name__)

# DeepSeek API
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Tabla de homologación: nombre en fixture → nombre en CSV
TEAM_NAME_MAPPING = {
    "USA": "United States",
    "United States": "United States",
}

def normalize_team_name(name: str) -> str:
    """Normaliza el nombre del equipo usando tabla de homologación."""
    return TEAM_NAME_MAPPING.get(name, name)


class AgentDebateSystem:
    """Sistema de debate de 3 agentes para predicción de marcadores."""

    def __init__(self):
        self.client = httpx.Client(timeout=60)
        self.conversation_history = []

    def _call_deepseek(self, prompt: str, use_reasoner: bool = True, max_tokens: Optional[int] = None) -> str:
        """Llama a DeepSeek con el prompt dado."""
        model = "deepseek-reasoner" if use_reasoner else "deepseek-chat"

        if max_tokens is None:
            max_tokens = 2000 if use_reasoner else 1000

        response = self.client.post(
            DEEPSEEK_URL,
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 1 if use_reasoner else 0.7,
                "max_tokens": max_tokens,
            },
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
        )

        if response.status_code != 200:
            raise RuntimeError(f"DeepSeek API error: {response.text}")

        return response.json()["choices"][0]["message"]["content"]

    def get_group_context(self, home_team: str, away_team: str) -> dict:
        """Obtiene contexto REAL del grupo calculando standings desde resultados reales."""
        import pandas as pd

        # Cargar resultados reales desde CSV
        try:
            results_df = pd.read_csv(ROOT / "data/external/wc2026_live_results.csv")
        except:
            results_df = pd.DataFrame()

        # Calcular standings reales desde los resultados
        standings = self._calculate_real_standings(results_df)

        # Extraer información para cada equipo
        home_info = self._extract_team_from_standings(home_team, standings, results_df)
        away_info = self._extract_team_from_standings(away_team, standings, results_df)

        # Construir contexto enriquecido
        context = {
            "home_team": {
                "name": home_team,
                "points": home_info.get("points", 0),
                "goal_diff": home_info.get("goal_diff", 0),
                "played": home_info.get("played", 0),
                "position": home_info.get("position", "?"),
                "group": home_info.get("group", "?"),
                "md1_result": home_info.get("md1_result", "No data"),
                "md1_opponent": home_info.get("md1_opponent", "?"),
                "status": home_info.get("status", "Unknown"),
            },
            "away_team": {
                "name": away_team,
                "points": away_info.get("points", 0),
                "goal_diff": away_info.get("goal_diff", 0),
                "played": away_info.get("played", 0),
                "position": away_info.get("position", "?"),
                "group": away_info.get("group", "?"),
                "md1_result": away_info.get("md1_result", "No data"),
                "md1_opponent": away_info.get("md1_opponent", "?"),
                "status": away_info.get("status", "Unknown"),
            },
        }
        return context

    def _calculate_real_standings(self, results_df) -> dict:
        """Calcula standings reales basado en resultados jugados."""
        import pandas as pd

        standings = {}

        if results_df.empty:
            return standings

        # PASO 1: Cargar mapa de grupos desde fixture.json (dinámico)
        team_to_group = self._load_group_mapping()

        # Si no se pudo cargar, retornar vacío
        if not team_to_group:
            logger.warning("No se pudo cargar los grupos desde fixture")
            return standings

        # PASO 2: Inicializar standings para todos los equipos
        groups_by_team = {}
        for team, group in team_to_group.items():
            if group not in standings:
                standings[group] = {}
            standings[group][team] = {"points": 0, "gf": 0, "ga": 0, "gd": 0, "played": 0}
            groups_by_team[team] = group

        # PASO 3: Procesar cada resultado
        for _, row in results_df.iterrows():
            home = row["home_team"]
            away = row["away_team"]
            h_score = row["home_score"]
            a_score = row["away_score"]

            # Saltar si falta score (partido no jugado)
            if pd.isna(h_score) or pd.isna(a_score):
                continue

            h_score, a_score = int(h_score), int(a_score)

            # Obtener grupo
            group_h = groups_by_team.get(home)
            group_a = groups_by_team.get(away)

            # Saltar si alguno no está en los equipos conocidos
            if not group_h or not group_a or group_h != group_a:
                continue

            group = group_h

            # Actualizar estadísticas
            standings[group][home]["played"] += 1
            standings[group][away]["played"] += 1
            standings[group][home]["gf"] += h_score
            standings[group][home]["ga"] += a_score
            standings[group][away]["gf"] += a_score
            standings[group][away]["ga"] += h_score

            # Puntos
            if h_score > a_score:
                standings[group][home]["points"] += 3
            elif h_score < a_score:
                standings[group][away]["points"] += 3
            else:
                standings[group][home]["points"] += 1
                standings[group][away]["points"] += 1

            # GD
            standings[group][home]["gd"] = standings[group][home]["gf"] - standings[group][home]["ga"]
            standings[group][away]["gd"] = standings[group][away]["gf"] - standings[group][away]["ga"]

        return standings

    def _load_group_mapping(self) -> dict:
        """Carga mapa dinámico equipo->grupo desde fixture.json (normalizado)."""
        import json

        team_to_group = {}

        try:
            with open(ROOT / "data/external/wc2026_fixture.json", encoding="utf-8") as f:
                fixture = json.load(f)

            # El fixture es un dict con "matches" (lista plana)
            matches = fixture.get("matches", [])
            for match in matches:
                group = match.get("group", "?")  # "Group A", "Group B", etc
                team1 = match.get("team1")
                team2 = match.get("team2")

                # Extraer solo la letra del grupo (Group A -> A)
                group_letter = group.replace("Group ", "").strip() if group else "?"

                if team1:
                    # Normalizar nombre y guardar
                    normalized_team1 = normalize_team_name(team1)
                    team_to_group[normalized_team1] = group_letter

                if team2:
                    # Normalizar nombre y guardar
                    normalized_team2 = normalize_team_name(team2)
                    team_to_group[normalized_team2] = group_letter

        except Exception as e:
            logger.warning(f"No se pudo cargar fixture.json: {e}")

        return team_to_group

    def _extract_team_from_standings(self, team_name: str, standings: dict, results_df) -> dict:
        """Extrae información de un equipo desde standings calculados."""
        import pandas as pd

        # Normalizar nombre del equipo PRIMERO
        normalized_team = normalize_team_name(team_name)

        info = {
            "points": 0,
            "goal_diff": 0,
            "played": 0,
            "position": "?",
            "group": "?",
            "md1_result": "No data",
            "md1_opponent": "?",
            "status": "Unknown",
        }

        # Buscar equipo en standings usando nombre normalizado
        for group, teams_data in standings.items():
            if normalized_team in teams_data:
                info["group"] = group
                team_stats = teams_data[normalized_team]
                info["points"] = team_stats.get("points", 0)
                info["goal_diff"] = team_stats.get("gd", 0)
                info["played"] = team_stats.get("played", 0)

                # Determinar estado y presión específica
                # Calcular si puede asegurar 1º con empate
                others_in_group = [t for t in teams_data.keys() if t != team_name]
                max_other_pts = max([teams_data[t]["points"] for t in others_in_group]) if others_in_group else 0

                if info["points"] == 0:
                    info["status"] = "Critical (0 pts, must win or OUT)"
                elif info["points"] == 1:
                    info["status"] = "In danger (1 pt, must win soon)"
                elif info["points"] >= 3:
                    # Equipo con 3+ puntos: analizar si puede perder
                    if info["played"] == 1:  # MD1 completado, MD2 pendiente
                        # ¿Cuántos puntos máximo puede tener otro equipo tras MD2?
                        max_others_after_md2 = max_other_pts + 3  # Si otro gana su MD2

                        # Si THIS equipo empata, tendrá points + 1
                        # Si another wins su MD2, tendrá max_other_pts + 3
                        team_with_draw = info["points"] + 1

                        if team_with_draw > max_others_after_md2:
                            info["status"] = "Can secure 1st with DRAW (comfortable)"
                        elif info["points"] + 3 > max_other_pts:
                            info["status"] = f"Need to WIN to secure 1st (pressure)"
                        else:
                            info["status"] = f"Advancing (likely, but watch GD)"
                    else:
                        info["status"] = "Advancing (likely)"
                else:
                    info["status"] = "Unknown"

                break

        # Buscar MD1 result (primer partido del equipo, no necesariamente 2026-06-11)
        normalized_team = normalize_team_name(team_name)
        if not results_df.empty:
            # Encontrar todos los partidos del equipo y tomar el primero
            team_matches = results_df[
                (results_df["home_team"] == normalized_team) |
                (results_df["away_team"] == normalized_team)
            ].sort_values("date")

            for _, row in team_matches.iterrows():
                if row["home_team"] == normalized_team or row["away_team"] == normalized_team:
                    home = row["home_team"]
                    away = row["away_team"]
                    h_score = row["home_score"]
                    a_score = row["away_score"]

                    if pd.isna(h_score) or pd.isna(a_score):
                        break

                    h_score, a_score = int(h_score), int(a_score)

                    if normalized_team == home:
                        info["md1_opponent"] = away
                        if h_score > a_score:
                            info["md1_result"] = f"WIN vs {away} ({h_score}-{a_score})"
                        elif h_score == a_score:
                            info["md1_result"] = f"DRAW vs {away} ({h_score}-{a_score})"
                        else:
                            info["md1_result"] = f"LOSS vs {away} ({h_score}-{a_score})"
                    else:
                        info["md1_opponent"] = home
                        if a_score > h_score:
                            info["md1_result"] = f"WIN vs {home} ({a_score}-{h_score})"
                        elif a_score == h_score:
                            info["md1_result"] = f"DRAW vs {home} ({h_score}-{a_score})"
                        else:
                            info["md1_result"] = f"LOSS vs {home} ({h_score}-{a_score})"
                    break

        return info

    def agent_1_group_analyst(
        self, home_team: str, away_team: str, context: dict
    ) -> str:
        """Agent 1: Group Analyst - Analiza lógica clasificatoria con datos reales."""
        home = context.get("home_team", {})
        away = context.get("away_team", {})

        prompt = f"""
Eres un experto analista de grupos en torneos de fútbol. Tienes datos REALES del torneo.

**SITUACION ACTUAL DEL PARTIDO:**
Grupo: {home.get("group", "?")}
- **{home.get("name")}** (Local): {home.get("points")} pts | GD: {home.get("goal_diff")} | Posición: {home.get("position")} | Estado: {home.get("status")}
  - MD1 Result: {home.get("md1_result")} (vs {home.get("md1_opponent")})

- **{away.get("name")}** (Visitante): {away.get("points")} pts | GD: {away.get("goal_diff")} | Posición: {away.get("position")} | Estado: {away.get("status")}
  - MD1 Result: {away.get("md1_result")} (vs {away.get("md1_opponent")})

**ANALIZA PROFUNDAMENTE:**
1. ¿Cuál es la diferencia de presión entre los dos equipos?
   - {home.get("name")}: {home.get("status")}
   - {away.get("name")}: {away.get("status")}

2. ¿Qué necesita cada equipo para CLASIFICAR?
   - Si {home.get("name")} GANA: ¿avanza?
   - Si EMPATAN: ¿quién queda en riesgo?
   - Si {away.get("name")} GANA: ¿cambia el panorama?

3. ¿Cómo influye MD1 en el estado mental de cada equipo?
   - {home.get("name")} salió de MD1: {home.get("md1_result")} → ¿moral alta o tensión?
   - {away.get("name")} salió de MD1: {away.get("md1_result")} → ¿motivado o desesperado?

4. PRESIÓN DIFERENCIAL: ¿Quién juega con más urgencia? ¿Quién puede perder?

5. Basándote en ESTA presión real, ¿cuáles marcadores son más probables?

**RESPONDE CON:**
- Razonamiento paso a paso
- Top 3 marcadores con probabilidad
- Explicación clasificatoria concreta

IMPORTANTE: Usa SOLO lógica deportiva y presión de clasificación REAL basada en la tabla actual.
"""
        response = self._call_deepseek(prompt, use_reasoner=True)
        return response

    def agent_2_tactical_scout(
        self, home_team: str, away_team: str, context: dict
    ) -> str:
        """Agent 2: Tactical Scout - Analiza tácticas y presión clasificatoria."""
        home = context.get("home_team", {})
        away = context.get("away_team", {})

        prompt = f"""
Eres un estratega táctico de fútbol experto. Analizas NO SOLO tácticas, sino cómo la presión clasificatoria CAMBIA las tácticas.

**SITUACION TACTÍCA + CLASIFICATORIA:**
- **{home.get("name")}** (Local): {home.get("status")}
  - MD1: {home.get("md1_result")}
  - ¿Jugará ofensivo o conservador basado en su situación?

- **{away.get("name")}** (Visitante): {away.get("status")}
  - MD1: {away.get("md1_result")}
  - ¿Jugará desesperado o ordenado?

**ANALIZA:**
1. Estilos de juego (ofensivo/defensivo) + cómo la presión los modifica
   - Si {home.get("name")} PUEDE PERDER: ¿se vuelve más ofensivo o se repliega?
   - Si {away.get("name")} DEBE GANAR: ¿ataca desde el minuto 1 o busca contragolpes?

2. Fortalezas/debilidades DE CADA EQUIPO en este torneo (basado en MD1)

3. Cómo cambiaría el juego táctico si {away.get("name")} marca primero

4. Ventaja de campo: ¿afecta la táctica o solo la psicología?

5. Histórico vs este rival (si existe)

**RESPONDE:**
- Razonamiento táctico paso a paso
- Top 3 marcadores basados en TÁCTICAS + PRESIÓN
- Cómo crees que jugaría cada equipo dado su estado actual

IMPORTANTE: La presión clasificatoria MODIFICA las tácticas. Analiza ambas.
"""
        response = self._call_deepseek(prompt, use_reasoner=True)
        return response

    def agent_3_sentiment_reader(
        self, home_team: str, away_team: str, context: dict
    ) -> str:
        """Agent 3: Sentiment Reader - Analiza moral REAL basada en MD1."""
        home = context.get("home_team", {})
        away = context.get("away_team", {})

        # Interpretar el resultado de MD1 en términos psicológicos
        home_md1 = home.get("md1_result", "No data")
        away_md1 = away.get("md1_result", "No data")

        prompt = f"""
Eres un experto en psicología deportiva. Analizas el MOMENTUM REAL basado en MD1.

**MOMENTUM REAL DE MD1 (hace poco, aún fresco emocionalmente):**

**{home.get("name")}** (Local):
- Resultado: {home_md1}
- Estado actual: {home.get("status")}
- Psicológicamente: ¿Ganó cómodo (confiado), ganó ajustado (tenso), o perdió (destruido)?

**{away.get("name")}** (Visitante):
- Resultado: {away_md1}
- Estado actual: {away.get("status")}
- Psicológicamente: ¿Fue goleada (colapsado), derrota ajustada (puede recuperarse), o victoria (eufórico)?

**ANALIZA PROFUNDAMENTE:**

1. **Momentum emocional REAL:**
   - Si {home.get("name")} {home_md1}: ¿cuál es su estado mental AHORA?
   - Si {away.get("name")} {away_md1}: ¿está motivado para redimirse o destruido?

2. **Confianza basada en MD1:**
   - ¿Quién llega a este partido con confianza? ¿Quién llega ansioso?
   - Una victoria 5-0 vs una victoria 1-0 son psicológicamente DIFERENTES

3. **Presión psicológica DIFERENCIAL:**
   - {home.get("name")} necesita: {home.get("status")}
   - {away.get("name")} necesita: {away.get("status")}
   - ¿Quién juega con más "nervios"? ¿Quién juega "suelto"?

4. **Colapso mental:**
   - ¿{home.get("name")} tiene riesgo de colapsar (0 pts después de MD2)?
   - ¿{away.get("name")} llegó desesperado desde MD1?

5. **Efecto "necesidad":**
   - ¿Genera goles la desesperación o errores?
   - {away.get("name")} necesita ganar → ¿ataca o se bloquea?

**RESPONDE:**
- Análisis psicológico basado en MD1 REAL
- Top 3 marcadores considerando MORAL + PRESIÓN
- Cómo el resultado de MD1 influye en este partido

IMPORTANTE: La psicología deportiva se basa en eventos REALES, no teóricos. MD1 fue hace poco.
"""
        response = self._call_deepseek(prompt, use_reasoner=True)
        return response

    def debate_round_2(
        self, agent1: str, agent2: str, agent3: str, home_team: str, away_team: str
    ) -> tuple[str, str, str]:
        """Ronda 2: Cada agente rebate a los otros."""

        # Agent 1 rebate
        rebate1_prompt = f"""
En un debate sobre {home_team} vs {away_team}:

Mi posición inicial fue:
{agent1[:500]}

Otros expertos argumentaron:

Expert 2 (Tactical):
{agent2[:500]}

Expert 3 (Sentiment):
{agent3[:500]}

Responde BREVEMENTE (máx 300 palabras):
- ¿Estoy en desacuerdo con ellos? ¿Por qué?
- ¿Me convencen? ¿Qué puntos son válidos?
- ¿Ajustas tu predicción de marcador?
- Defiende tu posición
"""
        rebate1 = self._call_deepseek(rebate1_prompt, use_reasoner=True)

        # Agent 2 rebate
        rebate2_prompt = f"""
En un debate sobre {home_team} vs {away_team}:

Mi posición inicial (Tactical Scout) fue:
{agent2[:500]}

Otros expertos argumentaron:

Expert 1 (Group Analyst):
{agent1[:500]}

Expert 3 (Sentiment):
{agent3[:500]}

Responde BREVEMENTE (máx 300 palabras):
- ¿Estoy en desacuerdo con ellos? ¿Por qué?
- ¿Me convencen? ¿Qué puntos son válidos?
- ¿Ajustas tu predicción de marcador?
- Defiende tu posición
"""
        rebate2 = self._call_deepseek(rebate2_prompt, use_reasoner=True)

        # Agent 3 rebate
        rebate3_prompt = f"""
En un debate sobre {home_team} vs {away_team}:

Mi posición inicial (Sentiment Reader) fue:
{agent3[:500]}

Otros expertos argumentaron:

Expert 1 (Group Analyst):
{agent1[:500]}

Expert 2 (Tactical):
{agent2[:500]}

Responde BREVEMENTE (máx 300 palabras):
- ¿Estoy en desacuerdo con ellos? ¿Por qué?
- ¿Me convencen? ¿Qué puntos son válidos?
- ¿Ajustas tu predicción de marcador?
- Defiende tu posición
"""
        rebate3 = self._call_deepseek(rebate3_prompt, use_reasoner=True)

        return rebate1, rebate2, rebate3

    def consensus_round(
        self,
        home_team: str,
        away_team: str,
        agent1: str,
        agent2: str,
        agent3: str,
        rebate1: str,
        rebate2: str,
        rebate3: str,
        context: dict,
    ) -> str:
        """Ronda 3: Los 3 agentes llegan a consenso CON IMPACTO EN CLASIFICACION."""
        home = context.get("home_team", {})
        away = context.get("away_team", {})

        consensus_prompt = f"""
Los 3 expertos debaten sobre: {home_team} vs {away_team}

**CONTEXTO DE CLASIFICACION:**
- {home.get("name")}: {home.get("status")} ({home.get("points")} pts)
- {away.get("name")}: {away.get("status")} ({away.get("points")} pts)

POSICIONES INICIALES Y REBATES:

Group Analyst (clasificacion):
{agent1[:400]}
Rebate: {rebate1[:200]}

Tactical Scout (tácticas + presión):
{agent2[:400]}
Rebate: {rebate2[:200]}

Sentiment Reader (psicología MD1):
{agent3[:400]}
Rebate: {rebate3[:200]}

---

AHORA CONSENSO FINAL CON IMPACTO EN CLASIFICACION:

Los 3 expertos llegan a acuerdo sobre los TOP 3 MARCADORES Y SU IMPACTO EN CLASIFICACION.

RESPONDE EN ESTE FORMATO:

🥇 PREDICCIÓN #1: [MARCADOR] ([PROBABILIDAD]%)
   Razón consensuada: [Explicación unificada]
   Impacto clasificación: [¿Quién avanza? ¿Quién queda en riesgo? ¿Eliminación directa?]

🥈 PREDICCIÓN #2: [MARCADOR] ([PROBABILIDAD]%)
   Razón consensuada: [Explicación unificada]
   Impacto clasificación: [Cambios en la tabla]

🥉 PREDICCIÓN #3: [MARCADOR] ([PROBABILIDAD]%)
   Razón consensuada: [Explicación unificada]
   Impacto clasificación: [Escenario]

ANÁLISIS FINAL (3-4 líneas):
- ¿En qué convergieron los 3 expertos? (presión diferencial, MD1 momentum, etc)
- ¿Dónde divergieron?
- Confianza general en la predicción (0-10)
- Confianza específica en el impacto clasificatorio

IMPORTANTE: Termina tu respuesta con esta línea EXACTA (sin texto adicional antes ni después,
usando los goles de tu PREDICCIÓN #1 y PREDICCIÓN #2, donde "home" = {home_team} y "away" = {away_team}):
RESULTADO_JSON: {{"predictions": [{{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}, {{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}]}}
"""
        # max_tokens alto: el razonamiento del reasoner + las 3 predicciones + el
        # bloque JSON final pueden agotar el límite por defecto (2000) antes de
        # emitir la línea RESULTADO_JSON, dejando top_prediction sin parsear.
        consensus = self._call_deepseek(consensus_prompt, use_reasoner=True, max_tokens=3500)
        return consensus

    @staticmethod
    def _prediction_with_winner(data: dict) -> dict:
        home_goals = int(data["home_goals"])
        away_goals = int(data["away_goals"])
        if home_goals > away_goals:
            winner = "home"
        elif home_goals < away_goals:
            winner = "away"
        else:
            winner = "draw"
        return {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "probability": float(data.get("probability", 0)),
            "predicted_winner": winner,
        }

    @classmethod
    def parse_top_prediction(cls, consensus_text: str) -> Optional[dict]:
        """Extrae la predicción #1 estructurada (compat hacia atrás)."""
        predictions = cls.parse_predictions(consensus_text)
        return predictions[0] if predictions else None

    @classmethod
    def parse_predictions(cls, consensus_text: str) -> list[dict]:
        """Extrae las predicciones #1 y #2 estructuradas del bloque RESULTADO_JSON.

        Soporta también el formato viejo de una sola predicción
        ({"home_goals": ..., "away_goals": ...}) para no romper resultados
        ya guardados antes de este cambio.
        """
        import re

        match = re.search(r"RESULTADO_JSON:\s*(\{.*?\})\s*$", consensus_text.strip(), re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))
            if "predictions" in data:
                predictions = data["predictions"]
                if not isinstance(predictions, list):
                    return []
                return [cls._prediction_with_winner(p) for p in predictions[:2]]
            # formato viejo: una sola predicción suelta
            return [cls._prediction_with_winner(data)]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError):
            logger.warning("No se pudo parsear RESULTADO_JSON del consenso")
            return []

    def predict_match(self, home_team: str, away_team: str) -> dict:
        """Ejecuta el debate completo para un partido CON CONTEXTO REAL."""
        logger.info(f"Iniciando Agent Debate para: {home_team} vs {away_team}")

        context = self.get_group_context(home_team, away_team)

        # Log contexto para auditoría
        logger.info(f"  Contexto cargado: {home_team} ({context['home_team'].get('status')}) vs {away_team} ({context['away_team'].get('status')})")

        # Ronda 1: Posiciones iniciales
        logger.info("  Ronda 1: Posiciones iniciales...")
        agent1_pos = self.agent_1_group_analyst(home_team, away_team, context)
        agent2_pos = self.agent_2_tactical_scout(home_team, away_team, context)
        agent3_pos = self.agent_3_sentiment_reader(home_team, away_team, context)

        # Ronda 2: Rebates
        logger.info("  Ronda 2: Rebates...")
        rebate1, rebate2, rebate3 = self.debate_round_2(
            agent1_pos, agent2_pos, agent3_pos, home_team, away_team
        )

        # Ronda 3: Consenso CON CONTEXTO
        logger.info("  Ronda 3: Consenso...")
        consensus = self.consensus_round(
            home_team,
            away_team,
            agent1_pos,
            agent2_pos,
            agent3_pos,
            rebate1,
            rebate2,
            rebate3,
            context,
        )

        predictions = self.parse_predictions(consensus)

        return {
            "match": f"{home_team} vs {away_team}",
            "context": context,
            "round_1": {
                "group_analyst": agent1_pos,
                "tactical_scout": agent2_pos,
                "sentiment_reader": agent3_pos,
            },
            "round_2": {"rebate_1": rebate1, "rebate_2": rebate2, "rebate_3": rebate3},
            "consensus": consensus,
            # "predictions": top-2 estructuradas (home_goals/away_goals/probability/predicted_winner)
            # "top_prediction": compat hacia atrás, igual a predictions[0]
            "predictions": predictions,
            "top_prediction": predictions[0] if predictions else None,
        }

    def close(self):
        """Cierra la conexión HTTP."""
        self.client.close()
