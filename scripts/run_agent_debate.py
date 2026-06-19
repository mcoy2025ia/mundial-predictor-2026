"""Script para ejecutar Agent Debate para partidos específicos."""

import json
import sys
import os
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

from src.agent_debate import AgentDebateSystem


def main():
    # Partidos de mañana (19 de junio)
    # Usar nombres exactos del fixture
    matches = [
        ("Mexico", "South Korea"),
        ("Scotland", "Morocco"),
        ("USA", "Australia"),
    ]

    system = AgentDebateSystem()
    results = []

    for home, away in matches:
        try:
            print("\n" + "=" * 100)
            print(f"AGENT DEBATE: {home} vs {away}")
            print("=" * 100)

            result = system.predict_match(home, away)
            results.append(result)

            # Mostrar consenso
            print("\nCONSENSO FINAL:")
            print(result["consensus"])

        except Exception as e:
            print(f"ERROR en {home} vs {away}: {e}")
            results.append({"match": f"{home} vs {away}", "error": str(e)})

    system.close()

    # Guardar resultados
    output_file = ROOT / "data/processed/agent_debate_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n[OK] Resultados guardados en: {output_file}")


if __name__ == "__main__":
    main()
