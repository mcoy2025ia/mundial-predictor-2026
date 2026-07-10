"""Exporta el bracket de eliminatorias para el frontend.

Combina la resolución del bracket (src/bracket.resolve_bracket) con las
predicciones del modelo (live_predictions.json) y produce
frontend/public/data/knockout_bracket.json con TODAS las rondas:

  Round of 32 → equipos reales + probabilidades del modelo (ya determinable)
  Round of 16 → octavos; equipos "por definir" con etiquetas de alimentador
                (p.ej. "South Africa / Canada" = ganador del #73)
  Quarter-final / Semi-final / Final → estructura del bracket

Cada ronda se etiqueta en español para la UI. Se ejecuta dentro del ciclo de
despliegue (después de predict_live.py).
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.bracket import (
    load_fixture_raw, resolve_bracket, _norm as bnorm,
)

OUT = ROOT / "frontend" / "public" / "data" / "knockout_bracket.json"
LIVE_PRED = ROOT / "frontend" / "public" / "data" / "live_predictions.json"
LIVE_RESULTS = ROOT / "data" / "external" / "wc2026_live_results.csv"

# Nombre de ronda (fixture) → etiqueta UI en español
ROUND_ES = {
    "Round of 32": "16avos de final",
    "Round of 16": "Octavos de final",
    "Quarter-final": "Cuartos de final",
    "Semi-final": "Semifinal",
    "Match for third place": "Tercer puesto",
    "Final": "Final",
}
ROUND_ORDER = ["Round of 32", "Round of 16", "Quarter-final", "Semi-final", "Match for third place", "Final"]

_RE_WL = re.compile(r"^([WL])(\d+)$")


def _load_live_preds() -> dict[frozenset, dict]:
    if not LIVE_PRED.exists():
        return {}
    data = json.loads(LIVE_PRED.read_text(encoding="utf-8"))
    preds = data if isinstance(data, list) else data.get("predictions", [])
    return {frozenset({bnorm(p["home_team"]), bnorm(p["away_team"])}): p for p in preds}


def _load_results(df: pd.DataFrame) -> dict[frozenset, dict]:
    """{frozenset(teams): {home, away, hs, as}} de los partidos ya jugados."""
    out: dict[frozenset, dict] = {}
    for _, r in df.iterrows():
        if pd.isna(r.get("home_score")) or pd.isna(r.get("away_score")):
            continue
        h, a = bnorm(str(r["home_team"])), bnorm(str(r["away_team"]))
        out[frozenset({h, a})] = {
            "home": h, "away": a,
            "home_score": int(r["home_score"]), "away_score": int(r["away_score"]),
        }
    return out


def _feeder_label(token: str, resolved: dict) -> str:
    """Etiqueta legible para un alimentador no resuelto (p.ej. 'W73').

    Si el partido alimentador (#73) ya tiene equipos, devuelve 'A / B'
    (uno de los dos avanza). Si no, 'Ganador 73' / 'Perdedor 73'.
    """
    m = _RE_WL.match(token)
    if not m:
        return token
    kind, num = m.group(1), int(m.group(2))
    feed = resolved.get(num)
    if feed and feed.get("home") and feed.get("away"):
        return f"{feed['home']} / {feed['away']}"
    return ("Ganador" if kind == "W" else "Perdedor") + f" #{num}"


def main() -> None:
    fixture = load_fixture_raw()
    df = pd.read_csv(LIVE_RESULTS) if LIVE_RESULTS.exists() else pd.DataFrame(
        columns=["home_team", "away_team", "home_score", "away_score"]
    )
    resolved = resolve_bracket(fixture, df)
    live_preds = _load_live_preds()
    results = _load_results(df)

    # Mapa num → entrada cruda del fixture (para alimentadores y placeholders)
    raw_by_num = {m.get("num"): m for m in fixture.get("matches", []) if not m.get("group")}

    rounds: dict[str, list] = {r: [] for r in ROUND_ORDER}

    for num in sorted(resolved):
        slot = resolved[num]
        rnd = slot["round"]
        if rnd not in rounds:
            continue
        raw = raw_by_num.get(num, {})

        home, away = slot["home"], slot["away"]
        # Etiquetas para equipos no resueltos (octavos en adelante)
        home_label = home or _feeder_label(raw.get("team1", ""), resolved)
        away_label = away or _feeder_label(raw.get("team2", ""), resolved)

        entry = {
            "num": num,
            "round": rnd,
            "round_es": ROUND_ES.get(rnd, rnd),
            "date": slot["date"],
            "time": slot["time"],
            "ground": slot["ground"],
            "home": home,
            "away": away,
            "home_label": home_label,
            "away_label": away_label,
            "resolved": slot["resolved"],
        }

        # Adjuntar predicción del modelo si el cruce está determinado
        if home and away:
            key = frozenset({bnorm(home), bnorm(away)})
            pred = live_preds.get(key)
            if pred:
                entry["pred"] = {
                    "p_home": pred.get("p_home"),
                    "p_draw": pred.get("p_draw"),
                    "p_away": pred.get("p_away"),
                    "top_scorelines": pred.get("top_scorelines", [])[:3],
                }
            # Resultado real si ya se jugó — orientado a home/away de esta entrada
            res = results.get(key)
            if res:
                same = bnorm(home) == res["home"]
                hs = res["home_score"] if same else res["away_score"]
                as_ = res["away_score"] if same else res["home_score"]
                entry["result"] = {
                    "home_score": hs,
                    "away_score": as_,
                    "winner": "home" if hs > as_ else ("away" if as_ > hs else "draw"),
                    "played": True,
                }

        rounds[rnd].append(entry)

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "round_order": ROUND_ORDER,
        "round_labels": ROUND_ES,
        "rounds": rounds,
        "counts": {r: len(v) for r, v in rounds.items()},
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_resolved = sum(1 for v in rounds.values() for e in v if e["resolved"])
    print(f"[OK] knockout_bracket.json -> {sum(len(v) for v in rounds.values())} cruces "
          f"({n_resolved} con equipos definidos). {OUT}")
    for r in ROUND_ORDER:
        print(f"   {ROUND_ES.get(r, r):18} {len(rounds[r])} cruces")


if __name__ == "__main__":
    main()
