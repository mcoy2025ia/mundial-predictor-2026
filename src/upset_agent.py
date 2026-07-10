"""Cazador de Sorpresas — agente de batacazos para la fase de eliminatorias.

Cuarto punto de vista, separado del debate de 3 agentes y del ensemble ML: un
analista que se especializa en construir el caso del equipo MENOS favorito
(underdog) en cada cruce de eliminación directa. No es contrarianismo aleatorio
— solo defiende la sorpresa cuando hay evidencia concreta (grietas del favorito,
armas del underdog, mayor varianza del partido único, prórroga/penales).

Toma como baseline objetivo la probabilidad del modelo (live_predictions.json)
para saber quién es el favorito, y razona con la campaña real de grupos de cada
equipo (vía src.bracket). Escribe data/processed/upset_predictions.json.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_URL = "https://api.deepseek.com/chat/completions"

LIVE_PRED_PATH = ROOT / "data" / "processed" / "live_predictions.json"
LIVE_PRED_FRONTEND = ROOT / "frontend" / "public" / "data" / "live_predictions.json"
OUT_PATH = ROOT / "data" / "processed" / "upset_predictions.json"
OUT_FRONTEND = ROOT / "frontend" / "public" / "data" / "upset_predictions.json"

# Umbral de plausibilidad a partir del cual el agente "se la juega" por la sorpresa.
UPSET_PICK_THRESHOLD = 0.35


class UpsetHunter:
    """Agente que evalúa y defiende el escenario de batacazo de cada cruce."""

    def __init__(self) -> None:
        self.client = httpx.Client(timeout=90)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "UpsetHunter":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ── LLM ────────────────────────────────────────────────────────────────
    def _call_deepseek(self, prompt: str, max_tokens: int = 2200) -> str:
        """Llama a deepseek-reasoner; cae a deepseek-chat si el contenido viene vacío."""
        for model in ("deepseek-reasoner", "deepseek-chat"):
            resp = self.client.post(
                DEEPSEEK_URL,
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 1.0 if model == "deepseek-reasoner" else 0.8,
                    "max_tokens": max_tokens,
                },
                headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}"},
            )
            if resp.status_code != 200:
                raise RuntimeError(f"DeepSeek API error ({model}): {resp.text[:300]}")
            content = resp.json()["choices"][0]["message"]["content"]
            if content and content.strip():
                return content
            logger.warning("%s devolvió contenido vacío; reintentando con fallback", model)
        return ""

    # ── Evidencia ──────────────────────────────────────────────────────────
    @staticmethod
    def _campaign_block(team: str, row: dict, qual_label: str, matches: list[str]) -> str:
        results = "\n".join(f"    {m}" for m in matches) or "    (sin datos)"
        return (
            f"{team} — {qual_label}: {row['pts']} pts, GD {row['gd']:+d}, "
            f"GF {row['gf']} / GA {row['ga']}\n  Partidos de grupo:\n{results}"
        )

    def analyze(
        self,
        home: str,
        away: str,
        favorite: str,
        underdog: str,
        fav_prob: float,
        round_label: str,
        evidence: dict,
    ) -> dict:
        """Genera el análisis de sorpresa para un cruce."""
        home_block = self._campaign_block(
            home, evidence["home_row"], evidence["home_qual"], evidence["home_matches"]
        )
        away_block = self._campaign_block(
            away, evidence["away_row"], evidence["away_qual"], evidence["away_matches"]
        )

        prompt = f"""
Eres el CAZADOR DE SORPRESAS: un analista de fútbol que se especializa en detectar
BATACAZOS REALES en eliminatorias. NO eres contrarianista: solo defiendes la sorpresa
cuando hay evidencia concreta. Si el favorito es abrumadoramente superior, lo admites
y pones una plausibilidad baja. Tu lente es siempre el equipo MENOS favorito.

**CRUCE ({round_label}, eliminación directa — gana o queda fuera):** {home} vs {away}
**Favorito según el modelo:** {favorite} ({fav_prob*100:.0f}% de ganar)
**Underdog (tu cliente):** {underdog}

**CAMPAÑA DE GRUPOS (evidencia real):**
{home_block}

{away_block}

**TU ROL:** eres el ABOGADO del batacazo. Tu PREDICCIÓN siempre es el escenario de
sorpresa (gana {underdog}); no cambias tu pick al favorito. Lo que ajustas es la
PLAUSIBILIDAD honesta (0-1): alta si el caso es sólido, baja si es un palo lejano.
Es tu única función — el favorito ya tiene quien lo defienda.

**CONSTRUYE EL CASO DE {underdog} CON RIGOR:**

1. **GRIETAS DEL FAVORITO {favorite}:** ¿Dónde es vulnerable? (arranque dubitativo,
   goles encajados, dependencia de una figura, posible exceso de confianza, fatiga).
2. **ARMAS DE {underdog}:** ¿Qué hace bien? (orden defensivo, pegada a la contra,
   balón parado, disciplina táctica, resultados de mérito en el grupo).
3. **FACTOR ELIMINATORIA:** partido único = más varianza; prórroga y penales nivelan
   al favorito. ¿El underdog sabe competir 120' y aguantar?
4. **PLAUSIBILIDAD HONESTA (0-1):** qué tan real es que {underdog} gane. Sé sincero,
   pero recuerda que la varianza del mata-mata casi nunca deja a un favorito por
   debajo del 25-30% de riesgo real.

El marcador (scoreline) debe ser el del BATACAZO: gana {underdog}.
Escribe 4-6 líneas de análisis y TERMINA EXACTO con esta línea (sin texto después):
RESULTADO_JSON: {{"underdog": "{underdog}", "upset_plausibility": <float 0-1>, "predicted_winner": "{underdog}", "scoreline": "<marcador donde gana {underdog}, formato H-A>", "key_factors": ["<factor 1>", "<factor 2>", "<factor 3>"], "one_liner": "<frase de cierre, máx 18 palabras>"}}
"""
        text = self._call_deepseek(prompt)
        parsed = self._parse(text)
        # El pick del Cazador es, por definición, el underdog (es su rol).
        parsed["predicted_winner"] = underdog
        return {
            "match": f"{home} vs {away}",
            "home": home,
            "away": away,
            "favorite": favorite,
            "underdog": underdog,
            "round": round_label,
            "model_fav_prob": round(fav_prob, 4),
            "analysis": text.split("RESULTADO_JSON:")[0].strip(),
            **parsed,
        }

    @staticmethod
    def _parse(text: str) -> dict:
        """Extrae el bloque RESULTADO_JSON; tolera fallos del LLM."""
        m = re.search(r"RESULTADO_JSON:\s*(\{.*\})\s*$", text.strip(), re.DOTALL)
        default = {
            "upset_plausibility": 0.0,
            "predicted_winner": None,
            "scoreline": None,
            "key_factors": [],
            "one_liner": "",
            "upset_pick": False,
        }
        if not m:
            return default
        try:
            data = json.loads(m.group(1))
            plaus = float(data.get("upset_plausibility", 0.0))
            return {
                "upset_plausibility": round(plaus, 3),
                "predicted_winner": data.get("predicted_winner"),
                "scoreline": data.get("scoreline"),
                "key_factors": data.get("key_factors", [])[:4],
                "one_liner": str(data.get("one_liner", ""))[:160],
                "upset_pick": plaus >= UPSET_PICK_THRESHOLD,
            }
        except (ValueError, KeyError, json.JSONDecodeError) as e:
            logger.warning("No se pudo parsear RESULTADO_JSON del cazador: %s", e)
            return default
