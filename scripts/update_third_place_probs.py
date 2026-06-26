#!/usr/bin/env python3
"""
Update group_standings.json (third place probabilities) WITHOUT regenerating narrations.

Runs export_frontend_data.py but skips narration generation to save tokens.
Designed for frequent updates during J3 when standings change but narrations remain stable.
"""

import logging
import sys
import os
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.export_frontend_data import (
    load_models,
    load_predictions,
    export_group_standings,
    FRONTEND_DATA_PATH
)

def update_third_place_only():
    """Update group_standings.json (Monte Carlo simulation) without touching narrations."""
    logger.info("=" * 60)
    logger.info("  UPDATING THIRD PLACE PROBABILITIES ONLY (no narrations)")
    logger.info("=" * 60)

    try:
        # Load models and current state
        logger.info("Loading models and predictions...")
        ensemble, poisson = load_models()

        # Load predictions with live ELO
        preds = load_predictions()

        if not preds:
            logger.error("No predictions found. Exiting.")
            return 1

        # Load ELO ratings for simulator
        import json
        elo_path = ROOT / "data/processed/elo_current.json"
        with open(elo_path, encoding="utf-8") as f:
            elos = json.load(f)

        # Recompute group standings (Monte Carlo) — this includes third place probs
        logger.info("Running Monte Carlo simulation (5000 iterations) for group standings...")
        group_standings = export_group_standings(preds, elos, n=5000)

        # Write only group_standings.json
        output_file = FRONTEND_DATA_PATH / "group_standings.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(group_standings, f, ensure_ascii=False, indent=2)

        file_size = output_file.stat().st_size / 1024
        logger.info(f"✓ group_standings.json updated ({file_size:.1f} KB)")
        logger.info(f"  Location: {output_file}")

        return 0

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1

if __name__ == "__main__":
    sys.exit(update_third_place_only())
