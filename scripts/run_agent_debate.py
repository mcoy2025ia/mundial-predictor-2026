"""Script para ejecutar Agent Debate para partidos especificos.

Acumula resultados en data/processed/agent_debate_results.json (no sobrescribe):
- Si un partido ya tiene debate guardado (sin error), se omite salvo --force.
- Nuevos partidos se agregan al array existente.
- Cada corrida deduplica el archivo completo: si hay entradas duplicadas o de
  error viejas para un partido que ya tiene un resultado bueno, se descartan.

Uso:
    python scripts/run_agent_debate.py "Mexico" "South Korea" "Scotland" "Morocco"
    python scripts/run_agent_debate.py --force "Mexico" "South Korea"

Backfill de partidos ya jugados (--cutoff YYYY-MM-DD):
    python scripts/run_agent_debate.py --force --cutoff 2026-07-04 "Canada" "Morocco"

    El contexto se arma solo con resultados de fecha ANTERIOR al cutoff, así los
    agentes no ven el resultado del partido debatido ni nada posterior (el LLM no
    conoce el WC 2026 por entrenamiento; el CSV es el único canal de fuga). El
    cutoff correcto es la fecha del partido. Cada entrada backfilleada queda
    marcada con "backfill_cutoff" para auditoría.
"""

import json
import sys
import os
import argparse
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Cargar variables de entorno desde .env.local
env_file = ROOT / "frontend" / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)

from src.agent_debate import AgentDebateSystem, normalize_team_name

OUTPUT_FILE = ROOT / "data/processed/agent_debate_results.json"
# data/processed/ esta gitignored: en CI cada corrida arranca de un checkout
# limpio y este archivo no existe. El JSON publicado en frontend/public/data/
# SI esta en git y refleja el historial acumulado real entre corridas, asi
# que sirve de semilla cuando no hay copia local en data/processed/.
PUBLISHED_FILE = ROOT / "frontend/public/data/agent_debate_results.json"
LIVE_PREDS_CANDIDATES = [
    ROOT / "data/processed/live_predictions.json",
    ROOT / "frontend/public/data/live_predictions.json",
]
GROUP_MATCHES_FILE = ROOT / "frontend/public/data/group_matches.json"

DEFAULT_MATCHES = [
    ("Mexico", "South Korea"),
    ("Scotland", "Morocco"),
    ("USA", "Australia"),
]


def safe_print(text: str) -> None:
    """Imprime sin crashear en consolas Windows que no soportan emojis (cp1252)."""
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode("ascii"))


def load_existing() -> list[dict]:
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE, encoding="utf-8") as f:
            return json.load(f)
    if PUBLISHED_FILE.exists():
        with open(PUBLISHED_FILE, encoding="utf-8") as f:
            return json.load(f)
    return []


def pair_key(home: str, away: str) -> str:
    return f"{normalize_team_name(home)}|{normalize_team_name(away)}"


def pair_key_from_entry(r: dict) -> str:
    """Deriva la clave del partido desde 'context' (si existe) o desde el string 'match'."""
    h_top, a_top = r.get("home"), r.get("away")
    if h_top and a_top:
        return pair_key(h_top, a_top)
    ctx = r.get("context", {})
    h = ctx.get("home_team", {}).get("name", "")
    a = ctx.get("away_team", {}).get("name", "")
    if h and a:
        return pair_key(h, a)
    match_str = r.get("match", "")
    if " vs " in match_str:
        h, a = match_str.split(" vs ", 1)
        return pair_key(h.strip(), a.strip())
    return match_str


def dedup(entries: list[dict]) -> list[dict]:
    """Por cada partido, conserva un único resultado: prefiere el más reciente sin error."""
    best: dict[str, dict] = {}
    for r in entries:
        key = pair_key_from_entry(r)
        if not key:
            continue
        current = best.get(key)
        if current is None:
            best[key] = r
        elif "error" in current and "error" not in r:
            best[key] = r  # un resultado bueno reemplaza un error viejo
        elif "error" not in current and "error" not in r:
            best[key] = r  # entre dos buenos, gana el más reciente (último visto)
        elif "error" in current and "error" in r:
            best[key] = r  # entre dos errores, gana el más reciente
    return list(best.values())


def already_debated(existing: list[dict], home: str, away: str) -> bool:
    target = pair_key(home, away)
    for r in existing:
        if "error" in r:
            continue
        if pair_key_from_entry(r) == target:
            return True
    return False


def _load_live_predictions() -> list[dict]:
    for path in LIVE_PREDS_CANDIDATES:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            preds = data.get("predictions", [])
        else:
            preds = data
        if isinstance(preds, list):
            return [p for p in preds if isinstance(p, dict)]
    return []


def _find_fixture_prediction(home: str, away: str, live_predictions: list[dict]) -> dict | None:
    target = pair_key(home, away)
    for pred in live_predictions:
        pred_home = pred.get("home_team")
        pred_away = pred.get("away_team")
        if pred_home and pred_away and pair_key(pred_home, pred_away) == target:
            return pred
    if GROUP_MATCHES_FILE.exists():
        try:
            group_matches = json.loads(GROUP_MATCHES_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            group_matches = {}
        for group, matches in group_matches.items():
            for match in matches:
                team1 = match.get("team1")
                team2 = match.get("team2")
                if team1 and team2 and pair_key(team1, team2) == target:
                    return {
                        "home_team": team1,
                        "away_team": team2,
                        "kickoff": match.get("date"),
                        "stage": "group",
                        "round": match.get("round"),
                        "group": group,
                    }
    return None


def _parse_dt(value: str | None):
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def annotate_audit(result: dict, home: str, away: str, cutoff: str | None, live_predictions: list[dict]) -> dict:
    """Agrega metadata para distinguir predicciones forward-only de backfills."""
    generated_at = datetime.now(timezone.utc)
    pred = _find_fixture_prediction(home, away, live_predictions)
    kickoff_raw = pred.get("kickoff") if pred else None
    kickoff_at = _parse_dt(kickoff_raw)
    was_pre_match = bool(kickoff_at and generated_at < kickoff_at)

    result["generated_at"] = generated_at.isoformat()
    result["audit"] = {
        "generated_at": result["generated_at"],
        "execution_mode": "backfill" if cutoff else "forward",
        "backfill_cutoff": cutoff,
        "kickoff": kickoff_raw,
        "stage": pred.get("stage") if pred else None,
        "round": pred.get("round") if pred else result.get("context", {}).get("round"),
        "group": pred.get("group") if pred else result.get("context", {}).get("group"),
        "was_pre_match": was_pre_match,
        "source": "scripts/run_agent_debate.py",
    }
    if cutoff:
        # Campo historico conservado para compatibilidad con reportes/manuales.
        result["backfill_cutoff"] = cutoff
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("teams", nargs="*", help="Pares de equipos: HOME AWAY HOME AWAY ...")
    parser.add_argument("--force", action="store_true", help="Re-ejecutar aunque ya exista debate guardado")
    parser.add_argument("--cutoff", metavar="YYYY-MM-DD", default=None,
                        help="Backfill: armar contexto solo con resultados anteriores a esta fecha (anti-leakage)")
    args = parser.parse_args()

    if args.teams:
        if len(args.teams) % 2 != 0:
            print("ERROR: se necesita un numero par de equipos (HOME AWAY HOME AWAY ...)")
            sys.exit(1)
        matches = [(args.teams[i], args.teams[i + 1]) for i in range(0, len(args.teams), 2)]
    else:
        matches = DEFAULT_MATCHES

    existing = dedup(load_existing())
    print(f"[INFO] {len(existing)} debate(s) ya guardados (tras dedup) en {OUTPUT_FILE.name}")

    system = AgentDebateSystem(cutoff_date=args.cutoff)
    live_predictions = _load_live_predictions()
    if args.cutoff:
        print(f"[INFO] Modo backfill: contexto limitado a resultados con fecha < {args.cutoff}")
    new_results = []

    for home, away in matches:
        if not args.force and already_debated(existing, home, away):
            print(f"[SKIP] {home} vs {away} ya tiene debate guardado (usa --force para repetir)")
            continue

        try:
            result = system.predict_match(home, away)
            result = annotate_audit(result, home, away, args.cutoff, live_predictions)
            new_results.append(result)

            safe_print("\n" + "=" * 100)
            safe_print(f"AGENT DEBATE: {home} vs {away}")
            safe_print("=" * 100)
            safe_print("\nCONSENSO FINAL:")
            safe_print(result["consensus"])
            print(f"\nTOP PREDICTION: {result.get('top_prediction')}")

        except Exception as e:
            print(f"ERROR en {home} vs {away}: {e}")
            new_results.append({"match": f"{home} vs {away}", "error": str(e)})

    system.close()

    if not new_results:
        print("\n[OK] Nada nuevo que ejecutar.")
        # Igual reescribimos el archivo si el dedup limpió algo del existente
        OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(existing, f, indent=2, ensure_ascii=False)
        return

    combined = dedup(existing + new_results)

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] {len(new_results)} debate(s) nuevo(s). Total acumulado: {len(combined)} en {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
