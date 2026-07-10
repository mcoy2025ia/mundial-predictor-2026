"""Corre el Cazador de Sorpresas sobre los cruces de eliminatorias.

Para cada partido determinado del bracket: toma el favorito del modelo
(live_predictions.json) y construye el caso del underdog con la campaña real de
grupos. Acumula en data/processed/upset_predictions.json (idempotente; --force
para repetir) y exporta a frontend/public/data/.

Uso:
    python scripts/run_upset_agent.py                       # todos los cruces resueltos
    python scripts/run_upset_agent.py "Brazil" "Japan"      # pares específicos
    python scripts/run_upset_agent.py --force "Brazil" "Japan"
"""
import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Cargar variables de entorno desde .env.local
env_file = ROOT / "frontend" / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)s  %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("upset_agent")

from src.upset_agent import UpsetHunter, OUT_PATH, OUT_FRONTEND, LIVE_PRED_PATH, LIVE_PRED_FRONTEND
from src.bracket import (
    load_fixture_raw, group_membership, final_standings, resolve_bracket, _norm as bnorm,
)


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _load_live_preds() -> dict[frozenset, dict]:
    """{frozenset({home,away}): pred} desde live_predictions.json (proc o frontend)."""
    for path in (LIVE_PRED_PATH, LIVE_PRED_FRONTEND):
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            preds = data if isinstance(data, list) else data.get("predictions", [])
            return {frozenset({bnorm(p["home_team"]), bnorm(p["away_team"])}): p for p in preds}
    return {}


def _qual_label(row: dict) -> str:
    return {1: "1º de grupo", 2: "2º de grupo", 3: "mejor tercero"}.get(row["pos"], f"{row['pos']}º")


def _team_matches(df: pd.DataFrame, team_norm: str) -> list[str]:
    out = []
    if df.empty:
        return out
    sub = df[(df["home_team"].map(bnorm) == team_norm) | (df["away_team"].map(bnorm) == team_norm)]
    for _, r in sub.iterrows():
        if pd.isna(r["home_score"]) or pd.isna(r["away_score"]):
            continue
        out.append(f"{bnorm(str(r['home_team']))} {int(r['home_score'])}-{int(r['away_score'])} {bnorm(str(r['away_team']))}")
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("teams", nargs="*", help="Pares HOME AWAY HOME AWAY (vacío = todos los resueltos)")
    parser.add_argument("--force", action="store_true", help="Re-analizar aunque ya exista")
    args = parser.parse_args()

    fixture = load_fixture_raw()
    mem = group_membership(fixture)
    df = pd.read_csv(ROOT / "data/external/wc2026_live_results.csv")
    standings = final_standings(df, mem)
    resolved = resolve_bracket(fixture, df)
    live_preds = _load_live_preds()

    # Determinar la lista de cruces a analizar
    if args.teams:
        if len(args.teams) % 2 != 0:
            print("ERROR: número impar de equipos")
            sys.exit(1)
        pairs = [(bnorm(args.teams[i]), bnorm(args.teams[i + 1])) for i in range(0, len(args.teams), 2)]
    else:
        pairs = [
            (bnorm(s["home"]), bnorm(s["away"]))
            for s in resolved.values() if s.get("resolved")
        ]

    # Cargar existentes
    existing = []
    if OUT_PATH.exists():
        existing = json.loads(OUT_PATH.read_text(encoding="utf-8")).get("upsets", [])
    done = {frozenset({bnorm(e["home"]), bnorm(e["away"])}) for e in existing}

    hunter = UpsetHunter()
    new_results = []
    for home, away in pairs:
        key = frozenset({home, away})
        if not args.force and key in done:
            print(f"[SKIP] {home} vs {away} ya analizado")
            continue

        hg, ag = mem.get(home), mem.get(away)
        if not hg or not ag:
            print(f"[WARN] grupo desconocido para {home}/{away}; omito")
            continue

        home_row = next((r for r in standings.get(hg, []) if r["team"] == home), None)
        away_row = next((r for r in standings.get(ag, []) if r["team"] == away), None)
        if home_row is None or away_row is None:
            print(f"[WARN] sin standings para {home}/{away}; omito")
            continue

        # Favorito/underdog y prob del modelo
        pred = live_preds.get(key, {})
        p_home = float(pred.get("p_home", 0.5))
        p_away = float(pred.get("p_away", 0.5))
        if p_home >= p_away:
            favorite, underdog, fav_prob = home, away, p_home
        else:
            favorite, underdog, fav_prob = away, home, p_away

        # Etiqueta de ronda
        round_label = "Eliminatorias"
        for s in resolved.values():
            if s.get("resolved") and {bnorm(s["home"]), bnorm(s["away"])} == key:
                round_label = s["round"]
                break

        evidence = {
            "home_row": home_row, "away_row": away_row,
            "home_qual": _qual_label(home_row), "away_qual": _qual_label(away_row),
            "home_matches": _team_matches(df, home), "away_matches": _team_matches(df, away),
        }

        logger.info("Cazando sorpresa: %s vs %s (favorito %s %.0f%%)", home, away, favorite, fav_prob * 100)
        try:
            res = hunter.analyze(home, away, favorite, underdog, fav_prob, round_label, evidence)
            new_results.append(res)
            mark = "🚨 SORPRESA" if res.get("upset_pick") else "favorito firme"
            safe_print(f"  → {mark}: gana {res.get('predicted_winner')} {res.get('scoreline')} "
                       f"(plausibilidad {res.get('upset_plausibility')}) — {res.get('one_liner')}")
        except Exception as e:
            print(f"ERROR en {home} vs {away}: {e}")

    hunter.close()

    # Combinar (nuevos reemplazan viejos del mismo par)
    by_key = {frozenset({bnorm(e["home"]), bnorm(e["away"])}): e for e in existing}
    for r in new_results:
        by_key[frozenset({bnorm(r["home"]), bnorm(r["away"])})] = r
    combined = sorted(by_key.values(), key=lambda e: (-e.get("upset_plausibility", 0)))

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": "Cazador de Sorpresas",
        "pick_threshold": 0.35,
        "n": len(combined),
        "upsets": combined,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_FRONTEND.parent.mkdir(parents=True, exist_ok=True)
    OUT_FRONTEND.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_upsets = sum(1 for e in combined if e.get("upset_pick"))
    safe_print(f"\n[OK] {len(new_results)} nuevo(s). Total {len(combined)} cruces, "
               f"{n_upsets} marcados como SORPRESA viva. -> {OUT_PATH.name} (+ frontend)")


if __name__ == "__main__":
    main()
