"""Audit Agent Debate coverage and accuracy by tournament phase.

This report intentionally separates coverage from validity. Old debate entries
that do not carry audit metadata can still be scored, but they are marked as
"unknown provenance" and should not be presented as strict pre-match evidence.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEBATE_FILE = ROOT / "frontend/public/data/agent_debate_results.json"
GROUP_MATCHES_FILE = ROOT / "frontend/public/data/group_matches.json"
BRACKET_FILE = ROOT / "frontend/public/data/knockout_bracket.json"
LIVE_RESULTS_FILE = ROOT / "data/external/wc2026_live_results.csv"


def norm(name: str | None) -> str:
    return re.sub(r"\s+", " ", (name or "").strip().lower())


def pair_key(a: str, b: str) -> tuple[str, str]:
    return tuple(sorted((norm(a), norm(b))))


def round_to_jor(round_name: str | None) -> str:
    n = int("".join(ch for ch in (round_name or "Matchday 1") if ch.isdigit()) or "1")
    if n <= 7:
        return "J1"
    if n <= 13:
        return "J2"
    return "J3"


def debate_teams(entry: dict) -> tuple[str, str] | None:
    if entry.get("home") and entry.get("away"):
        return entry["home"], entry["away"]
    ctx = entry.get("context") or {}
    home = (ctx.get("home_team") or {}).get("name")
    away = (ctx.get("away_team") or {}).get("name")
    if home and away:
        return home, away
    match = entry.get("match", "")
    if " vs " in match:
        home, away = match.split(" vs ", 1)
        return home.strip(), away.strip()
    return None


def load_scores() -> dict[tuple[str, str], dict]:
    scores = {}
    with LIVE_RESULTS_FILE.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                int(row["home_score"])
                int(row["away_score"])
            except (KeyError, TypeError, ValueError):
                continue
            scores[pair_key(row["home_team"], row["away_team"])] = row
    return scores


def orient_hit(debate: dict, team1: str, team2: str, score1: int, score2: int) -> dict[str, bool]:
    teams = debate_teams(debate)
    if not teams:
        return {}
    debate_home, _ = teams
    same_order = norm(debate_home) == norm(team1)
    actual = "home" if score1 > score2 else "away" if score1 < score2 else "draw"
    hits = {}
    for pred in debate.get("predictions") or []:
        agent = pred.get("agent") or "Unknown"
        winner = pred.get("predicted_winner")
        if not same_order and winner in {"home", "away"}:
            winner = "away" if winner == "home" else "home"
        hits[agent] = winner == actual
    return hits


def played_group_rows(scores: dict[tuple[str, str], dict]) -> list[dict]:
    group_matches = json.loads(GROUP_MATCHES_FILE.read_text(encoding="utf-8"))
    rows = []
    for group, matches in group_matches.items():
        for match in matches:
            key = pair_key(match["team1"], match["team2"])
            score = scores.get(key)
            if not score:
                continue
            s1, s2 = int(score["home_score"]), int(score["away_score"])
            if norm(score["home_team"]) != norm(match["team1"]):
                s1, s2 = s2, s1
            rows.append({
                "phase": round_to_jor(match.get("round")),
                "team1": match["team1"],
                "team2": match["team2"],
                "score1": s1,
                "score2": s2,
                "group": group,
            })
    return rows


def played_knockout_rows() -> list[dict]:
    bracket = json.loads(BRACKET_FILE.read_text(encoding="utf-8"))
    rows = []
    for round_key, matches in (bracket.get("rounds") or {}).items():
        for match in matches:
            result = match.get("result") or {}
            if not match.get("home") or not match.get("away") or not result.get("played"):
                continue
            rows.append({
                "phase": round_key,
                "team1": match["home"],
                "team2": match["away"],
                "score1": int(result["home_score"]),
                "score2": int(result["away_score"]),
                "group": round_key,
            })
    return rows


def main() -> int:
    debates = json.loads(DEBATE_FILE.read_text(encoding="utf-8"))
    debate_by_pair = {
        pair_key(*teams): debate
        for debate in debates
        if (teams := debate_teams(debate))
    }

    rows = played_group_rows(load_scores()) + played_knockout_rows()
    coverage = defaultdict(lambda: {"played": 0, "debated": 0, "missing": []})
    accuracy = defaultdict(lambda: defaultdict(lambda: {"hits": 0, "played": 0}))
    provenance = defaultdict(lambda: {"pre_match": 0, "backfill": 0, "unknown": 0})

    for row in rows:
        phase = row["phase"]
        coverage[phase]["played"] += 1
        debate = debate_by_pair.get(pair_key(row["team1"], row["team2"]))
        if not debate:
            coverage[phase]["missing"].append(f"{row['team1']} vs {row['team2']}")
            continue
        coverage[phase]["debated"] += 1

        audit = debate.get("audit") or {}
        if audit.get("execution_mode") == "backfill":
            provenance[phase]["backfill"] += 1
        elif audit.get("was_pre_match") is True:
            provenance[phase]["pre_match"] += 1
        else:
            provenance[phase]["unknown"] += 1

        for agent, hit in orient_hit(
            debate, row["team1"], row["team2"], row["score1"], row["score2"]
        ).items():
            accuracy[phase][agent]["played"] += 1
            accuracy[phase][agent]["hits"] += int(hit)

    phase_order = [
        "J1", "J2", "J3", "Round of 32", "Round of 16",
        "Quarter-final", "Semi-final", "Match for third place", "Final",
    ]
    print("Agent Debate validation audit")
    print("=" * 32)
    for phase in phase_order:
        if phase not in coverage:
            continue
        cov = coverage[phase]
        print(f"\n{phase}: {cov['debated']}/{cov['played']} debated")
        prov = provenance[phase]
        if cov["debated"]:
            print(
                "  provenance: "
                f"pre_match={prov['pre_match']}, backfill={prov['backfill']}, unknown={prov['unknown']}"
            )
        for agent, stats in sorted(accuracy[phase].items()):
            played = stats["played"]
            pct = stats["hits"] / played * 100 if played else 0.0
            print(f"  {agent}: {stats['hits']}/{played} ({pct:.1f}%)")
        if cov["missing"]:
            print("  missing:")
            for match in cov["missing"][:8]:
                print(f"    - {match}")
            if len(cov["missing"]) > 8:
                print(f"    ... {len(cov['missing']) - 8} more")

    unknown_total = sum(v["unknown"] for v in provenance.values())
    if unknown_total:
        print(
            "\nWARNING: Some scored debates have unknown provenance because older JSON "
            "entries lack audit metadata. Do not present those as strict pre-match "
            "validation unless external logs prove timing."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
