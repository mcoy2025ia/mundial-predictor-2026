"""
Recalibra los pesos del ensemble (ELO / Poisson / XGB) usando los partidos
ya jugados del Mundial 2026 como mini walk-forward.

Metodología:
  - Para cada partido jugado del WC 2026, calcula predicciones por sub-modelo
    con cutoff = fecha del partido (sin usar resultados del mismo día → anti-leakage).
  - Computa RPS individual por modelo.
  - Grid search para minimizar RPS del ensemble ponderado sobre los 20 partidos.
  - Si los pesos óptimos mejoran el RPS en > 0.003, los aplica a DEFAULT_WEIGHTS.

Uso:
    python scripts/calibrate_ensemble_2026.py           # muestra resultados
    python scripts/calibrate_ensemble_2026.py --apply   # aplica pesos al ensemble.py
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("calibrate_ensemble_2026")


# ── Helpers RPS ───────────────────────────────────────────────────────────────

def _rps(y_true: int, probs: tuple[float, float, float]) -> float:
    """Ranked Probability Score para un partido (3 outcomes: 0=home 1=draw 2=away)."""
    n = 3
    cum_pred = np.cumsum(probs)
    cum_true = np.cumsum([1.0 if y_true == k else 0.0 for k in range(n)])
    return float(np.sum((cum_pred - cum_true) ** 2) / (n - 1))


def _mean_rps(y_trues: list[int], probs_list: list[tuple]) -> float:
    return float(np.mean([_rps(y, p) for y, p in zip(y_trues, probs_list)]))


def _blend(probs_list, weights):
    """Mezcla ponderada renormalizada."""
    w = np.array(weights, dtype=float)
    w /= w.sum()
    p = np.array(probs_list)  # shape (n_models, 3)
    blended = (p * w[:, None]).sum(axis=0)
    blended /= blended.sum()
    return tuple(blended.tolist())


# ── ELO proba (replicado para no depender del modelo cargado) ─────────────────

def _elo_proba(elo_h: float, elo_a: float, is_neutral: bool) -> tuple:
    adj = 0.0 if is_neutral else 100.0
    exp_h = 1 / (1 + 10 ** ((elo_a - elo_h - adj) / 400))
    draw = max(0.08, min(0.28 * (1 - abs(exp_h - 0.5) * 1.6), 0.36))
    ph = exp_h * (1 - draw)
    pa = (1 - exp_h) * (1 - draw)
    t = ph + draw + pa
    return (ph / t, draw / t, pa / t)


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_played_wc2026() -> pd.DataFrame:
    """Devuelve los partidos del WC 2026 que ya tienen score en results.csv."""
    from src.extractor import load_results, add_outcome
    df = load_results()
    wc26 = df[
        (df["tournament"] == "FIFA World Cup") &
        (df["date"].dt.year == 2026) &
        df["home_score"].notna() &
        df["away_score"].notna()
    ].copy()
    wc26 = add_outcome(wc26)
    wc26 = wc26[wc26["outcome"].notna()].reset_index(drop=True)
    logger.info("Partidos WC 2026 jugados: %d", len(wc26))
    return wc26


def get_per_model_predictions(
    played: pd.DataFrame,
) -> tuple[list[int], list[tuple], list[tuple], list[tuple]]:
    """
    Para cada partido en `played`, devuelve predicciones con cutoff = fecha - 1 día.

    Returns:
        y_trues   : lista de outcomes (0=home 1=draw 2=away)
        elo_probs : lista de (ph, pd, pa) del modelo ELO-only
        poi_probs : lista de (ph, pd, pa) del modelo Poisson-only
        xgb_probs : lista de (ph, pd, pa) del modelo XGB-only
    """
    from src.extractor import load_results
    from src.features import compute_elo_ratings, compute_current_form
    from src.model import load_model, FEATURE_COLS, LABEL_MAP
    from src.poisson_model import PoissonModel

    LABEL_MAP_REV = {v: k for k, v in LABEL_MAP.items()}

    df_hist = load_results()
    # Solo histórico pre-2026 (sin WC 2026) para la base
    df_hist_base = df_hist[df_hist["date"].dt.year < 2026].copy()

    # Modelos fijos (entrenados sobre histórico, sin WC 2026 en train — anti-leakage)
    xgb_model = load_model()
    poi_model = PoissonModel.load()

    y_trues, elo_probs_list, poi_probs_list, xgb_probs_list = [], [], [], []

    played_sorted = played.sort_values("date").reset_index(drop=True)

    for i, row in played_sorted.iterrows():
        match_date = pd.Timestamp(row["date"])
        cutoff = match_date - timedelta(days=1)  # usa datos hasta el día anterior

        # Dataset para ELO: histórico + partidos WC 2026 ANTERIORES al cutoff
        wc26_before = played_sorted[
            played_sorted["date"] < match_date
        ].copy()

        if len(wc26_before) > 0:
            df_combined = pd.concat([df_hist_base, wc26_before], ignore_index=True)
            df_combined = df_combined.sort_values("date").reset_index(drop=True)
        else:
            df_combined = df_hist_base.copy()

        _, elo_ratings = compute_elo_ratings(df_combined)

        home = str(row["home_team"])
        away = str(row["away_team"])
        DEFAULT_ELO = 1500.0
        elo_h = elo_ratings.get(home, DEFAULT_ELO)
        elo_a = elo_ratings.get(away, DEFAULT_ELO)

        is_neutral_val = bool(row.get("neutral", True)) if "neutral" in row else True

        # Outcome real
        outcome_str = row["outcome"]
        y = LABEL_MAP[outcome_str]
        y_trues.append(y)

        # ── ELO ──────────────────────────────────────────────────────────────
        elo_probs_list.append(_elo_proba(elo_h, elo_a, is_neutral_val))

        # ── Poisson ──────────────────────────────────────────────────────────
        try:
            elo_diff = elo_h - elo_a
            lam_h, lam_a = poi_model.predict_goals(
                home, away, is_neutral=is_neutral_val, elo_diff=elo_diff
            )
            matrix = poi_model.scoreline_matrix(lam_h, lam_a)
            poi_probs_list.append(poi_model.aggregate_1x2(matrix))
        except Exception as e:
            logger.debug("Poisson falló para %s vs %s: %s", home, away, e)
            poi_probs_list.append(_elo_proba(elo_h, elo_a, is_neutral_val))  # fallback

        # ── XGB ───────────────────────────────────────────────────────────────
        try:
            # Forma: últimos 5 partidos antes del cutoff
            def _form(team):
                mask = (df_combined["home_team"] == team) | (df_combined["away_team"] == team)
                r5 = df_combined[mask & df_combined["home_score"].notna()].sort_values("date").tail(5)
                if r5.empty:
                    return 1.3, 1.1
                sc, con = [], []
                for rr in r5.itertuples():
                    if rr.home_team == team:
                        sc.append(float(rr.home_score)); con.append(float(rr.away_score))
                    else:
                        sc.append(float(rr.away_score)); con.append(float(rr.home_score))
                return sum(sc) / len(sc), sum(con) / len(con)

            def _h2h(t1, t2):
                mask = (
                    ((df_combined["home_team"] == t1) & (df_combined["away_team"] == t2)) |
                    ((df_combined["home_team"] == t2) & (df_combined["away_team"] == t1))
                ) & df_combined["home_score"].notna()
                h2h = df_combined[mask]
                if h2h.empty:
                    return 0.5
                from src.extractor import add_outcome
                h2h = add_outcome(h2h.copy())
                wins = (
                    ((h2h["home_team"] == t1) & (h2h["outcome"] == "home_win")).sum() +
                    ((h2h["away_team"] == t1) & (h2h["outcome"] == "away_win")).sum()
                )
                return float(wins) / len(h2h)

            def _wc_exp(team):
                wc_mask = (df_combined["tournament"] == "FIFA World Cup") & (
                    (df_combined["home_team"] == team) | (df_combined["away_team"] == team)
                ) & df_combined["home_score"].notna()
                years = df_combined[wc_mask]["date"].dt.year.unique()
                return len(years)

            hgs, hgc = _form(home)
            ags, agc = _form(away)
            h2h_val = _h2h(home, away)
            wc_exp_h = _wc_exp(home)
            wc_exp_a = _wc_exp(away)

            feat = np.array([[
                elo_h - elo_a,
                elo_h,
                elo_a,
                hgs,
                hgc,
                ags,
                agc,
                h2h_val,
                1.0 if is_neutral_val else 0.0,
                wc_exp_h - wc_exp_a,
            ]], dtype=float)

            # Asegurar que el orden de features coincide con FEATURE_COLS
            expected = [
                "elo_diff", "elo_home", "elo_away",
                "home_goals_scored_avg5", "home_goals_conceded_avg5",
                "away_goals_scored_avg5", "away_goals_conceded_avg5",
                "h2h_home_win_pct", "is_neutral", "wc_experience_diff",
            ]
            if FEATURE_COLS == expected:
                p_xgb = xgb_model.predict_proba(feat)[0]
                xgb_probs_list.append((float(p_xgb[0]), float(p_xgb[1]), float(p_xgb[2])))
            else:
                xgb_probs_list.append(_elo_proba(elo_h, elo_a, is_neutral_val))
        except Exception as e:
            logger.debug("XGB features falló: %s", e)
            xgb_probs_list.append(_elo_proba(elo_h, elo_a, is_neutral_val))

    return y_trues, elo_probs_list, poi_probs_list, xgb_probs_list


def grid_search_weights(
    y_trues, elo_probs, poi_probs, xgb_probs, step=0.05
) -> tuple[dict, float]:
    """Grid search de pesos (w_elo, w_poi, w_xgb) que minimizan RPS."""
    best_rps = float("inf")
    best_weights = {"elo": 0.22, "poisson": 0.58, "xgb": 0.20}

    vals = np.arange(0.10, 0.81, step)
    for we in vals:
        for wp in vals:
            wx = round(1.0 - we - wp, 10)
            if wx < 0.05 or wx > 0.75:
                continue
            blended = [_blend([e, p, x], [we, wp, wx])
                       for e, p, x in zip(elo_probs, poi_probs, xgb_probs)]
            rps = _mean_rps(y_trues, blended)
            if rps < best_rps:
                best_rps = rps
                best_weights = {
                    "elo": round(float(we), 2),
                    "poisson": round(float(wp), 2),
                    "xgb": round(float(wx), 2),
                }
    return best_weights, best_rps


def apply_weights_to_ensemble(new_weights: dict) -> None:
    """Reescribe DEFAULT_WEIGHTS en src/ensemble.py con los nuevos pesos."""
    ensemble_path = ROOT / "src" / "ensemble.py"
    text = ensemble_path.read_text(encoding="utf-8")
    old_line = re.search(r"DEFAULT_WEIGHTS\s*=\s*\{[^\}]+\}", text)
    if not old_line:
        logger.error("No se encontró DEFAULT_WEIGHTS en ensemble.py")
        return
    new_line = (
        f'DEFAULT_WEIGHTS = {{"elo": {new_weights["elo"]}, '
        f'"poisson": {new_weights["poisson"]}, '
        f'"xgb": {new_weights["xgb"]}}}'
    )
    updated = text[: old_line.start()] + new_line + text[old_line.end() :]
    ensemble_path.write_text(updated, encoding="utf-8")
    logger.info("DEFAULT_WEIGHTS actualizado en src/ensemble.py: %s", new_weights)


# ── Main ──────────────────────────────────────────────────────────────────────

def main(apply: bool = False) -> None:
    from src.ensemble import DEFAULT_WEIGHTS

    played = load_played_wc2026()
    if len(played) < 5:
        logger.warning("Solo %d partidos jugados — muestra insuficiente para recalibrar.", len(played))
        return

    logger.info("Calculando predicciones por sub-modelo para %d partidos...", len(played))
    y_trues, elo_p, poi_p, xgb_p = get_per_model_predictions(played)

    # RPS individual
    rps_elo = _mean_rps(y_trues, elo_p)
    rps_poi = _mean_rps(y_trues, poi_p)
    rps_xgb = _mean_rps(y_trues, xgb_p)

    # RPS con pesos actuales
    current_w = DEFAULT_WEIGHTS
    current_blended = [
        _blend([e, p, x], [current_w["elo"], current_w["poisson"], current_w["xgb"]])
        for e, p, x in zip(elo_p, poi_p, xgb_p)
    ]
    rps_current = _mean_rps(y_trues, current_blended)

    # Grid search
    logger.info("Grid search de pesos (step=0.05)...")
    best_w, rps_best = grid_search_weights(y_trues, elo_p, poi_p, xgb_p, step=0.05)

    # Accuracy por sub-modelo
    def acc(probs_list):
        correct = sum(1 for y, p in zip(y_trues, probs_list) if np.argmax(p) == y)
        return correct / len(y_trues)

    print("\n" + "=" * 60)
    print(f"  CALIBRACIÓN ENSEMBLE — WC 2026 ({len(played)} partidos)")
    print("=" * 60)
    print(f"\n{'Modelo':<18} {'RPS':>8}  {'Acc':>7}")
    print("-" * 36)
    print(f"{'ELO-only':<18} {rps_elo:>8.4f}  {acc(elo_p):>6.1%}")
    print(f"{'Poisson-only':<18} {rps_poi:>8.4f}  {acc(poi_p):>6.1%}")
    print(f"{'XGB-only':<18} {rps_xgb:>8.4f}  {acc(xgb_p):>6.1%}")
    print("-" * 36)
    print(f"{'Ensemble actual':<18} {rps_current:>8.4f}  {acc(current_blended):>6.1%}")
    print(f"  pesos: elo={current_w['elo']} poi={current_w['poisson']} xgb={current_w['xgb']}")
    print(f"\n{'Ensemble óptimo':<18} {rps_best:>8.4f}")
    print(f"  pesos: elo={best_w['elo']} poi={best_w['poisson']} xgb={best_w['xgb']}")

    improvement = rps_current - rps_best
    THRESHOLD = 0.003
    print(f"\n  Mejora potencial: {improvement:+.4f} RPS")

    # Con solo 20 partidos, evitar cambios extremos: clip al 50% del camino hacia el óptimo
    conservative_w = {
        k: round(current_w[k] + 0.5 * (best_w[k] - current_w[k]), 2)
        for k in ("elo", "poisson", "xgb")
    }
    # Renormalizar a suma 1
    total = sum(conservative_w.values())
    conservative_w = {k: round(v / total, 2) for k, v in conservative_w.items()}
    cons_blended = [
        _blend([e, p, x], [conservative_w["elo"], conservative_w["poisson"], conservative_w["xgb"]])
        for e, p, x in zip(elo_p, poi_p, xgb_p)
    ]
    rps_conservative = _mean_rps(y_trues, cons_blended)
    print(f"  Ensemble conservador  {rps_conservative:>8.4f}")
    print(f"  pesos: elo={conservative_w['elo']} poi={conservative_w['poisson']} xgb={conservative_w['xgb']}")
    print(f"  (promedio entre actual y optimo — prudente con n=20)")

    if improvement > THRESHOLD:
        print(f"\n  [OK] Mejora > {THRESHOLD} — pesos conservadores recomendados")
        if apply:
            apply_weights_to_ensemble(conservative_w)
            print("  DEFAULT_WEIGHTS actualizado en src/ensemble.py")
            print("  Ejecuta: python scripts/run_pipeline.py && python scripts/export_frontend_data.py")
        else:
            print("  Usa --apply para escribirlos en ensemble.py")
    else:
        print(f"\n  [--] Mejora < {THRESHOLD} — pesos actuales son suficientes (n=20 es muestra pequena)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true",
                        help="Aplica los pesos óptimos a src/ensemble.py")
    args = parser.parse_args()
    main(apply=args.apply)
