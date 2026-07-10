"""Oráculo de Eliminatorias — panel especializado para cuartos, semifinales y final.

Voz nueva y premium (separada del debate de 3 agentes de `agent_debate.py` y del
Cazador de Sorpresas de `upset_agent.py`) que SOLO corre en las rondas finales:
Quarter-final, Semi-final, Final y Match for third place.

A diferencia del debate de 3 agentes —que solo predice el marcador a 90'— este
panel razona la ELIMINATORIA COMPLETA: 90' → prórroga → penaltis → quién AVANZA.
Nunca deja un empate como resultado final de la llave.

Composición (5 llamadas a `deepseek-reasoner`, el modelo caro, por partido):
  1. Group Analyst                — campaña de grupos + knockout proyectada a 120'+
  2. Tactical Scout               — táctica, balón parado, ventaja si el partido se alarga
  3. Sentiment Reader             — psicología, temple para la tanda de penales
  4. Especialista en Definiciones — prórroga y penales (banca, históricos, portero) [NUEVO]
  + Consenso                      — reconcilia las 4 voces en un veredicto de avance

Cada voz emite la estructura de avance completa (ver SHARED_RULES). El módulo
valida y corrige la coherencia (90'↔prórroga↔penales↔clasificado) antes de
guardar, de modo que la salida siempre nombra un equipo clasificado.

Escribe data/processed/knockout_oracle_predictions.json (+ copia en frontend).
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

# Rondas en las que aplica el Oráculo (etiquetas del fixture / bracket resuelto).
ORACLE_ROUNDS = {"Quarter-final", "Semi-final", "Final", "Match for third place"}

VALID_PHASES = {"90_minutos", "tiempo_extra", "penaltis"}
VALID_CONVICTIONS = {"baja", "media", "alta"}

# Especialistas del panel: clave interna → (nombre visible, especialidad).
PANEL = {
    "group_analyst": ("Group Analyst", "campaña y regularidad en el torneo"),
    "tactical_scout": ("Tactical Scout", "táctica, transiciones y balón parado"),
    "sentiment_reader": ("Sentiment Reader", "psicología, momentum y temple"),
    "definitions_specialist": ("Especialista en Definiciones", "prórroga y penales"),
}


# ── Contrato compartido de eliminación directa ──────────────────────────────
SHARED_RULES = """
CONTEXTO DE ELIMINACIÓN DIRECTA (obligatorio):
El partido puede terminar de una de estas tres formas y SIEMPRE hay un clasificado:
  1. Un equipo gana en los 90 minutos.
  2. Empate en 90' → prórroga; un equipo gana en el tiempo extra (120').
  3. Empate tras 120' → tanda de penales, que define al clasificado.
NUNCA dejes la llave sin resolver. El resultado final NO puede ser "empate".

COHERENCIA OBLIGATORIA entre campos:
  • Si hay ganador en 90'  → habra_tiempo_extra=false, marcador_120_minutos=null,
    habra_penaltis=false, resultado_penaltis=null, fase_de_definicion="90_minutos".
  • Si hay empate en 90'   → habra_tiempo_extra=true (obligatorio).
  • Si hay ganador en 120' → habra_penaltis=false, resultado_penaltis=null,
    fase_de_definicion="tiempo_extra".
  • Si sigue empate en 120'→ habra_penaltis=true, resultado_penaltis con un ganador,
    fase_de_definicion="penaltis".
  • equipo_clasificado DEBE coincidir con el ganador de la fase que definió la llave.

NO mandes automáticamente todo empate a la prórroga ni sigas por inercia al favorito.
Evalúa explícitamente: diferencia de nivel, pegada y solidez, marcadores cerrados,
fatiga y profundidad de banca, experiencia en eliminatorias, capacidad de remontada,
nivel de los porteros, historial en penales y la tendencia del técnico a proteger el
empate. Distingue P(empate en 90') de P(el empate siga en prórroga) de P(penales).
"""

OUTPUT_CONTRACT = """
IMPORTANTE: escribe TODO el texto (el análisis y sobre todo "explicacion") en
ESPAÑOL neutro. NUNCA en inglés — ni una frase, ni una palabra suelta.

Escribe primero 3-6 líneas de análisis EN ESPAÑOL desde TU especialidad y TERMINA
EXACTO con esta línea (un único objeto JSON válido, sin texto después):
RESULTADO_JSON: {{"agente": "{agent}", "especialidad": "{specialty}", "marcador_90_minutos": {{"equipo_local": <int>, "equipo_visitante": <int>}}, "habra_tiempo_extra": <bool>, "marcador_120_minutos": {marcador120}, "habra_penaltis": <bool>, "resultado_penaltis": {penaltis}, "equipo_clasificado": "<{home} o {away}>", "fase_de_definicion": "<90_minutos|tiempo_extra|penaltis>", "conviccion": "<baja|media|alta>", "explicacion": "<EN ESPAÑOL, máx 45 palabras, di por qué termina en 90', prórroga o penales>"}}
donde equipo_local = {home} y equipo_visitante = {away}.
marcador_120_minutos = null si no hay prórroga; resultado_penaltis = null si no hay penales
(y {{"equipo_local": <int>, "equipo_visitante": <int>}} si sí los hay).
"""


class KnockoutOracle:
    """Panel de eliminatorias (QF/SF/Final) con deepseek-reasoner."""

    def __init__(self, timeout: float = 120.0) -> None:
        self.client = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "KnockoutOracle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── LLM ─────────────────────────────────────────────────────────────────
    def _call(self, prompt: str, max_tokens: int = 3200) -> str:
        """deepseek-reasoner (caro); cae a deepseek-chat si el contenido viene vacío.

        deepseek-reasoner cuenta los tokens de razonamiento contra max_tokens: si el
        pensamiento consume todo el presupuesto, `content` vuelve vacío con 200 OK.
        """
        for model in ("deepseek-reasoner", "deepseek-chat"):
            resp = self.client.post(
                DEEPSEEK_URL,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 1.0 if model == "deepseek-reasoner" else 0.7,
                    "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek API error ({model}): {resp.text[:300]}")
            content = resp.json()["choices"][0]["message"]["content"]
            if content and content.strip():
                return content
            logger.warning("%s devolvió contenido vacío; reintento con fallback", model)
        return ""

    # ── Prompts ─────────────────────────────────────────────────────────────
    @staticmethod
    def _evidence_block(home: str, away: str, ev: dict) -> str:
        """Dossier rico por equipo — evidencia real derivada de datos en disco.

        Cada línea se omite si su señal no está disponible (None), para no meter
        ruido ni afirmaciones vacías. La evidencia la arma el runner vía MatchIntel
        + ELO + historial de tandas + descanso.
        """
        def dossier(team: str, side: str) -> str:
            row = ev.get(f"{side}_row", {}) or {}
            lines = [
                f"  ▸ {team} — {ev.get(f'{side}_qual', '?')}: "
                f"{row.get('pts', 0)} pts, GD {row.get('gd', 0):+d}, "
                f"GF {row.get('gf', 0)} / GA {row.get('ga', 0)}"
            ]
            elo = ev.get(f"{side}_elo")
            if elo is not None:
                tier = ev.get(f"{side}_tier")
                lines.append(f"    ELO {elo:.0f}{f' ({tier})' if tier else ''}")

            def add(label: str, key: str) -> None:
                val = ev.get(key)
                if val:
                    lines.append(f"    {label}: {val}")

            add("Camino en el Mundial", f"{side}_wc_path")
            add("Forma (últimos 5, todos los internacionales)", f"{side}_form")
            add("Goles", f"{side}_goal_trend")
            add("Momentum", f"{side}_momentum")
            add("Goleadores", f"{side}_scorers")
            add("Tandas de penaltis (histórico)", f"{side}_pens")
            rest = ev.get(f"{side}_rest")
            if rest is not None:
                lines.append(f"    Descanso: {rest} día(s) desde su último partido")
            return "\n".join(lines)

        parts = [
            "DOSSIER DE LOS DOS EQUIPOS (evidencia real, no nombres):",
            dossier(home, "home"),
            "",
            dossier(away, "away"),
        ]

        h2h = ev.get("h2h")
        if h2h:
            parts.append(f"\nHistorial directo (H2H): {h2h}")

        gap = ev.get("elo_gap")
        higher = ev.get("elo_higher")
        if gap is not None and higher:
            parts.append(f"Diferencia de ELO: {gap:.0f} a favor de {higher}.")

        fav = ev.get("favorite")
        fav_prob = ev.get("fav_prob")
        if fav and fav_prob is not None:
            draw = ev.get("draw_prob")
            und = ev.get("underdog")
            und_prob = ev.get("und_prob")
            model = f"Baseline del modelo (1X2 a 90'): favorito {fav} {fav_prob*100:.0f}%"
            if draw is not None:
                model += f" · empate {draw*100:.0f}%"
            if und and und_prob is not None:
                model += f" · {und} {und_prob*100:.0f}%"
            parts.append(model + ".")

        return "\n".join(parts) + "\n"

    def _specialist_prompt(self, key: str, home: str, away: str, round_label: str, ev: dict) -> str:
        name, specialty = PANEL[key]
        focus = _SPECIALTY_FOCUS[key]
        contract = OUTPUT_CONTRACT.format(
            agent=name,
            specialty=specialty,
            home=home,
            away=away,
            marcador120='{"equipo_local": <int>, "equipo_visitante": <int>}',
            penaltis='{"equipo_local": <int>, "equipo_visitante": <int>}',
        )
        return f"""Eres el especialista "{name}" ({specialty}) en un panel de análisis de
{round_label} (eliminación directa) del Mundial 2026.

CRUCE: {home} (local) vs {away} (visitante) — {round_label}, gana o queda fuera.

{self._evidence_block(home, away, ev)}
{SHARED_RULES}

TU LENTE ({name}):
{focus}

Razona de forma INDEPENDIENTE desde tu especialidad; no imites al favorito por inercia
ni fuerces variedad artificial. Debes decidir 90', prórroga y/o penales, y el equipo
que AVANZA.
{contract}
"""

    def _consensus_prompt(self, home: str, away: str, round_label: str, ev: dict, panel: list[dict]) -> str:
        lines = []
        for p in panel:
            fase = p.get("fase_de_definicion", "?")
            clasif = p.get("equipo_clasificado", "?")
            m90 = p.get("marcador_90_minutos", {})
            lines.append(
                f"  - {p.get('agente')}: avanza {clasif} (fase {fase}); "
                f"90' {m90.get('equipo_local','?')}-{m90.get('equipo_visitante','?')}; "
                f"convicción {p.get('conviccion','?')}. {p.get('explicacion','')}"
            )
        panel_block = "\n".join(lines) if lines else "  (sin votos válidos del panel)"
        contract = OUTPUT_CONTRACT.format(
            agent="Consenso",
            specialty="veredicto reconciliado del panel",
            home=home,
            away=away,
            marcador120='{"equipo_local": <int>, "equipo_visitante": <int>}',
            penaltis='{"equipo_local": <int>, "equipo_visitante": <int>}',
        )
        return f"""Eres el ÁRBITRO DE CONSENSO del panel de {round_label} (eliminación directa).

CRUCE: {home} (local) vs {away} (visitante).

{self._evidence_block(home, away, ev)}
VOTOS DEL PANEL:
{panel_block}
{SHARED_RULES}

Pondera los 4 votos según su solidez (no promedies a ciegas). Entrega el veredicto
final de la llave: marcador a 90', si hay prórroga/penales, y el equipo que AVANZA.
{contract}
"""

    # ── Orquestación ────────────────────────────────────────────────────────
    def analyze(self, home: str, away: str, round_label: str, evidence: dict) -> dict:
        """Corre el panel completo (4 especialistas + consenso) para un cruce."""
        panel: list[dict] = []
        for key in PANEL:
            name = PANEL[key][0]
            logger.info("  [%s] razonando %s vs %s...", name, home, away)
            raw = self._call(self._specialist_prompt(key, home, away, round_label, evidence))
            parsed = self.parse_verdict(raw, home, away, fallback_agent=name)
            parsed["_analysis"] = raw.split("RESULTADO_JSON:")[0].strip()
            panel.append(parsed)

        logger.info("  [Consenso] reconciliando panel de %s vs %s...", home, away)
        raw_c = self._call(self._consensus_prompt(home, away, round_label, evidence, panel), max_tokens=4000)
        consensus = self.parse_verdict(raw_c, home, away, fallback_agent="Consenso")
        consensus["_analysis"] = raw_c.split("RESULTADO_JSON:")[0].strip()

        fav = evidence.get("favorite")
        fav_prob = evidence.get("fav_prob")
        return {
            "match": f"{home} vs {away}",
            "home": home,
            "away": away,
            "round": round_label,
            "model": {"favorite": fav, "fav_prob": round(fav_prob, 4) if fav_prob is not None else None},
            "panel": panel,
            "consensus": consensus,
        }

    # ── Parsing + validación ────────────────────────────────────────────────
    @classmethod
    def parse_verdict(cls, text: str, home: str, away: str, fallback_agent: str = "?") -> dict:
        """Extrae el bloque RESULTADO_JSON y lo valida/corrige. Nunca lanza."""
        m = re.search(r"RESULTADO_JSON:\s*(\{.*\})\s*$", (text or "").strip(), re.DOTALL)
        if not m:
            return cls._invalid(fallback_agent, home, away, reason="sin RESULTADO_JSON")
        try:
            data = json.loads(m.group(1))
        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("JSON inválido del %s: %s", fallback_agent, e)
            return cls._invalid(fallback_agent, home, away, reason="JSON inválido")
        return cls._validate(data, home, away, fallback_agent)

    @staticmethod
    def _team_from_side(side: str, home: str, away: str) -> str:
        return home if side == "home" else away

    @classmethod
    def _match_team(cls, name, home: str, away: str) -> Optional[str]:
        """Devuelve el nombre canónico (home/away) que corresponde a `name`, o None."""
        if not isinstance(name, str):
            return None
        n = name.strip().casefold()
        if n == home.casefold():
            return home
        if n == away.casefold():
            return away
        # match laxo por substring (por si el LLM abrevia)
        if n and n in home.casefold():
            return home
        if n and n in away.casefold():
            return away
        return None

    @classmethod
    def _validate(cls, data: dict, home: str, away: str, fallback_agent: str) -> dict:
        """Coacciona coherencia 90'↔prórroga↔penales↔clasificado. Nunca deja empate final."""
        agent = data.get("agente") or fallback_agent

        def _score(obj) -> Optional[tuple]:
            if not isinstance(obj, dict):
                return None
            try:
                return int(obj["equipo_local"]), int(obj["equipo_visitante"])
            except (KeyError, ValueError, TypeError):
                return None

        s90 = _score(data.get("marcador_90_minutos"))
        if s90 is None:
            return cls._invalid(agent, home, away, reason="marcador 90' ausente/ilegible")
        h90, a90 = s90

        conviccion = str(data.get("conviccion", "media")).lower()
        if conviccion not in VALID_CONVICTIONS:
            conviccion = "media"
        explicacion = str(data.get("explicacion", ""))[:400]

        out = {
            "agente": agent,
            "especialidad": data.get("especialidad", ""),
            "marcador_90_minutos": {"equipo_local": h90, "equipo_visitante": a90},
            "habra_tiempo_extra": False,
            "marcador_120_minutos": None,
            "habra_penaltis": False,
            "resultado_penaltis": None,
            "equipo_clasificado": None,
            "fase_de_definicion": "90_minutos",
            "conviccion": conviccion,
            "explicacion": explicacion,
            "valido": True,
        }

        # Caso 1: ganador en 90'.
        if h90 != a90:
            out["equipo_clasificado"] = home if h90 > a90 else away
            out["predicted_winner"] = "home" if h90 > a90 else "away"
            return out

        # Empate en 90' → prórroga obligatoria.
        out["habra_tiempo_extra"] = True
        s120 = _score(data.get("marcador_120_minutos"))

        # Caso 2: ganador en la prórroga.
        if s120 is not None and s120[0] != s120[1]:
            h120, a120 = s120
            out["marcador_120_minutos"] = {"equipo_local": h120, "equipo_visitante": a120}
            out["fase_de_definicion"] = "tiempo_extra"
            out["equipo_clasificado"] = home if h120 > a120 else away
            out["predicted_winner"] = "home" if h120 > a120 else "away"
            return out

        # Caso 3: sigue empatado tras 120' → penales.
        if s120 is not None:
            out["marcador_120_minutos"] = {"equipo_local": s120[0], "equipo_visitante": s120[1]}
        else:
            # El LLM dijo empate en 90' pero no dio 120'; asumimos que el empate se sostuvo.
            out["marcador_120_minutos"] = {"equipo_local": h90, "equipo_visitante": a90}
        out["habra_penaltis"] = True
        out["fase_de_definicion"] = "penaltis"
        pen = _score(data.get("resultado_penaltis"))
        if pen is not None and pen[0] != pen[1]:
            out["resultado_penaltis"] = {"equipo_local": pen[0], "equipo_visitante": pen[1]}
            out["equipo_clasificado"] = home if pen[0] > pen[1] else away
            out["predicted_winner"] = "home" if pen[0] > pen[1] else "away"
            return out

        # Penales sin ganador legible: usar el clasificado nombrado por el LLM y
        # sintetizar una tanda coherente (4-3). Si tampoco nombró clasificado,
        # marcar inválido (no inventamos un ganador de tanda de la nada).
        named = cls._match_team(data.get("equipo_clasificado"), home, away)
        if named is not None:
            out["resultado_penaltis"] = (
                {"equipo_local": 4, "equipo_visitante": 3}
                if named == home
                else {"equipo_local": 3, "equipo_visitante": 4}
            )
            out["equipo_clasificado"] = named
            out["predicted_winner"] = "home" if named == home else "away"
            return out
        return cls._invalid(agent, home, away, reason="penales sin ganador definido", partial=out)

    @staticmethod
    def _invalid(agent: str, home: str, away: str, reason: str, partial: Optional[dict] = None) -> dict:
        base = partial or {
            "agente": agent,
            "especialidad": "",
            "marcador_90_minutos": None,
            "habra_tiempo_extra": None,
            "marcador_120_minutos": None,
            "habra_penaltis": None,
            "resultado_penaltis": None,
            "conviccion": "baja",
            "explicacion": "",
        }
        base["agente"] = agent
        base["equipo_clasificado"] = None
        base["predicted_winner"] = None
        base["fase_de_definicion"] = base.get("fase_de_definicion", "90_minutos")
        base["valido"] = False
        base["error"] = reason
        logger.warning("Veredicto inválido del %s (%s vs %s): %s", agent, home, away, reason)
        return base


# Enfoque de cada especialista (inyectado en su prompt).
_SPECIALTY_FOCUS = {
    "group_analyst": (
        "Rendimiento en fase de grupos y en las eliminatorias ya jugadas: posición final,\n"
        "puntos, GF/GA, calidad de los rivales superados y regularidad. Proyecta cómo esa\n"
        "regularidad se sostiene (o no) en un partido de 120'+ contra este rival concreto."
    ),
    "tactical_scout": (
        "Formaciones, presión, transiciones, defensa del área, balón parado y duelos.\n"
        "Indica qué equipo gana la partida de ajedrez si el partido se alarga: quién tiene\n"
        "mejores cambios para la prórroga y quién sufre en los últimos 30 minutos."
    ),
    "sentiment_reader": (
        "Confianza, momentum, presión psicológica, reacción tras recibir un gol y temple\n"
        "para sostener una tanda de penales. No te bases en popularidad: usa los resultados\n"
        "reales del torneo como señal emocional."
    ),
    "definitions_specialist": (
        "ESPECIALISTA EN DEFINICIONES: tu foco es exactamente lo que decide estas rondas.\n"
        "Evalúa profundidad de banca y frescura física para la prórroga, historial y temple\n"
        "en tandas de penales, nivel de los porteros bajo presión y qué técnico protege el\n"
        "empate para forzar los penales. Eres quien más peso da a prórroga/penales cuando\n"
        "el cruce está parejo — pero no mandes todo a penales por defecto."
    ),
}
