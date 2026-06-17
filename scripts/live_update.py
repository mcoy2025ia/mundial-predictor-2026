"""
Actualización completa del modelo con resultados en vivo del Mundial 2026.

Flujo:
  1. Fetch partidos terminados desde football-data.org → appends a results.csv
  2. Si hay partidos nuevos: re-corre el pipeline (ELO + features + XGBoost)
  3. Exporta JSONs al frontend (predictions, teams, group_standings, etc.)
  4. Imprime instrucciones para hacer commit + deploy a Vercel

Uso:
    python scripts/live_update.py              # actualización completa
    python scripts/live_update.py --dry-run    # solo muestra qué se agregaría
    python scripts/live_update.py --force      # re-entrena aunque no haya partidos nuevos
    python scripts/live_update.py --token TOK  # override del token de API
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("live_update")

DIVIDER = "═" * 55


def _run(label: str, cmd: list[str]) -> bool:
    logger.info("%s", DIVIDER)
    logger.info("  %s", label)
    logger.info("%s", DIVIDER)
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        logger.error("'%s' terminó con código %d", label, result.returncode)
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Actualiza el modelo XGBoost con resultados en vivo del WC 2026"
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Ver qué se agregaría sin modificar nada")
    parser.add_argument("--force", action="store_true",
                        help="Re-entrenar aunque no haya partidos nuevos")
    parser.add_argument("--token", default=None,
                        help="Token de football-data.org")
    args = parser.parse_args()

    python = sys.executable

    # ── PASO 1: Fetch resultados ───────────────────────────────────────────
    fetch_cmd = [python, str(ROOT / "scripts" / "update_wc_results.py")]
    if args.dry_run:
        fetch_cmd.append("--dry-run")
    if args.token:
        fetch_cmd += ["--token", args.token]

    logger.info("%s", DIVIDER)
    logger.info("  PASO 1: Fetch resultados WC 2026")
    logger.info("%s", DIVIDER)
    result = subprocess.run(fetch_cmd, text=True)

    # Exit codes from update_wc_results:  0=nada nuevo  2=nuevos  1=error
    if result.returncode == 1:
        logger.error("Fetch falló. Verifica FOOTBALL_DATA_TOKEN y la conexión.")
        sys.exit(1)

    new_matches = result.returncode == 2   # True si hubo partidos nuevos
    dry_run_exit = args.dry_run

    if dry_run_exit:
        logger.info("[DRY-RUN] Simulación terminada. Sin cambios en disco.")
        sys.exit(0)

    if not new_matches and not args.force:
        logger.info("")
        logger.info("No hay partidos nuevos. El modelo está al día.")
        logger.info("Usa --force para re-entrenar de todas formas.")
        sys.exit(0)

    # ── PASO 2: Re-entrenar pipeline ──────────────────────────────────────
    if not _run(
        "PASO 2: Re-entrenar pipeline (ELO + features + XGBoost + Poisson)",
        [python, str(ROOT / "scripts" / "run_pipeline.py")],
    ):
        sys.exit(1)

    # ── PASO 3: Exportar JSONs al frontend ────────────────────────────────
    if not _run(
        "PASO 3: Exportar JSONs al frontend",
        [python, str(ROOT / "scripts" / "export_frontend_data.py")],
    ):
        sys.exit(1)

    # ── Resumen ───────────────────────────────────────────────────────────
    logger.info("%s", DIVIDER)
    logger.info("  ✓ Actualización completa")
    logger.info("%s", DIVIDER)
    logger.info("")
    logger.info("El modelo ya incorpora los resultados del Mundial 2026.")
    logger.info("Los ELO han sido recalculados y las predicciones actualizadas.")
    logger.info("")
    logger.info("Para desplegar a producción:")
    logger.info("  cd frontend")
    logger.info("  npx vercel --prod")
    logger.info("")
    logger.info("O para hacer commit primero:")
    logger.info("  git add data/raw/results.csv frontend/public/data/*.json")
    logger.info("  git commit -m 'update: WC 2026 live results'")


if __name__ == "__main__":
    main()
