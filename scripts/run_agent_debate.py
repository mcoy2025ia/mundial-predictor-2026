"""Script para ejecutar Agent Debate para partidos especificos.

Acumula resultados en data/processed/agent_debate_results.json (no sobrescribe):
- Si un partido ya tiene debate guardado (sin error), se omite salvo --force.
- Nuevos partidos se agregan al array existente.
- Cada corrida deduplica el archivo completo: si hay entradas duplicadas o de
  error viejas para un partido que ya tiene un resultado bueno, se descartan.

Uso:
    python scripts/run_agent_debate.py "Mexico" "South Korea" "Scotland" "Morocco"
    python scripts/run_agent_debate.py --force "Mexico" "South Korea"
"""

import json
import sys
import os
import argparse
from pathlib import Path

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
    return []


def pair_key(home: str, away: str) -> str:
    return f"{normalize_team_name(home)}|{normalize_team_name(away)}"


def pair_key_from_entry(r: dict) -> str:
    """Deriva la clave del partido desde 'context' (si existe) o desde el string 'match'."""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("teams", nargs="*", help="Pares de equipos: HOME AWAY HOME AWAY ...")
    parser.add_argument("--force", action="store_true", help="Re-ejecutar aunque ya exista debate guardado")
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

    system = AgentDebateSystem()
    new_results = []

    for home, away in matches:
        if not args.force and already_debated(existing, home, away):
            print(f"[SKIP] {home} vs {away} ya tiene debate guardado (usa --force para repetir)")
            continue

        try:
            result = system.predict_match(home, away)
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
