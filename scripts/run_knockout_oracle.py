"""Corre el Oráculo de Eliminatorias sobre los cruces de cuartos, semis y final.

Voz premium separada del debate de 3 agentes y del Cazador de Sorpresas: un panel
de 4 especialistas independientes + consenso (deepseek-reasoner, el modelo caro)
que razona la eliminatoria COMPLETA — 90' → prórroga → penales → quién avanza.

SOLO analiza cruces resueltos cuya ronda esté en ORACLE_ROUNDS (Quarter-final,
Semi-final, Final, Match for third place). Acumula en
data/processed/knockout_oracle_predictions.json (idempotente; --force para repetir)
y publica una copia en frontend/public/data/.

Uso:
    python scripts/run_knockout_oracle.py                    # todos los cruces QF/SF/Final resueltos
    python scripts/run_knockout_oracle.py "Spain" "Belgium"  # par(es) específico(s)
    python scripts/run_knockout_oracle.py --force "Spain" "Belgium"
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
logger = logging.getLogger("knockout_oracle")

from src.knockout_oracle import KnockoutOracle, ORACLE_ROUNDS
from src.bracket import (
    load_fixture_raw, group_membership, final_standings, resolve_bracket, _norm as bnorm,
)
from src.agents.match_intel import MatchIntel

RESULTS_CSV = ROOT / "data" / "raw" / "results.csv"
SHOOTOUTS_CSV = ROOT / "data" / "raw" / "shootouts.csv"
ELO_SNAPSHOT = ROOT / "data" / "processed" / "elo_current.json"

OUT_PATH = ROOT / "data" / "processed" / "knockout_oracle_predictions.json"
OUT_FRONTEND = ROOT / "frontend" / "public" / "data" / "knockout_oracle_predictions.json"
LIVE_PRED_CANDIDATES = [
    ROOT / "data" / "processed" / "live_predictions.json",
    ROOT / "frontend" / "public" / "data" / "live_predictions.json",
]


def safe_print(text: str) -> None:
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def _load_live_preds() -> dict[frozenset, dict]:
    for path in LIVE_PRED_CANDIDATES:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            preds = data if isinstance(data, list) else data.get("predictions", [])
            return {frozenset({bnorm(p["home_team"]), bnorm(p["away_team"])}): p for p in preds}
    return {}


def _qual_label(row: dict) -> str:
    return {1: "1º de grupo", 2: "2º de grupo", 3: "mejor tercero"}.get(row["pos"], f"{row['pos']}º")


def _is_played(df: pd.DataFrame, home_norm: str, away_norm: str) -> bool:
    """True si ese cruce exacto ya tiene resultado en el CSV (para omitirlo: forward-only)."""
    if df.empty:
        return False
    hn = df["home_team"].map(bnorm)
    an = df["away_team"].map(bnorm)
    mask = (
        ((hn == home_norm) & (an == away_norm)) | ((hn == away_norm) & (an == home_norm))
    ) & df["home_score"].notna() & df["away_score"].notna()
    return bool(mask.any())


def _oracle_pairs(resolved: dict) -> list[tuple[str, str, str]]:
    """(home, away, round_label) de cruces resueltos en rondas del Oráculo."""
    pairs = []
    for s in resolved.values():
        if s.get("resolved") and s.get("round") in ORACLE_ROUNDS:
            pairs.append((bnorm(s["home"]), bnorm(s["away"]), s["round"]))
    return pairs


# ── Enriquecimiento de evidencia (MatchIntel + ELO + tandas + descanso) ──────
def _build_intel() -> tuple[MatchIntel, pd.DataFrame, dict, pd.DataFrame]:
    """Construye MatchIntel una vez. Devuelve (intel, df_all, elo_snapshot, shootouts)."""
    df_all = pd.read_csv(RESULTS_CSV, parse_dates=["date"])
    df_wc26_played = df_all[
        (df_all.get("tournament") == "FIFA World Cup")
        & (df_all["date"].dt.year == 2026)
        & df_all["home_score"].notna()
    ].copy()
    elo_snapshot = {}
    if ELO_SNAPSHOT.exists():
        try:
            elo_snapshot = json.loads(ELO_SNAPSHOT.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            elo_snapshot = {}
    shootouts = pd.DataFrame()
    if SHOOTOUTS_CSV.exists():
        try:
            shootouts = pd.read_csv(SHOOTOUTS_CSV, parse_dates=["date"])
        except Exception:
            shootouts = pd.DataFrame()
    intel = MatchIntel(df_all, df_wc26_played, [], elo_snapshot)
    return intel, df_all, elo_snapshot, shootouts


def _shootout_record(shootouts: pd.DataFrame, team: str) -> str | None:
    """Historial de tandas de penaltis del equipo (crítico en eliminatorias)."""
    if shootouts.empty:
        return None
    sub = shootouts[(shootouts["home_team"] == team) | (shootouts["away_team"] == team)]
    if sub.empty:
        return None
    wins = int((sub["winner"] == team).sum())
    total = len(sub)
    recent = []
    for _, r in sub.sort_values("date").tail(3).iterrows():
        opp = r["away_team"] if r["home_team"] == team else r["home_team"]
        res = "ganó" if r["winner"] == team else "perdió"
        yr = str(r["date"])[:4]
        recent.append(f"{res} vs {opp} ({yr})")
    return f"{total} tandas: {wins}G-{total - wins}P. Recientes: {', '.join(recent)}"


def _rest_days(df_all: pd.DataFrame, team: str, as_of) -> int | None:
    """Días desde el último partido jugado del equipo (fatiga para la prórroga)."""
    mask = ((df_all["home_team"] == team) | (df_all["away_team"] == team)) & df_all["home_score"].notna()
    sub = df_all[mask & (df_all["date"] < pd.Timestamp(as_of))]
    if sub.empty:
        return None
    last = sub["date"].max()
    days = (pd.Timestamp(as_of) - last).days
    return days if 0 <= days <= 30 else None


def _build_evidence(intel, df_all, elo_snapshot, shootouts, home, away,
                    home_row, away_row, favorite, fav_prob, pred, as_of) -> dict:
    """Arma el dossier rico para un cruce (leak-free: as_of = fecha del partido)."""
    ev: dict = {
        "home_row": home_row, "away_row": away_row,
        "home_qual": _qual_label(home_row) if home_row else "?",
        "away_qual": _qual_label(away_row) if away_row else "?",
        "favorite": favorite, "fav_prob": fav_prob,
    }
    # Probabilidades 1X2 del modelo (empate + underdog)
    p_home = float(pred.get("p_home", 0.5)); p_away = float(pred.get("p_away", 0.5))
    ev["draw_prob"] = pred.get("p_draw")
    ev["underdog"] = away if favorite == home else home
    ev["und_prob"] = p_away if favorite == home else p_home

    for side, team in (("home", home), ("away", away)):
        ev[f"{side}_elo"] = elo_snapshot.get(team)
        ev[f"{side}_tier"] = intel._quality_label(team) or None
        ev[f"{side}_wc_path"] = intel.wc_results(team)
        ev[f"{side}_form"] = intel.form_summary(team, as_of)
        ev[f"{side}_goal_trend"] = intel.goal_trend(team, as_of)
        ev[f"{side}_momentum"] = intel.momentum(team, as_of)
        ev[f"{side}_scorers"] = intel.scorer_profile(team)
        ev[f"{side}_pens"] = _shootout_record(shootouts, team)
        ev[f"{side}_rest"] = _rest_days(df_all, team, as_of)

    # Historial directo
    ev["h2h"] = intel.h2h_summary(home, away, as_of)

    # Diferencia de ELO
    he, ae = ev.get("home_elo"), ev.get("away_elo")
    if he is not None and ae is not None:
        ev["elo_gap"] = abs(he - ae)
        ev["elo_higher"] = home if he >= ae else away
    return ev


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("teams", nargs="*", help="Pares HOME AWAY (vacío = todos los QF/SF/Final resueltos)")
    parser.add_argument("--force", action="store_true", help="Re-analizar aunque ya exista")
    parser.add_argument("--dry-run", action="store_true",
                        help="Imprime el contexto/prompt que se le daría al modelo SIN llamar a la API")
    args = parser.parse_args()

    fixture = load_fixture_raw()
    mem = group_membership(fixture)
    df = pd.read_csv(ROOT / "data/external/wc2026_live_results.csv")
    standings = final_standings(df, mem)
    resolved = resolve_bracket(fixture, df)
    live_preds = _load_live_preds()

    # Fecha programada de cada cruce (para el corte anti-leakage de forma/H2H)
    slot_by_key = {
        frozenset({bnorm(s["home"]), bnorm(s["away"])}): s
        for s in resolved.values() if s.get("resolved")
    }
    intel, df_all, elo_snapshot, shootouts = _build_intel()

    all_oracle = _oracle_pairs(resolved)

    if args.teams:
        if len(args.teams) % 2 != 0:
            print("ERROR: número impar de equipos")
            sys.exit(1)
        requested = [(bnorm(args.teams[i]), bnorm(args.teams[i + 1])) for i in range(0, len(args.teams), 2)]
        # Asociar cada par pedido con su ronda del bracket (si es de eliminatorias tardías)
        round_by_key = {frozenset({h, a}): rnd for h, a, rnd in all_oracle}
        pairs = []
        for h, a in requested:
            rnd = round_by_key.get(frozenset({h, a}))
            if rnd is None:
                print(f"[WARN] {h} vs {a} no es un cruce resuelto de QF/SF/Final; omito")
                continue
            pairs.append((h, a, rnd))
    else:
        pairs = all_oracle

    if not pairs:
        print("[OK] No hay cruces de QF/SF/Final resueltos para analizar todavía.")
        return

    # Cargar existentes (data/processed primero; si no, semilla publicada en frontend)
    existing = []
    for path in (OUT_PATH, OUT_FRONTEND):
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8")).get("matches", [])
            break
    done = {frozenset({bnorm(e["home"]), bnorm(e["away"])}) for e in existing if "error" not in e}

    oracle = KnockoutOracle()
    new_results = []
    for home, away, round_label in pairs:
        key = frozenset({home, away})
        if not args.force and not args.dry_run and key in done:
            print(f"[SKIP] {home} vs {away} ({round_label}) ya analizado")
            continue
        if _is_played(df, home, away):
            # Forward-only: el Oráculo predice ANTES del partido. Un cruce ya jugado
            # metería su propio resultado en la evidencia (fuga). No se backfillea.
            print(f"[SKIP] {home} vs {away} ({round_label}) ya se jugó — el Oráculo es forward-only")
            continue

        hg, ag = mem.get(home), mem.get(away)
        home_row = next((r for r in standings.get(hg, []) if r["team"] == home), {}) if hg else {}
        away_row = next((r for r in standings.get(ag, []) if r["team"] == away), {}) if ag else {}

        pred = live_preds.get(key, {})
        p_home = float(pred.get("p_home", 0.5))
        p_away = float(pred.get("p_away", 0.5))
        favorite, fav_prob = (home, p_home) if p_home >= p_away else (away, p_away)

        # Fecha del cruce → corte anti-leakage para forma/H2H (leak-free: el cruce no está jugado)
        slot = slot_by_key.get(key, {})
        slot_date = slot.get("date")
        as_of = pd.Timestamp(slot_date) if slot_date else pd.Timestamp.utcnow().tz_localize(None)

        evidence = _build_evidence(
            intel, df_all, elo_snapshot, shootouts, home, away,
            home_row, away_row, favorite, fav_prob, pred, as_of,
        )

        # Modo dry-run: mostrar el contexto/prompt sin gastar en la API.
        if args.dry_run:
            safe_print("\n" + "=" * 90)
            safe_print(f"CONTEXTO PARA EL ORÁCULO — {home} vs {away} ({round_label}, corte {as_of.date()})")
            safe_print("=" * 90)
            safe_print(oracle._evidence_block(home, away, evidence))
            safe_print(f"[dry-run] {5} llamadas a deepseek-reasoner NO ejecutadas para este cruce.")
            continue

        logger.info("Oráculo (%s): %s vs %s (favorito %s %.0f%%)", round_label, home, away, favorite, fav_prob * 100)
        try:
            res = oracle.analyze(home, away, round_label, evidence)
            res["generated_at"] = datetime.now(timezone.utc).isoformat()
            new_results.append(res)
            c = res["consensus"]
            safe_print(
                f"  → CONSENSO: avanza {c.get('equipo_clasificado')} "
                f"(fase {c.get('fase_de_definicion')}, convicción {c.get('conviccion')}) — {c.get('explicacion')}"
            )
        except Exception as e:
            print(f"ERROR en {home} vs {away}: {e}")
            new_results.append({"match": f"{home} vs {away}", "home": home, "away": away,
                                "round": round_label, "error": str(e)})

    oracle.close()

    if args.dry_run:
        safe_print("\n[dry-run] Solo contexto. No se llamó a la API ni se escribió ningún archivo.")
        return

    # Combinar (nuevos reemplazan viejos del mismo par)
    by_key = {frozenset({bnorm(e["home"]), bnorm(e["away"])}): e for e in existing}
    for r in new_results:
        by_key[frozenset({bnorm(r["home"]), bnorm(r["away"])})] = r
    combined = list(by_key.values())

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agent": "Oráculo de Eliminatorias",
        "rounds": sorted(ORACLE_ROUNDS),
        "panel": ["Group Analyst", "Tactical Scout", "Sentiment Reader", "Especialista en Definiciones", "Consenso"],
        "n": len(combined),
        "matches": combined,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    OUT_FRONTEND.parent.mkdir(parents=True, exist_ok=True)
    OUT_FRONTEND.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    n_ok = sum(1 for e in new_results if "error" not in e)
    safe_print(f"\n[OK] {n_ok} nuevo(s). Total {len(combined)} cruce(s) -> {OUT_PATH.name} (+ frontend)")


if __name__ == "__main__":
    main()
