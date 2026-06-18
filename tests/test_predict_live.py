"""Tests para el modo live de predicciones."""
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

import sys
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.predict_live import (
    _is_neutral,
    _norm_team,
    _parse_kickoff,
    assert_no_leakage,
    build_simultaneous_group_context,
    build_third_place_context,
    load_fixture,
)


# ---------------------------------------------------------------------------
# Normalización de nombres
# ---------------------------------------------------------------------------

def test_norm_team_usa():
    assert _norm_team("USA") == "United States"


def test_norm_team_bosnia():
    assert _norm_team("Bosnia & Herzegovina") == "Bosnia and Herzegovina"


def test_norm_team_passthrough():
    assert _norm_team("Brazil") == "Brazil"


# ---------------------------------------------------------------------------
# Parseo de kickoff
# ---------------------------------------------------------------------------

def test_parse_kickoff_utc_minus_6():
    dt = _parse_kickoff("2026-06-11", "13:00 UTC-6")
    assert dt == datetime(2026, 6, 11, 19, 0)  # 13:00-6 = 19:00 UTC


def test_parse_kickoff_utc_minus_4():
    dt = _parse_kickoff("2026-06-12", "15:00 UTC-4")
    assert dt == datetime(2026, 6, 12, 19, 0)  # 15:00-4 = 19:00 UTC


def test_parse_kickoff_half_hour():
    dt = _parse_kickoff("2026-07-19", "15:00 UTC-4")
    assert dt.year == 2026 and dt.month == 7 and dt.day == 19


# ---------------------------------------------------------------------------
# is_neutral
# ---------------------------------------------------------------------------

def test_mexico_home_not_neutral():
    assert _is_neutral("Mexico", "Brazil", "Mexico City") is False


def test_mexico_away_neutral():
    # Mexico como visitante en Houston → neutral
    assert _is_neutral("Brazil", "Mexico", "Houston") is True


def test_canada_home_not_neutral():
    assert _is_neutral("Canada", "France", "Vancouver") is False


def test_usa_home_not_neutral():
    assert _is_neutral("United States", "Germany", "Dallas") is False


def test_neutral_match():
    assert _is_neutral("Brazil", "France", "Dallas") is True


def test_build_simultaneous_group_context_lists_same_kickoff_peer():
    kickoff = datetime(2026, 6, 24, 19, 0)
    fixture = [
        {"home_team": "A", "away_team": "B", "group": "Group X", "kickoff": kickoff},
        {"home_team": "C", "away_team": "D", "group": "Group X", "kickoff": kickoff},
        {"home_team": "E", "away_team": "F", "group": "Group X", "kickoff": kickoff + timedelta(hours=1)},
    ]
    assert build_simultaneous_group_context(fixture[0], fixture) == "C vs D"


def test_build_third_place_context_uses_cutline_and_tiebreakers():
    standings = {}
    for i, pts in enumerate([6, 5, 4, 4, 3, 3, 2, 2, 1], start=1):
        grp = f"Group {chr(64 + i)}"
        standings[grp] = {
            f"{grp} 1": {"pts": 6, "gd": 2, "gf": 4, "played": 2},
            f"{grp} 2": {"pts": 5, "gd": 1, "gf": 3, "played": 2},
            f"{grp} 3": {"pts": pts, "gd": i % 3 - 1, "gf": i, "played": 2},
            f"{grp} 4": {"pts": 0, "gd": -3, "gf": 1, "played": 2},
        }
    ctx = build_third_place_context(standings)
    assert "best_third_cutline=" in ctx
    assert "1.A:" in ctx


# ---------------------------------------------------------------------------
# Anti-leakage
# ---------------------------------------------------------------------------

def test_assert_no_leakage_ok():
    kickoff = datetime(2026, 6, 15, 20, 0)
    cutoff = kickoff - timedelta(seconds=60)
    assert_no_leakage(cutoff, kickoff)  # no debe lanzar


def test_assert_no_leakage_fires():
    kickoff = datetime(2026, 6, 15, 20, 0)
    bad_cutoff = kickoff  # igual → fuga
    with pytest.raises(ValueError, match="LEAKAGE"):
        assert_no_leakage(bad_cutoff, kickoff)


def test_assert_no_leakage_fires_after():
    kickoff = datetime(2026, 6, 15, 20, 0)
    bad_cutoff = kickoff + timedelta(seconds=1)
    with pytest.raises(ValueError, match="LEAKAGE"):
        assert_no_leakage(bad_cutoff, kickoff)


# ---------------------------------------------------------------------------
# load_fixture
# ---------------------------------------------------------------------------

def test_fixture_loads_real_teams():
    matches = load_fixture()
    assert len(matches) > 50, "Fixture debe tener al menos 50 partidos reales"


def test_fixture_no_placeholders():
    matches = load_fixture()
    for m in matches:
        for field in ("home_team", "away_team"):
            name = m[field]
            assert not name.startswith("W"), f"Placeholder no filtrado: {name}"
            assert not name.startswith("1"), f"Placeholder no filtrado: {name}"


def test_fixture_has_kickoff_datetime():
    matches = load_fixture()
    for m in matches[:5]:
        assert isinstance(m["kickoff"], datetime)


def test_fixture_mexico_home_not_neutral():
    matches = load_fixture()
    mex_home = [m for m in matches if m["home_team"] == "Mexico" and "Mexico City" in m["venue"]]
    assert mex_home, "Debe haber partidos de Mexico en Mexico City"
    assert all(not m["is_neutral"] for m in mex_home)


def test_fixture_usa_normalized():
    matches = load_fixture()
    teams = {m["home_team"] for m in matches} | {m["away_team"] for m in matches}
    assert "United States" in teams, "USA debe normalizarse a 'United States'"
    assert "USA" not in teams, "'USA' no debe quedar sin normalizar"
