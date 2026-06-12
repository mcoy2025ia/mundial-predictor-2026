"""Tests de integridad post-pipeline: validan que los artefactos generados
son consistentes con el fixture oficial del Mundial 2026."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
DATA_PROCESSED = ROOT / "data" / "processed"
DATA_EXTERNAL = ROOT / "data" / "external"
FRONTEND_DATA = ROOT / "frontend" / "public" / "data"

from src.simulator import WC2026_GROUPS, WC2026_TEAMS, WC2026_HOSTS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# ── Fixtures que requieren artefactos generados ──────────────────────────────

@pytest.fixture(scope="module")
def elo_ratings():
    path = DATA_PROCESSED / "elo_current.json"
    if not path.exists():
        pytest.skip("elo_current.json no existe — corre run_pipeline.py primero")
    return _load_json(path)


@pytest.fixture(scope="module")
def teams_json():
    path = FRONTEND_DATA / "teams.json"
    if not path.exists():
        pytest.skip("teams.json no existe — corre export_frontend_data.py primero")
    return _load_json(path)


@pytest.fixture(scope="module")
def predictions_json():
    path = FRONTEND_DATA / "predictions.json"
    if not path.exists():
        pytest.skip("predictions.json no existe — corre export_frontend_data.py primero")
    return _load_json(path)


# ── Tests ELO ────────────────────────────────────────────────────────────────

def test_all_wc_teams_have_elo(elo_ratings):
    missing = [t for t in WC2026_TEAMS if t not in elo_ratings]
    assert not missing, f"Equipos sin ELO real (caerían a default 1500): {missing}"


def test_elo_values_in_sane_range(elo_ratings):
    for team in WC2026_TEAMS:
        elo = elo_ratings.get(team, 0)
        assert 1000 < elo < 2500, f"{team} tiene ELO={elo} fuera del rango esperado"


# ── Tests teams.json ─────────────────────────────────────────────────────────

def test_all_wc_teams_in_teams_json(teams_json):
    missing = [t for t in WC2026_TEAMS if t not in teams_json]
    assert not missing, f"Equipos ausentes en teams.json: {missing}"


def test_no_team_has_default_elo_1500(teams_json):
    """Equipos con ELO exactamente 1500 son sospechosos (valor default)."""
    default_elo = [
        t for t in WC2026_TEAMS
        if teams_json.get(t, {}).get("elo") == 1500.0
    ]
    assert not default_elo, f"Equipos con ELO=1500 (default silencioso): {default_elo}"


def test_all_teams_have_nonzero_wc_matches_or_debutant(teams_json):
    """Debutantes reales deben tener wc_matches=0 — pero la forma reciente
    NO debe ser los valores hardcodeados (1.5/1.2)."""
    debutants_2026 = {"Curacao", "Jordan", "Cape Verde", "Uzbekistan"}
    for team in debutants_2026:
        if team in teams_json:
            assert teams_json[team]["wc_matches"] == 0, \
                f"{team} debería ser debutante (wc_matches=0)"
            scored = teams_json[team].get("goals_scored", 1.5)
            conceded = teams_json[team].get("goals_conceded", 1.2)
            assert scored != 1.5 or conceded != 1.2, \
                f"{team} usa defaults hardcodeados (goals_scored=1.5, goals_conceded=1.2)"


# ── Tests predictions.json ───────────────────────────────────────────────────

def test_probabilities_sum_to_one(predictions_json):
    failures = []
    for key, p in predictions_json.items():
        total = p["home_win"] + p["draw"] + p["away_win"]
        if abs(total - 1.0) > 1e-3:
            failures.append((key, total))
    assert not failures, f"Probabilidades no suman 1: {failures[:5]}"


def test_host_teams_both_directions_exist(predictions_json):
    """Cuando un anfitrión juega contra un no-anfitrión, ambas direcciones
    deben existir en predictions.json con probabilidades válidas.

    Nota: la asimetría real (ventaja local) se verificará en Fase 2 cuando el
    modelo entrene con todos los internacionales y tenga señal para is_neutral.
    El modelo actual (solo WC) tiene señal casi nula para este feature.
    """
    for host in WC2026_HOSTS:
        opponent = next(t for t in WC2026_TEAMS if t != host and t not in WC2026_HOSTS)
        for key in [f"{host}|{opponent}", f"{opponent}|{host}"]:
            assert key in predictions_json, f"Falta {key} en predictions.json"
            p = predictions_json[key]
            total = p["home_win"] + p["draw"] + p["away_win"]
            assert abs(total - 1.0) < 1e-3, f"{key}: probs no suman 1 ({total:.4f})"


def test_all_wc_pairs_present(predictions_json):
    """Todos los pares de equipos del Mundial deben tener predicción."""
    missing = []
    for i, t1 in enumerate(WC2026_TEAMS):
        for t2 in WC2026_TEAMS[i + 1:]:
            if f"{t1}|{t2}" not in predictions_json and f"{t2}|{t1}" not in predictions_json:
                missing.append(f"{t1} vs {t2}")
    assert not missing, f"Pares sin predicción: {missing[:5]}"


# ── Tests consistencia grupos ─────────────────────────────────────────────────

def test_groups_cover_48_teams():
    all_teams = [t for ts in WC2026_GROUPS.values() for t in ts]
    assert len(all_teams) == 48, f"WC2026_GROUPS tiene {len(all_teams)} equipos, se esperan 48"
    assert len(set(all_teams)) == 48, "Hay equipos duplicados en WC2026_GROUPS"


def test_hosts_are_in_wc_teams():
    for host in WC2026_HOSTS:
        assert host in WC2026_TEAMS, f"Anfitrión '{host}' no está en WC2026_TEAMS"
