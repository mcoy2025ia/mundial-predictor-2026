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

    def get_full_group_context(self, home_team: str, away_team: str) -> dict:
        """Contexto COMPLETO del grupo: tabla 4 equipos, partidos jugados, análisis de terceros."""
        import pandas as pd
        import json

        # Cargar resultados y fixture
        try:
            results_df = pd.read_csv(ROOT / "data/external/wc2026_live_results.csv")
        except:
            results_df = pd.DataFrame()

        # Calcular standings reales
        standings = self._calculate_real_standings(results_df)

        # Obtener grupo del partido
        team_to_group = self._load_group_mapping()
        group_letter = team_to_group.get(normalize_team_name(home_team), "?")

        if group_letter not in standings:
            return {"error": f"Group {group_letter} not found"}

        # Tabla completa del grupo (4 equipos ordenados)
        group_standings = standings[group_letter]
        table = sorted(
            [
                {
                    "pos": i + 1,
                    "team": t,
                    "pts": group_standings[t]["points"],
                    "played": group_standings[t]["played"],
                    "gf": group_standings[t]["gf"],
                    "ga": group_standings[t]["ga"],
                    "gd": group_standings[t]["gd"],
                }
                for i, t in enumerate(group_standings.keys())
            ],
            key=lambda x: (-x["pts"], -x["gd"], -x["gf"]),
        )

        # Partidos jugados del grupo (histórico)
        matches_played = []
        if not results_df.empty:
            group_matches = results_df[
                (results_df["home_team"].isin(group_standings.keys())) |
                (results_df["away_team"].isin(group_standings.keys()))
            ].sort_values("date")

            for _, row in group_matches.iterrows():
                h_score = row["home_score"]
                a_score = row["away_score"]
                if not (pd.isna(h_score) or pd.isna(a_score)):
                    matches_played.append({
                        "date": row["date"],
                        "result": f"{row['home_team']} {int(h_score)}-{int(a_score)} {row['away_team']}"
                    })

        # Análisis de terceros: ¿cuál es el mejor tercero actual?
        # (simplificado: si hay >3 grupos jugados, comparar terceros)
        best_third = {"team": "TBD", "pts": 0, "gd": -999}
        third_analysis = f"This group 3rd: {table[2]['team']} ({table[2]['pts']} pts, GD {table[2]['gd']})"

        # Escenarios de clasificación para este partido
        scenarios = {
            "if_home_wins": f"{home_team} → 1st, {away_team} → 2nd (likely)",
            "if_draw": f"Both on same points, GD decides ranking",
            "if_away_wins": f"{away_team} → 1st, {home_team} → 2nd (likely)",
        }

        # Contexto completo
        full_context = {
            "group": group_letter,
            "table": table,
            "matches_played": matches_played,
            "best_third_so_far": best_third,
            "third_analysis": third_analysis,
            "classification_scenarios": scenarios,
            "home_team_name": home_team,
            "away_team_name": away_team,
        }

        return full_context

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
                elif info["points"] >= 6:
                    # 6 puntos = Dos victorias o 2V+1E (YA CLASIFICADO)
                    info["status"] = "Already through (6 pts, qualified)"
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
                    elif info["played"] == 2:  # MD2 completado, MD3 pendiente
                        # En MD3: con 3 puntos, puede perder; con 4-5 es cómodo; con 6 ya está fuera
                        max_others_after_md3 = max_other_pts + 3
                        team_with_draw = info["points"] + 1

                        if info["points"] == 3:
                            # 3 puntos: puede perder solo si otro baja
                            if max_other_pts < 3:  # Otro equipo aún tiene menos
                                info["status"] = "Third place watch (3 pts, tight)"
                            else:
                                info["status"] = "Must win (3 pts, depends on others)"
                        elif info["points"] in [4, 5]:
                            info["status"] = "Comfortable (4-5 pts, likely advances)"
                        else:
                            info["status"] = "Unknown"
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
        """Agent 1: Group Analyst - Analiza TODA la secuencia del grupo + clasificación."""
        group = context.get("group", "?")
        table = context.get("table", [])
        matches = context.get("matches_played", [])
        scenarios = context.get("classification_scenarios", {})

        # Formatear tabla
        table_str = "Posición | Equipo | Pts | J | GF | GA | GD\n"
        for row in table:
            table_str += f"{row['pos']}. {row['team']:20} | {row['pts']} | {row['played']} | {row['gf']} | {row['ga']} | {row['gd']}\n"

        # Formatear histórico
        matches_str = "\n".join([f"  {m['date']}: {m['result']}" for m in matches[-5:]])  # Últimos 5

        prompt = f"""
Eres un experto analista de grupos en torneos de fútbol. ANALIZA LA SECUENCIA COMPLETA del grupo, no solo estos 2 equipos.

**TABLA ACTUAL GRUPO {group}:**
{table_str}

**HISTÓRICO DE PARTIDOS (últimos):**
{matches_str or "  (No matches yet)"}

**PRÓXIMO PARTIDO:** {home_team} vs {away_team}

**ESCENARIOS DE CLASIFICACIÓN:**
- Si {home_team} gana: {scenarios.get("if_home_wins", "N/A")}
- Si empatan: {scenarios.get("if_draw", "N/A")}
- Si {away_team} gana: {scenarios.get("if_away_wins", "N/A")}

**ANALIZA PROFUNDAMENTE (extendiéndote):**

1. **SECUENCIA DEL GRUPO:** ¿Qué patrones ves en los partidos ya jugados?
   - ¿Hay favoritos claros?
   - ¿Hay sorpresas (como la derrota de Alemania 1-0 vs Ecuador)?
   - ¿Cómo impacta eso en la dinámica?

2. **PRESIÓN DIFERENCIAL REAL:**
   - ¿Qué presión tiene {home_team}? (Clasificación segura? Debe ganar? Corre riesgo de tercero?)
   - ¿Qué presión tiene {away_team}? (Mismos análisis)
   - ¿Alguien juega a no perder? ¿Alguien juega desesperado?

3. **ANÁLISIS DE TERCEROS:**
   - {context.get("third_analysis", "N/A")}
   - ¿Si {home_team} gana 2-0 vs {away_team}, mejora su posición de tercero en otros grupos?
   - ¿Qué diferencia de goles es crítica?

4. **MARCADORES MÁS PROBABLES:**
   - Basándote en la secuencia del grupo y presión real
   - Top 3 marcadores con probabilidad
   - Justificación por cada uno

**IMPORTANTE:** Análiza toda la secuencia, no solo 2 equipos. El batacazo de Ecuador vs Alemania cambió dinámicas.
"""
        response = self._call_deepseek(prompt, use_reasoner=True)
        return response

    def agent_2_tactical_scout(
        self, home_team: str, away_team: str, context: dict
    ) -> str:
        """Agent 2: Tactical Scout - Analiza tácticas MODULADAS por presión de clasificación."""
        group = context.get("group", "?")
        table = context.get("table", [])
        matches = context.get("matches_played", [])

        # Encontrar posiciones en tabla
        home_row = next((r for r in table if r["team"] == home_team), None)
        away_row = next((r for r in table if r["team"] == away_team), None)

        home_status = f"{home_row['pos']}º lugar, {home_row['pts']} pts" if home_row else "?"
        away_status = f"{away_row['pos']}º lugar, {away_row['pts']} pts" if away_row else "?"

        prompt = f"""
Eres un estratega táctico experto. NO analizas solo tácticas → analizas CÓMO LA PRESIÓN DE CLASIFICACIÓN MODULA LAS TÁCTICAS.

**TABLA Y CONTEXTO:**
{home_team}: {home_status}
{away_team}: {away_status}

**HISTÓRICO (últimos partidos):**
{chr(10).join([f"  {m['result']}" for m in matches[-3:]] or ["  (sin datos)"])}

**PRESIÓN TÁCTICA:**
- Si {home_team} DEBE GANAR (0-2 pts): Ataca siempre. Riesgo defensivo.
- Si {home_team} PUEDE PERDER (3-5 pts): Balance ataque/defensa. Busca no perder.
- Si {home_team} YA CLASIFICADO (6 pts): Probablemente ROTA. Juego más relajado/experimental.

(Mismo análisis para {away_team})

**ANALIZA PROFUNDAMENTE:**

1. **PRESIÓN TÁCTICA REAL (no genérica):**
   - {home_team}: ¿Presión de clasificación? ¿O presión de terceros (ganar + goles)?
   - {away_team}: ¿Desesperado o conservador?
   - ¿Alguien jugará en "modo rotación"?

2. **MODIFICACIÓN TÁCTICA POR PRESIÓN:**
   - Si {home_team} está en 1º pero {away_team} en 4º:
     * {home_team} puede jugar más relajado (MENOS ofensivo)
     * {away_team} DEBE atacar (DEFENSA más expuesta)
   - Esto cambia el patrón de goles esperado

3. **ANÁLISIS DE TERCEROS EN TÁCTICA:**
   - ¿{home_team} necesita ganar 2+ goles para mejorar su posición de tercero?
   - ¿Eso afecta su táctica? (Ataque más agresivo en 2ª mitad si van 1-0 abajo)

4. **ESTILOS HISTÓRICOS + PRESIÓN ACTUAL:**
   - Estilo conocido de {home_team} en torneos
   - ¿Cómo se adapta ese estilo cuando tiene presión de clasificación?

5. **MARCADORES MÁS PROBABLES POR TÁCTICA:**
   - Top 3 con confianza
   - Explicación: "Si {home_team} juega conservador (ya clasificado), espero 0-0 o 1-0"

**IMPORTANTE:**
- La presión de TERCEROS es tan importante como la de 1º/2º/eliminación
- Analiza si alguien necesita "ganar X goles" para tercero
- Presión ≠ solo jugar ofensivo → presión sobre terceros = estrategia de ataque+goles
"""
        response = self._call_deepseek(prompt, use_reasoner=True)
        return response

    def agent_3_sentiment_reader(
        self, home_team: str, away_team: str, context: dict
    ) -> str:
        """Agent 3: Sentiment Reader - Analiza MOMENTUM real de la SECUENCIA del grupo."""
        table = context.get("table", [])
        matches = context.get("matches_played", [])

        # Formatear histórico completo
        matches_str = "\n".join([f"  {m['result']}" for m in matches]) or "  (sin datos)"

        # Obtener filas de tabla para ambos equipos
        home_row = next((r for r in table if r["team"] == home_team), None)
        away_row = next((r for r in table if r["team"] == away_team), None)

        prompt = f"""
Eres un experto en psicología deportiva. Analizas el MOMENTUM REAL de LA SECUENCIA COMPLETA del grupo, no solo MD1.

**HISTÓRICO COMPLETO DEL GRUPO (lo que pasó, patrones emocionales):**
{matches_str}

**POSICIONES ACTUALES:**
{home_team}: {home_row['pos']}º, {home_row['pts']} pts, GD {home_row['gd']} ({home_row['gf']}-{home_row['ga']})
{away_team}: {away_row['pos']}º, {away_row['pts']} pts, GD {away_row['gd']} ({away_row['gf']}-{away_row['ga']})

**ANALIZA PROFUNDAMENTE (extendiéndote):**

1. **PATRONES EMOCIONALES EN LA SECUENCIA:**
   - Últimos resultados: ¿hay una tendencia? (mejorando, empeorando, consistente)
   - Ejemplo: "Ecuador sorprendió con victoria sobre Alemania 1-0 → moral alta, Alemania derrumbada"
   - ¿Hay equipos colapsados vs equipos en racha?

2. **MOMENTUM DIFERENCIAL:**
   - {home_team}: ¿llega en racha positiva o negativa? ¿Confiado o dudando?
   - {away_team}: ¿misma evaluación?
   - ¿Quién tiene VENTAJA PSICOLÓGICA?

3. **PRESIÓN EMOCIONAL (no solo lógica):**
   - {home_team} está en posición {home_row['pos']}. ¿Miedo a perder o confianza de ganar?
   - {away_team} está en posición {away_row['pos']}. ¿Desesperación o tranquilidad?
   - ¿Alguien colapsará bajo presión? ¿Alguien jugará "suelto"?

4. **EFECTO SORPRESA:**
   - ¿Ha habido goleadas en el grupo? ¿Sorpresas?
   - Ejemplo: Si Alemania perdió 1-0 y juega ahora, ¿psicológicamente buscará revancha (más arriesgado)?
   - ¿Eso genera más goles?

5. **PRESIÓN DE TERCEROS (emocional):**
   - {home_team}: ¿solo le importa clasificar de tercero? ¿Eso genera más urgencia emocional?
   - ¿Necesita ganar por goleada? ¿Eso afecta su psicología (presión → errores)?

**RESPONDE:**
- Análisis psicológico basado en SECUENCIA real del grupo
- Top 3 marcadores considerando MOMENTUM + PRESIÓN EMOCIONAL
- Cómo la secuencia de partidos influye emocionalmente en este partido

IMPORTANTE: No analices solo los 2 equipos. El contexto completo (goleadas, sorpresas, colapsas) define la psicología.
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

AHORA CADA EXPERTO PROPONE SU PREDICCIÓN FINAL Y LLEGAN A CONSENSO:

RESPONDE EN ESTE FORMATO:

🔵 **Group Analyst** (clasificación + presión): [MARCADOR] ([PROBABILIDAD]%)
   Análisis: [1 línea]

🟠 **Tactical Scout** (tácticas): [MARCADOR] ([PROBABILIDAD]%)
   Análisis: [1 línea]

🟡 **Sentiment Reader** (psicología MD1): [MARCADOR] ([PROBABILIDAD]%)
   Análisis: [1 línea]

🏆 **CONSENSO FINAL**: Ranking de probabilidad considerando las 3 posiciones

ANÁLISIS FINAL (2-3 líneas):
- ¿En qué convergieron los 3 expertos? (presión diferencial, MD1 momentum, etc)
- Confianza general en la predicción (0-10)

IMPORTANTE: Termina tu respuesta con esta línea EXACTA (sin texto adicional antes ni después.
Las 4 predicciones son: 1 de cada agente individual + 1 de consenso):
RESULTADO_JSON: {{"group_analyst": {{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}, "tactical_scout": {{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}, "sentiment_reader": {{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}, "consensus": {{"home_goals": <int>, "away_goals": <int>, "probability": <float 0-1>}}}}
"""
        # max_tokens 4500: razonamiento del reasoner + 4 predicciones individuales + análisis + bloque JSON.
        consensus = self._call_deepseek(consensus_prompt, use_reasoner=True, max_tokens=4500)
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
        result = {
            "home_goals": home_goals,
            "away_goals": away_goals,
            "probability": float(data.get("probability", 0)),
            "predicted_winner": winner,
        }
        # Incluir nombre del agente si existe (para trazabilidad)
        if "agent" in data:
            result["agent"] = data["agent"]
        return result

    @classmethod
    def parse_top_prediction(cls, consensus_text: str) -> Optional[dict]:
        """Extrae la predicción #1 estructurada (compat hacia atrás)."""
        predictions = cls.parse_predictions(consensus_text)
        return predictions[0] if predictions else None

    @classmethod
    def parse_predictions(cls, consensus_text: str) -> list[dict]:
        """Extrae las 4 predicciones (3 agentes + consenso) del bloque RESULTADO_JSON.

        Formato nuevo:
        {
          "group_analyst": {...},
          "tactical_scout": {...},
          "sentiment_reader": {...},
          "consensus": {...}
        }

        Retorna lista: [agent1, agent2, agent3, consensus]
        con campos agent="Group Analyst"|"Tactical Scout"|"Sentiment Reader"|"Consensus"
        """
        import re

        match = re.search(r"RESULTADO_JSON:\s*(\{.*?\})\s*$", consensus_text.strip(), re.DOTALL)
        if not match:
            return []
        try:
            data = json.loads(match.group(1))

            # Formato nuevo: 4 predicciones estructuradas
            if all(k in data for k in ["group_analyst", "tactical_scout", "sentiment_reader", "consensus"]):
                predictions = []
                agent_map = {
                    "group_analyst": "Group Analyst",
                    "tactical_scout": "Tactical Scout",
                    "sentiment_reader": "Sentiment Reader",
                    "consensus": "Consensus"
                }
                for key in ["group_analyst", "tactical_scout", "sentiment_reader", "consensus"]:
                    p = data[key].copy()
                    p["agent"] = agent_map[key]
                    predictions.append(cls._prediction_with_winner(p))
                return predictions

            # Formato viejo: array de predicciones (compatibilidad hacia atrás)
            if "predictions" in data:
                predictions = data["predictions"]
                if not isinstance(predictions, list):
                    return []
                return [cls._prediction_with_winner(p) for p in predictions[:2]]

            # Formato viejo: una sola predicción suelta
            return [cls._prediction_with_winner(data)]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            logger.warning("No se pudo parsear RESULTADO_JSON del consenso: %s", e)
            return []

    def predict_match(self, home_team: str, away_team: str) -> dict:
        """Ejecuta el debate completo para un partido CON CONTEXTO COMPLETO DEL GRUPO."""
        logger.info(f"Iniciando Agent Debate para: {home_team} vs {away_team}")

        # Contexto completo del grupo (tabla 4 equipos, histórico, terceros)
        context = self.get_full_group_context(home_team, away_team)

        if "error" in context:
            logger.error(f"  Error cargando contexto: {context['error']}")
            return None

        # Log contexto para auditoría
        logger.info(f"  Grupo {context['group']}: {len(context['table'])} equipos, {len(context['matches_played'])} partidos jugados")

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
            "home": home_team,
            "away": away_team,
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
