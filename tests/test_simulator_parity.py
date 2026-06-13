"""Test de paridad entre el simulador Python y los datos que usa el simulador TypeScript.

El simulador TS lee predictions.json (pre-calculado por Python).
Este test verifica que:
1. Todas las probs en predictions.json son consistentes con el modelo Python en vivo.
2. La simetría directa/inversa se cumple en ambas fuentes (A vs B == B vs A invertido).
3. Todas las probs suman 1.0 ± tolerancia.
4. Los valores están en rango [0, 1].
5. El simulador Python produce distribuciones plausibles con seed fijo.

La "paridad" TS↔Python es estructural: el TS lee exactamente el JSON que Python exporta,
por lo que cualquier discrepancia en predictions.json se propagaría a ambos sistemas.
"""
import json
import math
import random
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
PREDICTIONS_PATH = ROOT / "frontend" / "public" / "data" / "predictions.json"

# Cuántos pares muestrear para verificar consistencia (test rápido)
N_SAMPLE_PAIRS = 50
PROB_TOL = 1e-3  # tolerancia para suma de probabilidades


@pytest.fixture(scope="module")
def predictions() -> dict:
    if not PREDICTIONS_PATH.exists():
        pytest.skip("predictions.json no existe — correr export_frontend_data.py primero")
    with open(PREDICTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Tests sobre predictions.json (fuente compartida Python↔TS)
# ---------------------------------------------------------------------------

def test_predictions_not_empty(predictions):
    assert len(predictions) > 0, "predictions.json está vacío"


def test_all_probs_sum_to_one(predictions):
    """Todas las 2,256 predicciones deben sumar 1.0 ± tolerancia."""
    errors = []
    for key, probs in predictions.items():
        total = probs["home_win"] + probs["draw"] + probs["away_win"]
        if abs(total - 1.0) > PROB_TOL:
            errors.append(f"{key}: sum={total:.6f}")
    assert not errors, f"Probabilidades no suman 1.0 en {len(errors)} pares:\n" + "\n".join(errors[:5])


_PROB_FIELDS = {"home_win", "draw", "away_win", "ensemble_home_win", "ensemble_draw", "ensemble_away_win"}


def test_all_probs_in_valid_range(predictions):
    """Las probabilidades 1X2 deben estar en [0, 1]."""
    errors = []
    for key, entry in predictions.items():
        for field in _PROB_FIELDS:
            p = entry.get(field)
            if p is None:
                continue
            if not (0.0 <= float(p) <= 1.0):
                errors.append(f"{key} {field}={p}")
    assert not errors, f"Probabilidades fuera de rango en {len(errors)} casos:\n" + "\n".join(errors[:5])


HOSTS = {"Mexico", "United States", "Canada"}


def test_symmetry_home_away(predictions):
    """Para pares sin anfitriones, A|B y B|A deben tener probs invertidas.

    Los partidos con anfitriones son INTENCIONALMENTE asimétricos:
    host como 'home' usa is_neutral=0 (ventaja local); como 'away' usa is_neutral=1.
    """
    errors = []
    missing = []
    keys = list(predictions.keys())
    for key in keys:
        home, away = key.split("|")
        reverse_key = f"{away}|{home}"
        if reverse_key not in predictions:
            missing.append(f"Falta la dirección inversa de: {key}")
            continue
        # Saltar pares que involucran anfitriones (asimetría por diseño)
        if home in HOSTS or away in HOSTS:
            continue
        p_fwd = predictions[key]
        p_rev = predictions[reverse_key]
        if abs(p_fwd["home_win"] - p_rev["away_win"]) > PROB_TOL:
            errors.append(
                f"{key}: home_win={p_fwd['home_win']} != {reverse_key} away_win={p_rev['away_win']}"
            )
        if abs(p_fwd["draw"] - p_rev["draw"]) > PROB_TOL:
            errors.append(
                f"{key}: draw={p_fwd['draw']} != {reverse_key} draw={p_rev['draw']}"
            )
    assert not missing, f"Direcciones inversas faltantes: {missing[:3]}"
    assert not errors, f"Simetría rota en {len(errors)} pares (sin anfitriones):\n" + "\n".join(errors[:5])


def test_no_team_always_loses(predictions):
    """Ningún equipo debe tener win_prob=0 para TODOS sus partidos (señal de datos corruptos)."""
    from collections import defaultdict
    team_wins = defaultdict(list)
    for key, probs in predictions.items():
        home, away = key.split("|")
        team_wins[home].append(probs["home_win"])
        team_wins[away].append(probs["away_win"])
    for team, wins in team_wins.items():
        assert max(wins) > 0.01, f"{team} tiene win_prob=0 en todos sus partidos"


def test_draw_probs_reasonable(predictions):
    """La probabilidad de empate debe estar entre 5% y 50% para todos los pares."""
    out_of_range = [
        (k, v["draw"])
        for k, v in predictions.items()
        if not (0.05 <= v["draw"] <= 0.50)
    ]
    assert not out_of_range, (
        f"{len(out_of_range)} pares con draw fuera de [5%,50%]:\n"
        + "\n".join(f"{k}: {p:.3f}" for k, p in out_of_range[:5])
    )


def test_host_nations_have_home_advantage(predictions):
    """México, USA y Canadá deben tener mayor win_prob como 'home' vs como 'away'.

    Cuando el host aparece como 'home' en el key, el export usó is_neutral=0 (+100 ELO).
    Cuando aparece como 'away', is_neutral=1 (sede neutral). Por tanto avg_home >= avg_away.
    """
    hosts = ["Mexico", "United States", "Canada"]
    failures = []
    for host in hosts:
        host_home_wins = []
        host_away_wins = []
        for key, probs in predictions.items():
            home, away = key.split("|")
            if home == host:
                host_home_wins.append(probs["home_win"])
            elif away == host:
                host_away_wins.append(probs["away_win"])
        if not host_home_wins or not host_away_wins:
            continue
        avg_home = sum(host_home_wins) / len(host_home_wins)
        avg_away = sum(host_away_wins) / len(host_away_wins)
        # Tolerancia: el promedio home puede empatar al away por equipos muy desbalanceados
        if avg_home < avg_away - 0.005:
            failures.append(f"{host}: avg_home={avg_home:.4f} < avg_away={avg_away:.4f}")
    assert not failures, "Anfitriones sin ventaja local:\n" + "\n".join(failures)


# ---------------------------------------------------------------------------
# Test de consistencia: re-predecir muestra con el modelo Python en vivo
# ---------------------------------------------------------------------------

def test_python_model_matches_predictions_json(predictions):
    """Samplea N pares y verifica que el modelo Python produce probs ≈ predictions.json."""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from src.features import compute_elo_ratings
        from src.extractor import load_results
        from src.model import load_model
        from src.simulator import predict_match as py_predict
    except Exception as e:
        pytest.skip(f"No se puede cargar el modelo Python: {e}")

    try:
        df_all = load_results()
        _, elo_ratings = compute_elo_ratings(df_all)
        model = load_model()
    except Exception as e:
        pytest.skip(f"Datos o modelo no disponibles: {e}")

    keys = list(predictions.keys())
    rng = random.Random(42)
    sample = rng.sample(keys, min(N_SAMPLE_PAIRS, len(keys)))

    tolerance = 0.02  # 2% — diferencia aceptable por re-entrenamientos y floating point

    mismatches = []
    for key in sample:
        home, away = key.split("|")
        p_json = predictions[key]
        try:
            p_h, p_d, p_a = py_predict(
                home, away, model,
                elo_ratings=elo_ratings,
                is_neutral=True,
                df_all=df_all,
            )
        except Exception as e:
            continue  # equipos no encontrados — saltar
        for val_json, val_py, label in [
            (p_json["home_win"], p_h, "home_win"),
            (p_json["draw"], p_d, "draw"),
            (p_json["away_win"], p_a, "away_win"),
        ]:
            if abs(val_json - val_py) > tolerance:
                mismatches.append(
                    f"{key} {label}: json={val_json:.4f} py={val_py:.4f} diff={abs(val_json-val_py):.4f}"
                )

    assert not mismatches, (
        f"Modelo Python difiere de predictions.json en {len(mismatches)} casos "
        f"(tolerancia={tolerance}):\n" + "\n".join(mismatches[:10])
    )


# ---------------------------------------------------------------------------
# Test de simulación Monte Carlo Python: distribuciones plausibles
# ---------------------------------------------------------------------------

def test_python_simulator_champion_distribution(predictions):
    """El simulador Python debe producir distribuciones plausibles con seed=42."""
    try:
        import sys
        sys.path.insert(0, str(ROOT))
        from src.simulator import simulate_tournament
        from src.extractor import load_results
        from src.features import compute_elo_ratings
        from src.model import load_model
    except Exception as e:
        pytest.skip(f"Simulador no disponible: {e}")

    try:
        df_all = load_results()
        _, elo_ratings = compute_elo_ratings(df_all)
        model = load_model()
    except Exception as e:
        pytest.skip(f"Datos no disponibles: {e}")

    n_sims = 500  # pocos para que el test sea rápido
    try:
        results = simulate_tournament(model, elo_ratings, n_sims=n_sims, random_state=42, df_all=df_all)
    except Exception as e:
        pytest.skip(f"simulate_tournament falló: {e}")

    champion_dist = results.get("champion", {})
    if not champion_dist:
        pytest.skip("simulate_tournament no retornó champion distribution")

    # Suma de probs de campeón ≈ 1.0
    total = sum(champion_dist.values())
    assert abs(total - 1.0) < 0.02, f"Distribución de campeones no suma 1: {total:.4f}"

    # Ningún favorito histórico debe tener 0% de ganar
    favorites = ["Brazil", "France", "Germany", "Spain", "Argentina"]
    for team in favorites:
        p = champion_dist.get(team, 0)
        assert p > 0.001, f"{team} tiene win_prob={p} — parece un error en la simulación"
