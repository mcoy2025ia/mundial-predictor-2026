"""Tests for src/agents/match_intel.py — the free evidence layer for agents."""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.agents.match_intel import MatchIntel, _result_letter


def _hist() -> pd.DataFrame:
    """Synthetic international results: France strong, Norway mid."""
    rows = [
        # France: 3 wins, 1 draw, scoring well, solid defense
        ("2026-05-01", "France", "Norway", 2, 1),
        ("2026-05-10", "France", "Senegal", 3, 0),
        ("2026-05-20", "Iraq", "France", 0, 2),
        ("2026-06-01", "France", "Iceland", 1, 1),
        ("2026-06-12", "France", "Senegal", 3, 1),   # WC
        # Norway: mixed
        ("2026-05-05", "Norway", "Sweden", 1, 1),
        ("2026-05-15", "Norway", "Iraq", 4, 1),      # later WC-ish
        ("2026-06-13", "Norway", "Iraq", 4, 1),      # WC
    ]
    df = pd.DataFrame(rows, columns=["date", "home_team", "away_team", "home_score", "away_score"])
    df["date"] = pd.to_datetime(df["date"])
    df["tournament"] = "Friendly"
    df["neutral"] = False
    return df


def _wc26() -> pd.DataFrame:
    rows = [
        ("2026-06-12", "France", "Senegal", 3, 1),
        ("2026-06-13", "Norway", "Iraq", 4, 1),
    ]
    df = pd.DataFrame(rows, columns=["date", "home_team", "away_team", "home_score", "away_score"])
    df["date"] = pd.to_datetime(df["date"])
    return df


def _elo() -> dict:
    return {"France": 1980, "Norway": 1650, "Senegal": 1760, "Iraq": 1550, "Sweden": 1700}


@pytest.fixture
def intel() -> MatchIntel:
    return MatchIntel(_hist(), _wc26(), [], _elo())


def test_result_letter():
    assert _result_letter(2, 1) == "W"
    assert _result_letter(0, 3) == "L"
    assert _result_letter(1, 1) == "D"


def test_form_summary_has_record_and_opponents(intel):
    asof = datetime(2026, 6, 26)
    s = intel.form_summary("France", asof)
    assert s is not None
    assert "W" in s and "vs" in s
    # opponent quality tier should appear for known-ELO opponents
    assert "[" in s


def test_goal_trend_reports_averages(intel):
    asof = datetime(2026, 6, 26)
    s = intel.goal_trend("France", asof)
    assert s is not None
    assert "scored" in s and "conceded" in s


def test_quality_label_bands(intel):
    assert intel._quality_label("France") == "elite"
    assert intel._quality_label("Senegal") == "strong"
    assert intel._quality_label("Norway") == "mid"
    assert intel._quality_label("Iraq") == "weak"
    assert intel._quality_label("Unknown Team") == ""


def test_h2h_orientation(intel):
    asof = datetime(2026, 6, 26)
    s = intel.h2h_summary("France", "Norway", asof)
    assert s is not None
    assert "France" in s and "meeting" in s


def test_wc_results_only_tournament(intel):
    s = intel.wc_results("France")
    assert s is not None
    assert "Senegal" in s
    # Friendlies must not leak into WC results
    assert "Iceland" not in s


def test_momentum_label(intel):
    asof = datetime(2026, 6, 26)
    m = intel.momentum("France", asof)
    assert m in {"hot (strong recent run)", "rising", "falling", "stable", "cold (poor recent run)"}


def test_enrich_returns_all_keys(intel):
    asof = datetime(2026, 6, 26)
    enr = intel.enrich("France", "Norway", asof)
    for key in (
        "home_form", "away_form", "home_goal_trend", "away_goal_trend",
        "home_momentum", "away_momentum", "h2h_summary",
        "home_wc_results", "away_wc_results", "home_scorers", "away_scorers",
        "third_place_math",
    ):
        assert key in enr


def test_no_evidence_returns_none():
    empty = pd.DataFrame(columns=["date", "home_team", "away_team", "home_score", "away_score", "tournament", "neutral"])
    mi = MatchIntel(empty, empty, [], {})
    asof = datetime(2026, 6, 26)
    assert mi.form_summary("Nobody", asof) is None
    assert mi.goal_trend("Nobody", asof) is None
    assert mi.h2h_summary("A", "B", asof) is None


def test_third_place_math_reads_standings(intel):
    standings = {
        "Group I": {
            "France": {"pts": 6, "gd": 4, "gf": 6, "played": 2},
            "Norway":  {"pts": 4, "gd": 2, "gf": 5, "played": 2},
            "Senegal": {"pts": 1, "gd": -2, "gf": 2, "played": 2},
            "Iraq":    {"pts": 0, "gd": -4, "gf": 1, "played": 2},
        }
    }
    s = intel.third_place_math("Senegal", "Group I", standings)
    assert s is not None
    assert "Senegal" in s and "3rd" in s
    # no double "Group Group"
    assert "Group Group" not in s
