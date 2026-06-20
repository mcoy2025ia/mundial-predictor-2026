"""Print upcoming group-stage Home/Away pairs (quoted, space-separated) kicking
off within the next WINDOW_HOURS, for the Agent Debate CI automation.
Empty output means nothing to debate yet -- the caller should skip the step.
"""
import csv
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LIVE_PREDS = ROOT / "data" / "processed" / "live_predictions.json"
LIVE_RESULTS = ROOT / "data" / "external" / "wc2026_live_results.csv"
WINDOW_HOURS = 36


def played_pairs() -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not LIVE_RESULTS.exists():
        return pairs
    with LIVE_RESULTS.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                home_score = int(row.get("home_score", -1))
                away_score = int(row.get("away_score", -1))
            except (TypeError, ValueError):
                continue
            if home_score >= 0 and away_score >= 0:
                pairs.add((row["home_team"], row["away_team"]))
    return pairs


def main() -> None:
    if not LIVE_PREDS.exists():
        return
    preds = json.loads(LIVE_PREDS.read_text(encoding="utf-8"))
    played = played_pairs()
    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(hours=WINDOW_HOURS)

    teams: list[str] = []
    for m in preds:
        if m.get("stage") != "group":
            continue
        home, away = m.get("home_team"), m.get("away_team")
        if not home or not away or (home, away) in played:
            continue
        try:
            kickoff = datetime.fromisoformat(str(m.get("kickoff", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if now <= kickoff <= cutoff:
            teams.extend([home, away])

    if teams:
        print(" ".join(f'"{t}"' for t in teams))


if __name__ == "__main__":
    main()
