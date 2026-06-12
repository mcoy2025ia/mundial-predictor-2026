"""App Streamlit: predictor + simulador + histórico del Mundial 2026."""
import json
import logging
import sys
from pathlib import Path

# Garantiza que la raíz del proyecto esté en sys.path.
# Streamlit agrega src/ al path al ejecutar src/app.py, no la raíz.
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

from typing import Optional

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.model import FEATURE_COLS, LABEL_MAP, load_model

DATA_PROCESSED = _ROOT_DIR / "data" / "processed"
DATA_RAW = _ROOT_DIR / "data" / "raw"
MODELS_DIR = _ROOT_DIR / "models"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LABEL_NAMES = {v: k for k, v in LABEL_MAP.items()}

st.set_page_config(
    page_title="Mundial 2026 Predictor",
    page_icon="⚽",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─── CSS ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
#MainMenu { visibility: hidden; }
footer { visibility: hidden; }

.wc-hero {
    background: linear-gradient(135deg, #C8102E 0%, #7B0D1E 40%, #003087 100%);
    border-radius: 16px;
    padding: 28px 32px 20px 32px;
    margin-bottom: 24px;
    text-align: center;
    color: white;
}
.wc-hero h1 { font-size: 2.2rem; font-weight: 900; margin: 0 0 6px 0; text-shadow: 2px 2px 4px rgba(0,0,0,0.4); }
.wc-hero p  { font-size: 0.9rem; opacity: 0.85; margin: 0; }

.team-card {
    border-radius: 12px;
    padding: 18px 14px;
    text-align: center;
    border: 1px solid rgba(200,16,46,0.35);
    background: linear-gradient(160deg, rgba(200,16,46,0.08) 0%, rgba(0,48,135,0.06) 100%);
}
.team-card .flag { font-size: 2.8rem; line-height: 1.1; }
.team-card .name { font-size: 1.15rem; font-weight: 700; margin: 6px 0 10px 0; }
.elo-badge {
    display: inline-block; background: #C8102E; color: white;
    border-radius: 20px; padding: 3px 13px; font-weight: 700; font-size: 0.95rem;
    margin-bottom: 8px;
}
.pred-result {
    border-radius: 10px; padding: 18px 14px; text-align: center;
    border: 2px solid #F5D300;
    background: linear-gradient(135deg, rgba(245,211,0,0.10) 0%, rgba(200,16,46,0.08) 100%);
    margin: 10px 0;
}
.pred-result .pct { font-size: 2rem; font-weight: 900; margin: 0; line-height: 1; }
.pred-result .label { font-size: 0.82rem; opacity: 0.75; margin-top: 3px; }

.group-card {
    border: 1px solid rgba(200,16,46,0.25);
    border-radius: 10px;
    padding: 14px;
    margin-bottom: 14px;
}
.group-title { font-weight: 800; font-size: 1rem; color: #C8102E; margin-bottom: 8px; }

/* Bracket de knockout */
.bracket-match {
    border: 1px solid rgba(200,16,46,0.3);
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 8px;
    background: rgba(0,48,135,0.04);
}
.bracket-winner { color: #22c55e; font-weight: 700; }
.bracket-loser  { opacity: 0.5; }

/* Responsive: móvil → columnas apiladas */
@media screen and (max-width: 640px) {
    div[data-testid="column"] {
        min-width: 100% !important;
        flex: 1 1 100% !important;
    }
    .wc-hero h1 { font-size: 1.5rem; }
    .pred-result .pct { font-size: 1.5rem; }
}

.h2h-win  { color: #22c55e; font-weight: 600; }
.h2h-draw { color: #f59e0b; font-weight: 600; }
.h2h-loss { color: #ef4444; font-weight: 600; }

.stat-box {
    text-align: center; padding: 14px 8px;
    border-radius: 10px; border: 1px solid rgba(200,16,46,0.2);
    background: rgba(200,16,46,0.06);
}
.stat-box .val { font-size: 1.8rem; font-weight: 900; color: #C8102E; line-height: 1; }
.stat-box .lbl { font-size: 0.78rem; opacity: 0.7; margin-top: 3px; }

.info-box {
    border-left: 4px solid #F5D300;
    background: rgba(245,211,0,0.06);
    border-radius: 0 8px 8px 0;
    padding: 10px 14px; margin: 10px 0;
    font-size: 0.88rem;
}
</style>
""", unsafe_allow_html=True)

# ─── Multi-idioma ────────────────────────────────────────────────────────────

STRINGS: dict = {
    "🇪🇸 Español": {
        "title": "⚽ Mundial 2026 — Predictor", "subtitle": "ELO · Machine Learning · Datos en vivo",
        "tab_pred": "🎯 Predictor", "tab_sim": "🏆 Simulador WC 2026", "tab_hist": "📊 Histórico",
        "team1": "Selección 1", "team2": "Selección 2", "btn": "⚡ Predecir",
        "wins1": "Gana la Sel. 1", "draw": "Empate", "wins2": "Gana la Sel. 2",
        "elo": "ELO", "elo_rank": "Ranking ELO", "wc_matches": "Partidos WC",
        "scored": "Goles/partido", "conceded": "Recibidos/partido",
        "h2h": "⚔️ Historial en Mundiales", "no_h2h": "Sin enfrentamientos previos en Mundiales",
        "date_col": "Fecha", "score_col": "Marcador",
        "probs": "📊 Probabilidades",
        "model_err": "Modelo no encontrado. Ejecuta el pipeline de entrenamiento primero.",
        "sim_title": "🏆 Simulador del torneo completo",
        "sim_desc": "Simula el Mundial entero con Monte Carlo — **{n:,} torneos** para calcular probabilidades reales.",
        "run_sim": "🎲 Simular torneo",
        "n_sim": "Número de simulaciones",
        "group_section": "Grupos y predicciones",
        "group_lbl": "Grupo",
        "champion_col": "Campeón",
        "qualify_col": "Clasifica (R32)",
        "r16_col": "Octavos",
        "qf_col": "Cuartos",
        "sf_col": "Semi",
        "final_col": "Final",
        "live_title": "📡 Resultados en vivo",
        "no_live": "El torneo arranca el 11 de junio. Vuelve para ver resultados en vivo.",
        "hist_wc_wins": "🏆 Títulos mundiales",
        "hist_goals": "⚽ Goles por torneo",
        "hist_best": "Mejores equipos históricos",
        "hist_top_scorers": "🥇 Máximos goleadores del Mundial",
        "model_info": "ℹ️ Sobre el modelo",
        "model_detail": (
            "El predictor usa un modelo **XGBoost calibrado** entrenado con "
            "**964 partidos** de fase final de Mundial (1930–2022).\n\n"
            "**Features usadas:**\n"
            "- `elo_diff` — diferencia de rating ELO (feature #1)\n"
            "- `wc_experience_diff` — partidos de WC previos\n"
            "- `home/away_goals_avg5` — goles promedio últimos 5 partidos\n"
            "- `h2h_home_win_pct` — historial H2H en Mundiales\n"
            "- `is_neutral` — 1 para sede neutral (siempre en WC)\n\n"
            "**Split temporal:** entrenado hasta 2018, evaluado en Qatar 2022."
        ),
        "wc_teams_note": "Solo se muestran los 48 clasificados al Mundial 2026",
        "neutral_note": "En el Mundial, todos los partidos se juegan en sede neutral",
        "vs_lbl": "VS",
        "tab_glos": "📖 Glosario",
        "tab_curiosos": "🤩 Curiosidades",
        "curiosos_title": "Curiosidades del fútbol mundial (1930–2022)",
        "rec_mas_goles_ed": "Edición más goleadora",
        "rec_avg_goles_max": "Mayor promedio goles/partido",
        "rec_partido_goles": "Partido con más goles",
        "rec_goleada_max": "Mayor goleada",
        "curiosos_avg_label": "Promedio de goles/partido por edición del Mundial",
        "curiosos_era_title": "Resultados por década: ¿cada vez menos goles?",
        "curiosos_goals_title": "🎯 Equipos más goleadores en Mundiales",
        "curiosos_upsets_title": "💥 Las 10 mayores sorpresas basadas en ELO",
        "curiosos_facts_title": "🤯 ¿Sabías que...?",
        "curiosos_col_title": "🇨🇴 Colombia en cifras",
        "curiosos_home_win_lbl": "Gana el local",
        "curiosos_draw_lbl": "Empate",
        "curiosos_away_win_lbl": "Gana el visitante",
        "curiosos_decade_lbl": "Década",
        "curiosos_goals_team": "Equipo",
        "curiosos_goals_gf": "Goles a favor",
        "curiosos_goals_ga": "Goles en contra",
        "curiosos_goals_diff": "Diferencia",
        "curiosos_goals_matches": "Partidos",
        "curiosos_goals_avg": "Goles/partido",
        "curiosos_upsets_date": "Año",
        "curiosos_upsets_match": "Partido",
        "curiosos_upsets_score": "Marcador",
        "curiosos_upsets_favored": "Favorito (ELO)",
        "curiosos_upsets_winner": "Ganador sorpresa",
        "curiosos_upsets_diff": "Ventaja ELO desaprovechada",
    },
    "🇬🇧 English": {
        "title": "⚽ World Cup 2026 — Predictor", "subtitle": "ELO · Machine Learning · Live Data",
        "tab_pred": "🎯 Predictor", "tab_sim": "🏆 WC 2026 Simulator", "tab_hist": "📊 History",
        "team1": "Team 1", "team2": "Team 2", "btn": "⚡ Predict",
        "wins1": "Team 1 wins", "draw": "Draw", "wins2": "Team 2 wins",
        "elo": "ELO", "elo_rank": "ELO Rank", "wc_matches": "WC matches",
        "scored": "Goals/game", "conceded": "Conceded/game",
        "h2h": "⚔️ World Cup H2H History", "no_h2h": "No previous World Cup meetings",
        "date_col": "Date", "score_col": "Score",
        "probs": "📊 Probabilities",
        "model_err": "Model not found. Run the training pipeline first.",
        "sim_title": "🏆 Full tournament simulator",
        "sim_desc": "Simulates the entire World Cup with Monte Carlo — **{n:,} tournaments** for accurate probabilities.",
        "run_sim": "🎲 Simulate tournament",
        "n_sim": "Number of simulations",
        "group_section": "Groups & predictions",
        "group_lbl": "Group",
        "champion_col": "Champion",
        "qualify_col": "Qualify (R32)",
        "r16_col": "Round of 16",
        "qf_col": "Quarter-final",
        "sf_col": "Semi-final",
        "final_col": "Final",
        "live_title": "📡 Live results",
        "no_live": "Tournament starts June 11. Come back for live results.",
        "hist_wc_wins": "🏆 World Cup titles",
        "hist_goals": "⚽ Goals per tournament",
        "hist_best": "Most successful teams historically",
        "hist_top_scorers": "🥇 All-time top scorers",
        "model_info": "ℹ️ About the model",
        "model_detail": (
            "This predictor uses a **calibrated XGBoost model** trained on "
            "**964 World Cup matches** (1930–2022).\n\n"
            "**Features:**\n"
            "- `elo_diff` — ELO rating difference (top feature)\n"
            "- `wc_experience_diff` — prior WC matches played\n"
            "- `home/away_goals_avg5` — avg goals last 5 matches\n"
            "- `h2h_home_win_pct` — H2H win % at World Cups\n"
            "- `is_neutral` — 1 for neutral venue (always in WC)\n\n"
            "**Temporal split:** trained up to 2018, evaluated on Qatar 2022."
        ),
        "wc_teams_note": "Only the 48 qualified teams for World Cup 2026 are shown",
        "neutral_note": "All World Cup matches are played at neutral venues",
        "vs_lbl": "VS",
        "tab_glos": "📖 Glossary",
        "tab_curiosos": "🤩 Fun Facts",
        "curiosos_title": "World Cup Fun Facts & Stats (1930–2022)",
        "rec_mas_goles_ed": "Most goals in an edition",
        "rec_avg_goles_max": "Highest avg goals/match",
        "rec_partido_goles": "Highest-scoring match",
        "rec_goleada_max": "Biggest victory margin",
        "curiosos_avg_label": "Average goals/match per World Cup edition",
        "curiosos_era_title": "Results by decade: is football becoming more defensive?",
        "curiosos_goals_title": "🎯 Top scoring teams in World Cups",
        "curiosos_upsets_title": "💥 Top 10 biggest upsets by ELO",
        "curiosos_facts_title": "🤯 Did you know...?",
        "curiosos_col_title": "🇨🇴 Colombia in numbers",
        "curiosos_home_win_lbl": "Home wins",
        "curiosos_draw_lbl": "Draws",
        "curiosos_away_win_lbl": "Away wins",
        "curiosos_decade_lbl": "Decade",
        "curiosos_goals_team": "Team",
        "curiosos_goals_gf": "Goals scored",
        "curiosos_goals_ga": "Goals conceded",
        "curiosos_goals_diff": "Difference",
        "curiosos_goals_matches": "Matches",
        "curiosos_goals_avg": "Goals/match",
        "curiosos_upsets_date": "Year",
        "curiosos_upsets_match": "Match",
        "curiosos_upsets_score": "Score",
        "curiosos_upsets_favored": "Favourite (ELO)",
        "curiosos_upsets_winner": "Surprise winner",
        "curiosos_upsets_diff": "ELO advantage wasted",
    },
    "🇧🇷 Português": {
        "title": "⚽ Copa do Mundo 2026 — Preditor", "subtitle": "ELO · Machine Learning · Dados em tempo real",
        "tab_pred": "🎯 Preditor", "tab_sim": "🏆 Simulador Copa 2026", "tab_hist": "📊 Histórico",
        "team1": "Seleção 1", "team2": "Seleção 2", "btn": "⚡ Prever",
        "wins1": "Sel. 1 vence", "draw": "Empate", "wins2": "Sel. 2 vence",
        "elo": "ELO", "elo_rank": "Ranking ELO", "wc_matches": "Jogos na Copa",
        "scored": "Gols/jogo", "conceded": "Sofridos/jogo",
        "h2h": "⚔️ Histórico H2H em Copas", "no_h2h": "Sem confrontos em Copas do Mundo",
        "date_col": "Data", "score_col": "Placar",
        "probs": "📊 Probabilidades",
        "model_err": "Modelo não encontrado. Execute o pipeline de treinamento primeiro.",
        "sim_title": "🏆 Simulador do torneio completo",
        "sim_desc": "Simula a Copa inteira com Monte Carlo — **{n:,} torneios** para probabilidades reais.",
        "run_sim": "🎲 Simular torneio",
        "n_sim": "Número de simulações",
        "group_section": "Grupos e previsões",
        "group_lbl": "Grupo",
        "champion_col": "Campeão",
        "qualify_col": "Classifica (R32)",
        "r16_col": "Oitavas",
        "qf_col": "Quartas",
        "sf_col": "Semi",
        "final_col": "Final",
        "live_title": "📡 Resultados em tempo real",
        "no_live": "O torneio começa em 11 de junho. Volte para ver resultados ao vivo.",
        "hist_wc_wins": "🏆 Títulos mundiais",
        "hist_goals": "⚽ Gols por torneio",
        "hist_best": "Melhores times históricos",
        "hist_top_scorers": "🥇 Artilheiros históricos",
        "model_info": "ℹ️ Sobre o modelo",
        "model_detail": (
            "Este preditor usa um modelo **XGBoost calibrado** treinado com "
            "**964 jogos** de Copa do Mundo (1930–2022).\n\n"
            "**Features:**\n"
            "- `elo_diff` — diferença de rating ELO (feature #1)\n"
            "- `wc_experience_diff` — partidas de Copa anteriores\n"
            "- `home/away_goals_avg5` — média de gols últimos 5 jogos\n"
            "- `h2h_home_win_pct` — % vitórias no H2H em Copas\n"
            "- `is_neutral` — 1 para local neutro (sempre na Copa)\n\n"
            "**Split temporal:** treinado até 2018, avaliado no Qatar 2022."
        ),
        "wc_teams_note": "Apenas os 48 classificados para a Copa do Mundo 2026 são exibidos",
        "neutral_note": "Todos os jogos da Copa são em local neutro",
        "vs_lbl": "VS",
        "tab_glos": "📖 Glossário",
        "tab_curiosos": "🤩 Curiosidades",
        "curiosos_title": "Curiosidades do futebol mundial (1930–2022)",
        "rec_mas_goles_ed": "Edição mais goleadora",
        "rec_avg_goles_max": "Maior média gols/jogo",
        "rec_partido_goles": "Jogo com mais gols",
        "rec_goleada_max": "Maior goleada",
        "curiosos_avg_label": "Média de gols/jogo por edição da Copa",
        "curiosos_era_title": "Resultados por década: futebol defensivo?",
        "curiosos_goals_title": "🎯 Seleções mais goleadoras nas Copas",
        "curiosos_upsets_title": "💥 As 10 maiores surpresas por ELO",
        "curiosos_facts_title": "🤯 Você sabia...?",
        "curiosos_col_title": "🇨🇴 Colômbia em números",
        "curiosos_home_win_lbl": "Vitória mandante",
        "curiosos_draw_lbl": "Empate",
        "curiosos_away_win_lbl": "Vitória visitante",
        "curiosos_decade_lbl": "Década",
        "curiosos_goals_team": "Seleção",
        "curiosos_goals_gf": "Gols marcados",
        "curiosos_goals_ga": "Gols sofridos",
        "curiosos_goals_diff": "Saldo",
        "curiosos_goals_matches": "Jogos",
        "curiosos_goals_avg": "Gols/jogo",
        "curiosos_upsets_date": "Ano",
        "curiosos_upsets_match": "Jogo",
        "curiosos_upsets_score": "Placar",
        "curiosos_upsets_favored": "Favorito (ELO)",
        "curiosos_upsets_winner": "Surpresa vencedora",
        "curiosos_upsets_diff": "Vantagem ELO desperdiçada",
    },
}

TEAM_FLAGS: dict = {
    "Argentina": "🇦🇷", "Brazil": "🇧🇷", "Colombia": "🇨🇴",
    "France": "🇫🇷", "Germany": "🇩🇪", "West Germany": "🇩🇪",
    "Spain": "🇪🇸", "England": "🏴󠁧󠁢󠁥󠁮󠁧󁿢", "Italy": "🇮🇹",
    "Mexico": "🇲🇽", "Portugal": "🇵🇹", "Netherlands": "🇳🇱",
    "Uruguay": "🇺🇾", "Belgium": "🇧🇪", "Croatia": "🇭🇷",
    "Senegal": "🇸🇳", "Morocco": "🇲🇦", "Japan": "🇯🇵",
    "South Korea": "🇰🇷", "Australia": "🇦🇺", "United States": "🇺🇸",
    "Canada": "🇨🇦", "Ecuador": "🇪🇨", "Peru": "🇵🇪",
    "Chile": "🇨🇱", "Paraguay": "🇵🇾", "Bolivia": "🇧🇴",
    "Venezuela": "🇻🇪", "Poland": "🇵🇱", "Switzerland": "🇨🇭",
    "Denmark": "🇩🇰", "Sweden": "🇸🇪", "Norway": "🇳🇴",
    "Austria": "🇦🇹", "Czech Republic": "🇨🇿", "Serbia": "🇷🇸",
    "Hungary": "🇭🇺", "Romania": "🇷🇴", "Ukraine": "🇺🇦",
    "Turkey": "🇹🇷", "Russia": "🇷🇺", "Soviet Union": "🇷🇺",
    "Saudi Arabia": "🇸🇦", "Iran": "🇮🇷", "Qatar": "🇶🇦",
    "Nigeria": "🇳🇬", "Ghana": "🇬🇭", "Cameroon": "🇨🇲",
    "Tunisia": "🇹🇳", "Egypt": "🇪🇬", "Algeria": "🇩🇿",
    "South Africa": "🇿🇦", "Ivory Coast": "🇨🇮",
    "Uzbekistan": "🇺🇿", "DR Congo": "🇨🇩",
    "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󁿢", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󁿢",
    "Costa Rica": "🇨🇷", "Honduras": "🇭🇳", "Jamaica": "🇯🇲",
    "Panama": "🇵🇦", "Greece": "🇬🇷", "Bulgaria": "🇧🇬",
    "Slovakia": "🇸🇰", "Czechoslovakia": "🇨🇿", "Yugoslavia": "🇷🇸",
    "North Korea": "🇰🇵", "Israel": "🇮🇱", "New Zealand": "🇳🇿",
    "Cuba": "🇨🇺", "Haiti": "🇭🇹", "Bosnia and Herzegovina": "🇧🇦",
    "Jordan": "🇯🇴", "Iraq": "🇮🇶", "Cape Verde": "🇨🇻",
    "Curacao": "🇨🇼",
}


def flag(team: str) -> str:
    return TEAM_FLAGS.get(team, "🏳️")


# ─── Carga de datos ──────────────────────────────────────────────────────────

@st.cache_resource
def get_model():
    return load_model(MODELS_DIR / "xgb_calibrated.pkl")


@st.cache_resource
def get_prediction_caches(_model):
    """
    Pre-computa UNA SOLA VEZ al iniciar:
      1. team_stats  — stats de cada equipo (O(1) lookup)
      2. h2h_stats   — H2H win% pre-calculado (O(1) lookup)
      3. probs_cache — probabilidades de los 1128 pares WC en un batch

    Sin este caché: ~90 min para 1000 sims.
    Con él: ~2 segundos.
    """
    from src.simulator import (
        build_team_stats, build_h2h_stats,
        precompute_match_probs, WC2026_TEAMS,
    )
    import time
    df_f = get_features()
    elos = get_elo_ratings()

    t0 = time.perf_counter()
    team_stats = build_team_stats(df_f, elos)
    h2h_stats = build_h2h_stats(df_f, WC2026_TEAMS)
    probs_cache = precompute_match_probs(_model, team_stats, h2h_stats, WC2026_TEAMS)
    logger.info("Caches pre-computados en %.2fs — %d pares", time.perf_counter() - t0, len(probs_cache) // 2)
    return team_stats, h2h_stats, probs_cache


@st.cache_data
def get_features() -> pd.DataFrame:
    return pd.read_parquet(DATA_PROCESSED / "features.parquet")


@st.cache_data
def get_wc_matches() -> pd.DataFrame:
    df = pd.read_csv(DATA_PROCESSED / "wc_clean.csv", parse_dates=["date"])
    return df[["date", "home_team", "away_team", "home_score", "away_score", "outcome"]].dropna()


@st.cache_data
def get_elo_ratings() -> dict:
    with open(DATA_PROCESSED / "elo_current.json") as f:
        return json.load(f)


@st.cache_data
def get_goalscorers() -> pd.DataFrame:
    path = DATA_RAW / "goalscorers.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=["date"])
    return df


@st.cache_data(ttl=3600)
def get_live_fixture() -> list:
    from src.simulator import fetch_live_fixture
    return fetch_live_fixture()


@st.cache_resource
def get_shootout_stats() -> dict:
    """Historial de tandas de penales por equipo (para tiebreaker en knockout)."""
    from src.extractor import load_shootouts
    from src.simulator import build_shootout_stats
    try:
        return build_shootout_stats(load_shootouts())
    except FileNotFoundError:
        return {}


# ─── Helpers de predicción ────────────────────────────────────────────────────

def get_team_features(df_features: pd.DataFrame, team: str) -> dict:
    mask = (df_features["home_team"] == team) | (df_features["away_team"] == team)
    rows = df_features[mask].sort_values("date")
    if rows.empty:
        return {"goals_scored": 1.5, "goals_conceded": 1.2, "wc_matches": 0}
    last = rows.iloc[-1]
    if last["home_team"] == team:
        scored, conceded = last["home_goals_scored_avg5"], last["home_goals_conceded_avg5"]
    else:
        scored, conceded = last["away_goals_scored_avg5"], last["away_goals_conceded_avg5"]
    return {"goals_scored": round(float(scored), 2), "goals_conceded": round(float(conceded), 2), "wc_matches": len(rows)}


def calc_h2h_win_pct(df_features: pd.DataFrame, home: str, away: str) -> float:
    mask = (
        ((df_features["home_team"] == home) & (df_features["away_team"] == away)) |
        ((df_features["home_team"] == away) & (df_features["away_team"] == home))
    )
    h2h = df_features[mask]
    if h2h.empty:
        return 0.5
    wins = (
        ((h2h["home_team"] == home) & (h2h["outcome"] == "home_win")).sum() +
        ((h2h["home_team"] == away) & (h2h["outcome"] == "away_win")).sum()
    )
    return float(wins) / len(h2h)


def build_prediction_row(
    home: str, away: str, neutral: bool,
    elo_ratings: dict, df_features: pd.DataFrame,
    team_stats: Optional[dict] = None,
    h2h_stats: Optional[dict] = None,
) -> pd.DataFrame:
    """Construye la fila de features para predict_proba.
    Si se pasan team_stats / h2h_stats (pre-computados) es O(1); si no, hace pandas scans.
    """
    if team_stats:
        s_h = team_stats.get(home, {})
        s_a = team_stats.get(away, {})
        elo_home = s_h.get("elo", elo_ratings.get(home, 1500.0))
        elo_away = s_a.get("elo", elo_ratings.get(away, 1500.0))
        gs_h = s_h.get("goals_scored", 1.5);  gc_h = s_h.get("goals_conceded", 1.2)
        gs_a = s_a.get("goals_scored", 1.5);  gc_a = s_a.get("goals_conceded", 1.2)
        n_h = s_h.get("wc_matches", 0);       n_a = s_a.get("wc_matches", 0)
        h2h_pct = (h2h_stats or {}).get((home, away), 0.5)
    else:
        elo_home = elo_ratings.get(home, 1500.0)
        elo_away = elo_ratings.get(away, 1500.0)
        stats_h = get_team_features(df_features, home)
        stats_a = get_team_features(df_features, away)
        gs_h = stats_h["goals_scored"];  gc_h = stats_h["goals_conceded"]
        gs_a = stats_a["goals_scored"];  gc_a = stats_a["goals_conceded"]
        n_h = stats_h["wc_matches"];     n_a = stats_a["wc_matches"]
        h2h_pct = calc_h2h_win_pct(df_features, home, away)

    return pd.DataFrame([{
        "elo_diff": elo_home - elo_away,
        "elo_home": elo_home, "elo_away": elo_away,
        "home_goals_scored_avg5": gs_h, "home_goals_conceded_avg5": gc_h,
        "away_goals_scored_avg5": gs_a, "away_goals_conceded_avg5": gc_a,
        "h2h_home_win_pct": h2h_pct,
        "is_neutral": int(neutral),
        "wc_experience_diff": n_h - n_a,
    }])


# ─── Gráficas ─────────────────────────────────────────────────────────────────

def donut_chart(p1: float, draw: float, p2: float, l1: str, l2: str, lbl_draw: str) -> go.Figure:
    colors = ["#C8102E", "#888888", "#003087"]
    fig = go.Figure(go.Pie(
        labels=[l1, lbl_draw, l2],
        values=[p1, draw, p2],
        hole=0.58,
        marker=dict(colors=colors, line=dict(color="#111", width=2)),
        textinfo="label+percent",
        textfont_size=12,
        hovertemplate="%{label}: %{percent}<extra></extra>",
    ))
    fig.update_layout(
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=10, b=10, l=10, r=10),
        height=240,
    )
    return fig


# ─── TAB 1: Predictor ────────────────────────────────────────────────────────

def tab_predictor(model, df_features, df_wc, elo_ratings, T, team_stats=None, h2h_stats=None, probs_cache=None):
    from src.simulator import WC2026_TEAMS

    st.markdown(f"""<div class="info-box">
    {T['wc_teams_note']}. {T['neutral_note']}.
    </div>""", unsafe_allow_html=True)

    wc_teams_sorted = sorted(WC2026_TEAMS)
    col_idx = wc_teams_sorted.index("Colombia") if "Colombia" in wc_teams_sorted else 0
    arg_idx = wc_teams_sorted.index("Argentina") if "Argentina" in wc_teams_sorted else 1

    c1, cv, c2 = st.columns([5, 1, 5])
    with c1:
        t1 = st.selectbox(T["team1"], wc_teams_sorted, index=col_idx)
    with cv:
        st.markdown(f"<div style='text-align:center;padding-top:32px;font-weight:900;font-size:1.2rem;opacity:0.4;'>{T['vs_lbl']}</div>", unsafe_allow_html=True)
    with c2:
        t2 = st.selectbox(T["team2"], wc_teams_sorted, index=arg_idx)

    st.markdown("---")

    # Cards de equipo
    elo_sorted_names = list(elo_ratings.keys())
    rank1 = elo_sorted_names.index(t1) + 1 if t1 in elo_sorted_names else "—"
    rank2 = elo_sorted_names.index(t2) + 1 if t2 in elo_sorted_names else "—"

    # Usar caché pre-computado si está disponible (O(1)), si no recalcular (lento)
    if team_stats:
        _def = {"elo": 1500, "goals_scored": 1.5, "goals_conceded": 1.2, "wc_matches": 0}
        _s1 = team_stats.get(t1, _def)
        _s2 = team_stats.get(t2, _def)
        elo1 = _s1["elo"]; elo2 = _s2["elo"]
        s1 = {"goals_scored": _s1["goals_scored"], "goals_conceded": _s1["goals_conceded"], "wc_matches": _s1["wc_matches"]}
        s2 = {"goals_scored": _s2["goals_scored"], "goals_conceded": _s2["goals_conceded"], "wc_matches": _s2["wc_matches"]}
    else:
        elo1 = elo_ratings.get(t1, 1500)
        elo2 = elo_ratings.get(t2, 1500)
        s1 = get_team_features(df_features, t1)
        s2 = get_team_features(df_features, t2)

    ca, cb = st.columns(2)
    for col, team, elo, rank, stats in [(ca, t1, elo1, rank1, s1), (cb, t2, elo2, rank2, s2)]:
        with col:
            st.markdown(f"""
            <div class="team-card">
              <div class="flag">{flag(team)}</div>
              <div class="name">{team}</div>
              <span class="elo-badge">{T['elo']} {elo:.0f} &nbsp;·&nbsp; #{rank}</span><br><br>
              <b>{T['scored']}</b> {stats['goals_scored']:.2f} &nbsp;|&nbsp;
              <b>{T['conceded']}</b> {stats['goals_conceded']:.2f}<br>
              <small style="opacity:0.6">{stats['wc_matches']} {T['wc_matches']}</small>
            </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    if st.button(T["btn"], use_container_width=True, type="primary"):
        # Usar caché si disponible (instantáneo), si no calcular
        if probs_cache and (t1, t2) in probs_cache:
            _p = probs_cache[(t1, t2)]
            p1, pd_, p2 = _p["team1_win"], _p["draw"], _p["team2_win"]
        else:
            row = build_prediction_row(t1, t2, True, elo_ratings, df_features, team_stats, h2h_stats)
            proba = model.predict_proba(row[FEATURE_COLS])[0]
            p1, pd_, p2 = float(proba[0]), float(proba[1]), float(proba[2])

        st.markdown(f"#### {T['probs']}")
        ch, cn = st.columns([3, 2])
        with ch:
            st.plotly_chart(
                donut_chart(p1, pd_, p2, f"{flag(t1)} {T['wins1']}", f"{T['wins2']} {flag(t2)}", T["draw"]),
                use_container_width=True,
            )
        with cn:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown(f"""
            <div class="pred-result">
              <div class="pct" style="color:#C8102E">{p1:.1%}</div>
              <div class="label">{flag(t1)} {t1}</div>
            </div>
            <div class="pred-result" style="border-color:#aaa">
              <div class="pct" style="color:#888">{pd_:.1%}</div>
              <div class="label">{T['draw']}</div>
            </div>
            <div class="pred-result" style="border-color:#003087">
              <div class="pct" style="color:#003087">{p2:.1%}</div>
              <div class="label">{flag(t2)} {t2}</div>
            </div>""", unsafe_allow_html=True)

    # H2H
    st.markdown(f"#### {T['h2h']}")
    mask = (
        ((df_wc["home_team"] == t1) & (df_wc["away_team"] == t2)) |
        ((df_wc["home_team"] == t2) & (df_wc["away_team"] == t1))
    )
    h2h = df_wc[mask].sort_values("date", ascending=False).head(5)
    if h2h.empty:
        st.info(T["no_h2h"])
    else:
        for _, row in h2h.iterrows():
            score = f"{int(row['home_score'])}–{int(row['away_score'])}"
            if row["outcome"] == "home_win":
                winner, css = row["home_team"], ("h2h-win" if row["home_team"] == t1 else "h2h-loss")
            elif row["outcome"] == "draw":
                winner, css = T["draw"], "h2h-draw"
            else:
                winner, css = row["away_team"], ("h2h-win" if row["away_team"] == t1 else "h2h-loss")
            st.markdown(
                f"`{row['date'].strftime('%d %b %Y')}` — "
                f"{flag(row['home_team'])} **{row['home_team']}** {score} **{row['away_team']}** {flag(row['away_team'])} "
                f"&nbsp;→&nbsp; <span class='{css}'>{flag(winner)} {winner}</span>",
                unsafe_allow_html=True,
            )

    # Explicación del modelo
    with st.expander(T["model_info"]):
        st.markdown(T["model_detail"])


# ─── TAB 2: Simulador WC 2026 ────────────────────────────────────────────────

def _group_card(group_name, teams, model, elo_ratings, df_features, live_matches, T, probs_cache=None):
    """Muestra una tarjeta de grupo con equipos y tabla de posiciones en vivo o predicha."""
    from src.simulator import get_group_live_standings, predict_match

    live_standing = get_group_live_standings(live_matches, f"Group {group_name}")

    with st.container():
        teams_flags = "  ".join(f"{flag(t)} {t}" for t in teams)
        st.markdown(f"<div class='group-card'><div class='group-title'>Grupo {group_name}</div>{teams_flags}</div>", unsafe_allow_html=True)

    if live_standing is not None:
        st.dataframe(live_standing, use_container_width=True, hide_index=True)
    else:
        # Tabla de ELOs para este grupo
        elo_rows = [{"Equipo": f"{flag(t)} {t}", "ELO": round(elo_ratings.get(t, 1500), 0)} for t in teams]
        st.dataframe(pd.DataFrame(elo_rows), use_container_width=True, hide_index=True)

    # Partidos del grupo con probabilidades
    with st.expander(f"Partidos del Grupo {group_name}"):
        matches = []
        for i, t1 in enumerate(teams):
            for t2 in teams[i + 1:]:
                p = predict_match(model, t1, t2, elo_ratings, df_features, probs_cache)
                # Buscar si ya se jugó
                played = next(
                    (m for m in live_matches
                     if m.get("group") == f"Group {group_name}"
                     and {m["team1"], m["team2"]} == {t1, t2}
                     and m.get("score1") is not None),
                    None,
                )
                if played:
                    score_str = f"**{int(played['score1'])}–{int(played['score2'])}** ✅"
                    prob_str = ""
                else:
                    score_str = "—"
                    prob_str = (
                        f"{flag(t1)} {p['team1_win']:.0%}  |  "
                        f"Empate {p['draw']:.0%}  |  "
                        f"{p['team2_win']:.0%} {flag(t2)}"
                    )
                matches.append({
                    "Partido": f"{flag(t1)} {t1}  vs  {flag(t2)} {t2}",
                    "Marcador": score_str,
                    "Pronóstico (Sel1 | Emp | Sel2)": prob_str,
                })
        st.dataframe(pd.DataFrame(matches), use_container_width=True, hide_index=True)


def tab_simulator(model, df_features, elo_ratings, T, probs_cache=None):
    from src.simulator import (
        WC2026_GROUPS, WC2026_TEAMS, build_fixed_results,
        monte_carlo, simulate_deterministic_tournament,
    )

    live_matches = get_live_fixture()
    played = [m for m in live_matches if m.get("score1") is not None]
    fixed_results = build_fixed_results(live_matches)
    shootout_stats = get_shootout_stats()

    # ── Estado del torneo ───────────────────────────────────────────────────
    if played:
        st.success(
            f"📡 {len(played)} partido(s) jugado(s). Las simulaciones fijan esos "
            f"resultados reales: las probabilidades son condicionales a lo que ya pasó."
        )
    else:
        st.info(T["no_live"])

    # ── Grupos — filtro + 2 columnas ────────────────────────────────────────
    st.markdown(f"### {T['group_section']}")

    fc1, fc2 = st.columns([1, 2])
    with fc1:
        group_options = ["Todos"] + [f"Grupo {g}" for g in sorted(WC2026_GROUPS.keys())]
        group_sel = st.selectbox("🔍 Filtrar por grupo", group_options, index=0)
    with fc2:
        team_search = st.text_input("🔍 Buscar equipo", placeholder="ej: Colombia, España, Brasil…")

    # Aplicar filtros
    if team_search.strip():
        q = team_search.strip().lower()
        filtered_groups = {g: ts for g, ts in WC2026_GROUPS.items()
                           if any(q in t.lower() for t in ts)}
    elif group_sel != "Todos":
        gkey = group_sel.split(" ")[-1]
        filtered_groups = {gkey: WC2026_GROUPS[gkey]}
    else:
        filtered_groups = WC2026_GROUPS

    if not filtered_groups:
        st.warning("No se encontró ningún equipo con ese nombre.")
    else:
        items = list(filtered_groups.items())
        for i in range(0, len(items), 2):
            row_cols = st.columns(2)
            for j, (gname, teams) in enumerate(items[i : i + 2]):
                with row_cols[j]:
                    _group_card(gname, teams, model, elo_ratings, df_features, live_matches, T, probs_cache)

    st.divider()

    # ── Bracket eliminatorio (determinista) ─────────────────────────────────
    st.markdown("### 🗓️ Bracket eliminatorio — camino más probable")
    st.caption("Muestra el resultado más probable en cada partido, comenzando desde los grupos. No es el único escenario posible.")

    if st.button("📋 Generar bracket", type="secondary"):
        with st.spinner("Calculando bracket…"):
            bracket_rounds, group_standings = simulate_deterministic_tournament(
                model, elo_ratings, df_features, probs_cache=probs_cache
            )

        # Clasificados de grupos
        with st.expander("👥 Clasificados proyectados de fase de grupos", expanded=False):
            rows = []
            for gname, standing in sorted(group_standings.items()):
                for pos, team in enumerate(standing, 1):
                    label = "Clasifica" if pos <= 2 else ("Mejor 3°?" if pos == 3 else "Eliminado")
                    rows.append({"Grupo": gname, "Pos.": pos, "Equipo": f"{flag(team)} {team}", "Estado": label})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

        # Rondas de knockout
        round_icons = {
            "Ronda de 32": "⚡ Ronda de 32 (32 → 16)",
            "Octavos de final": "🔥 Octavos de final (16 → 8)",
            "Cuartos de final": "💥 Cuartos de final (8 → 4)",
            "Semifinal": "⭐ Semifinales (4 → 2)",
            "Final": "🏆 Final",
        }
        for round_name, matches in bracket_rounds.items():
            if not matches:
                continue
            st.markdown(f"#### {round_icons.get(round_name, round_name)}")
            cols_per_row = 2 if round_name not in ("Semifinal", "Final") else 2
            for i in range(0, len(matches), cols_per_row):
                row_c = st.columns(cols_per_row)
                for j, m in enumerate(matches[i : i + cols_per_row]):
                    with row_c[j]:
                        t1, t2 = m["team1"], m["team2"]
                        p = m["probs"]
                        winner = m["winner"]
                        loser = t2 if winner == t1 else t1
                        w_p = p["team1_win"] if winner == t1 else p["team2_win"]
                        st.markdown(f"""
<div class="bracket-match">
  <span class="bracket-winner">{flag(winner)} {winner} ✓</span> &nbsp;<small style="opacity:.6">{w_p:.0%}</small><br>
  <span class="bracket-loser">{flag(loser)} {loser}</span> &nbsp;<small style="opacity:.45">{1-w_p-p['draw']:.0%}</small>
  <div style="font-size:0.75rem;opacity:0.5;margin-top:4px">Empate: {p['draw']:.0%}</div>
</div>""", unsafe_allow_html=True)

    st.divider()

    # ── Monte Carlo ─────────────────────────────────────────────────────────
    st.markdown(f"### {T['sim_title']}")

    n_sim = st.select_slider(T["n_sim"], options=[500, 1000, 2000, 5000, 10000], value=1000)
    st.markdown(T["sim_desc"].format(n=n_sim))

    if st.button(T["run_sim"], type="primary"):
        with st.spinner("Simulando torneos…"):
            df_mc = monte_carlo(
                model, elo_ratings, df_features, n=n_sim, probs_cache=probs_cache,
                shootout_stats=shootout_stats, fixed_results=fixed_results,
            )

        # Tabla completa
        cols_map = {
            "equipo": "Equipo", "grupo": T["group_lbl"], "elo": T["elo"],
            "Ronda de 32": T["qualify_col"], "Octavos de final": T["r16_col"],
            "Cuartos de final": T["qf_col"], "Semifinal": T["sf_col"],
            "Final": T["final_col"], "Campeón": T["champion_col"],
        }
        df_show = df_mc[[c for c in cols_map if c in df_mc.columns]].rename(columns=cols_map)
        df_show["Equipo"] = df_show["Equipo"].apply(lambda t: f"{flag(t)} {t}")
        pct_cols = [T["qualify_col"], T["r16_col"], T["qf_col"], T["sf_col"], T["final_col"], T["champion_col"]]
        for c in pct_cols:
            if c in df_show.columns:
                df_show[c] = df_show[c].apply(lambda x: f"{x:.1%}")
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # Gráfico top 15
        df_chart = df_mc.head(15).copy()
        df_chart["label"] = df_chart["equipo"].apply(lambda t: f"{flag(t)} {t}")
        df_chart["color"] = df_chart["equipo"].apply(lambda t: "#F5D300" if t == "Colombia" else "#C8102E")
        fig = go.Figure(go.Bar(
            x=df_chart["Campeón"], y=df_chart["label"], orientation="h",
            marker_color=df_chart["color"].tolist(),
            text=df_chart["Campeón"].apply(lambda x: f"{x:.1%}"),
            textposition="outside",
        ))
        fig.update_layout(
            title="Top 15 — % de ganar el torneo",
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=40, b=10, l=10, r=60), height=420,
            xaxis=dict(showgrid=False, showticklabels=False),
            yaxis=dict(autorange="reversed"),
        )
        st.plotly_chart(fig, use_container_width=True)

        # Colombia highlight
        if "Colombia" in df_mc["equipo"].values:
            cr = df_mc[df_mc["equipo"] == "Colombia"].iloc[0]
            pos = df_mc.index[df_mc["equipo"] == "Colombia"][0] + 1
            st.markdown(f"""<div class="info-box">
            🇨🇴 <b>Colombia</b> — #{pos} en probabilidad de título &nbsp;·&nbsp; ELO {cr['elo']:.0f}<br>
            Clasifica: <b>{cr.get('Ronda de 32', 0):.1%}</b> &nbsp;·&nbsp;
            Octavos: <b>{cr.get('Octavos de final', 0):.1%}</b> &nbsp;·&nbsp;
            Final: <b>{cr.get('Final', 0):.1%}</b> &nbsp;·&nbsp;
            Campeón: <b>{cr.get('Campeón', 0):.1%}</b>
            </div>""", unsafe_allow_html=True)


# ─── TAB 3: Histórico ────────────────────────────────────────────────────────

def tab_historico(df_wc, df_goalscorers, T):
    st.markdown("### 🏆 Estadísticas históricas del Mundial (1930–2022)")

    # ── Métricas globales ───────────────────────────────────────────────────
    total_matches = len(df_wc)
    total_goals = int(df_wc["home_score"].sum() + df_wc["away_score"].sum())
    editions = df_wc["date"].dt.year.nunique()
    avg_goals = total_goals / total_matches if total_matches else 0

    c1, c2, c3, c4 = st.columns(4)
    for col, val, lbl in [
        (c1, editions, "Ediciones"),
        (c2, total_matches, "Partidos totales"),
        (c3, total_goals, "Goles totales"),
        (c4, f"{avg_goals:.2f}", "Goles por partido"),
    ]:
        with col:
            st.markdown(f'<div class="stat-box"><div class="val">{val}</div><div class="lbl">{lbl}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Equipos más exitosos ────────────────────────────────────────────────
    st.markdown(f"#### {T['hist_best']}")

    # Victorias totales en Mundiales
    home_wins = df_wc[df_wc["outcome"] == "home_win"].groupby("home_team").size().rename("v_home")
    away_wins = df_wc[df_wc["outcome"] == "away_win"].groupby("away_team").size().rename("v_away")
    total_wins = home_wins.add(away_wins, fill_value=0).astype(int)

    home_played = df_wc.groupby("home_team").size().rename("p_home")
    away_played = df_wc.groupby("away_team").size().rename("p_away")
    total_played = home_played.add(away_played, fill_value=0).astype(int)

    home_goals = df_wc.groupby("home_team")["home_score"].sum().rename("gf_home")
    away_goals = df_wc.groupby("away_team")["away_score"].sum().rename("gf_away")
    total_gf = home_goals.add(away_goals, fill_value=0).astype(int)

    df_hist = pd.DataFrame({
        "Victorias": total_wins,
        "Partidos": total_played,
        "Goles": total_gf,
    }).fillna(0).astype(int)
    df_hist["Win %"] = (df_hist["Victorias"] / df_hist["Partidos"] * 100).round(1)
    df_hist = df_hist[df_hist["Partidos"] >= 10].sort_values("Victorias", ascending=False).head(20)

    df_hist.insert(0, "Selección", df_hist.index.map(lambda t: f"{flag(t)} {t}"))
    st.dataframe(df_hist[["Selección", "Partidos", "Victorias", "Win %", "Goles"]],
                 use_container_width=True, hide_index=True)

    # ── Goles por edición ──────────────────────────────────────────────────
    st.markdown(f"#### {T['hist_goals']}")
    goals_by_year = df_wc.groupby(df_wc["date"].dt.year).apply(
        lambda g: g["home_score"].sum() + g["away_score"].sum()
    ).reset_index()
    goals_by_year.columns = ["Año", "Goles"]
    fig = px.bar(goals_by_year, x="Año", y="Goles",
                 color_discrete_sequence=["#C8102E"],
                 title="Goles totales por edición del Mundial")
    fig.update_layout(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      margin=dict(t=40, b=10), height=300)
    st.plotly_chart(fig, use_container_width=True)

    # ── Goleadores históricos ──────────────────────────────────────────────
    if not df_goalscorers.empty:
        st.markdown(f"#### {T['hist_top_scorers']}")

        # Filtrar solo goles en fase final del Mundial
        # goalscorers.csv no tiene 'tournament' — se cruza por fecha+equipos con wc_clean
        wc_dates = set(
            zip(df_wc["date"].dt.date.astype(str), df_wc["home_team"], df_wc["away_team"])
        )
        df_goalscorers["_key"] = list(zip(
            df_goalscorers["date"].astype(str),
            df_goalscorers["home_team"],
            df_goalscorers["away_team"],
        ))
        wc_scorers = df_goalscorers[df_goalscorers["_key"].isin(wc_dates)]

        if not wc_scorers.empty and "scorer" in wc_scorers.columns:
            # Excluir own goals
            og_mask = wc_scorers.get("own_goal", pd.Series(False))
            wc_scorers = wc_scorers[~og_mask]

            top_scorers = (
                wc_scorers.groupby(["scorer", "team"])
                .size()
                .reset_index(name="Goles")
                .sort_values("Goles", ascending=False)
                .head(20)
            )
            top_scorers.insert(0, "Jugador", top_scorers["scorer"])
            top_scorers["Selección"] = top_scorers["team"].apply(lambda t: f"{flag(t)} {t}")
            top_scorers = top_scorers.rename(columns={"Goles": "⚽ Goles"})

            st.dataframe(
                top_scorers[["Jugador", "Selección", "⚽ Goles"]],
                use_container_width=True, hide_index=True,
            )

            # Gráfico top 10
            top10 = top_scorers.head(10)
            fig2 = px.bar(
                top10, x="⚽ Goles", y="Jugador", orientation="h",
                color_discrete_sequence=["#003087"],
                title="Top 10 goleadores históricos del Mundial",
            )
            fig2.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(autorange="reversed"),
                margin=dict(t=40, b=10), height=320,
            )
            st.plotly_chart(fig2, use_container_width=True)

    # ── Historial de selección ────────────────────────────────────────────────
    st.divider()
    st.markdown("#### 🔎 Historial de una selección en el Mundial")

    all_wc_teams = sorted(set(df_wc["home_team"].tolist() + df_wc["away_team"].tolist()))
    default_idx = all_wc_teams.index("Colombia") if "Colombia" in all_wc_teams else 0
    sel = st.selectbox(
        "Selecciona una selección",
        all_wc_teams,
        index=default_idx,
        format_func=lambda t: f"{flag(t)} {t}",
    )

    sel_mask = (df_wc["home_team"] == sel) | (df_wc["away_team"] == sel)
    df_sel = df_wc[sel_mask].copy()

    if df_sel.empty:
        st.info(f"{flag(sel)} {sel} no tiene partidos registrados en la fase final del Mundial.")
    else:
        total_s = len(df_sel)
        wins_s = (
            ((df_sel["home_team"] == sel) & (df_sel["outcome"] == "home_win")) |
            ((df_sel["away_team"] == sel) & (df_sel["outcome"] == "away_win"))
        ).sum()
        draws_s = (df_sel["outcome"] == "draw").sum()
        losses_s = total_s - wins_s - draws_s
        gf_s = df_sel.apply(
            lambda r: r["home_score"] if r["home_team"] == sel else r["away_score"], axis=1
        ).sum()
        gc_s = df_sel.apply(
            lambda r: r["away_score"] if r["home_team"] == sel else r["home_score"], axis=1
        ).sum()
        win_pct = wins_s / total_s * 100 if total_s else 0

        cs1, cs2, cs3, cs4, cs5, cs6 = st.columns(6)
        for col, val, lbl in [
            (cs1, total_s, "Partidos"),
            (cs2, wins_s, "Victorias"),
            (cs3, draws_s, "Empates"),
            (cs4, losses_s, "Derrotas"),
            (cs5, f"{int(gf_s)}-{int(gc_s)}", "Goles F-C"),
            (cs6, f"{win_pct:.0f}%", "Win rate"),
        ]:
            with col:
                st.markdown(
                    f'<div class="stat-box"><div class="val">{val}</div>'
                    f'<div class="lbl">{lbl}</div></div>',
                    unsafe_allow_html=True,
                )

        st.markdown("<br>", unsafe_allow_html=True)

        # Tabla partido a partido
        results_list = []
        for _, row in df_sel.sort_values("date").iterrows():
            rival = row["away_team"] if row["home_team"] == sel else row["home_team"]
            gf = int(row["home_score"] if row["home_team"] == sel else row["away_score"])
            gc = int(row["away_score"] if row["home_team"] == sel else row["home_score"])
            if row["outcome"] == "draw":
                res, css = "E", "h2h-draw"
            elif (row["home_team"] == sel and row["outcome"] == "home_win") or \
                 (row["away_team"] == sel and row["outcome"] == "away_win"):
                res, css = "V", "h2h-win"
            else:
                res, css = "D", "h2h-loss"
            results_list.append({
                "Año": row["date"].year,
                "Rival": f"{flag(rival)} {rival}",
                "Marcador": f"{gf}–{gc}",
                "Res.": res,
            })

        df_show = pd.DataFrame(results_list)
        st.dataframe(df_show, use_container_width=True, hide_index=True)

        # Gráfico de rendimiento por año (W/D/L apiladas)
        if len(df_show) >= 3:
            year_summary = (
                df_show.groupby(["Año", "Res."]).size().unstack(fill_value=0).reset_index()
            )
            fig_team = go.Figure()
            color_map = {"V": "#22c55e", "E": "#f59e0b", "D": "#ef4444"}
            label_map = {"V": "Victoria", "E": "Empate", "D": "Derrota"}
            for res_key in ["V", "E", "D"]:
                if res_key in year_summary.columns:
                    fig_team.add_trace(go.Bar(
                        x=year_summary["Año"],
                        y=year_summary[res_key],
                        name=label_map[res_key],
                        marker_color=color_map[res_key],
                    ))
            fig_team.update_layout(
                barmode="stack",
                title=f"Resultados de {sel} por edición del Mundial",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(t=40, b=10),
                height=280,
                legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_team, use_container_width=True)


# ─── TAB 4: Glosario ─────────────────────────────────────────────────────────

def tab_glosario():
    st.markdown("### 📖 Glosario de términos")
    st.markdown("""
    Esta pestaña explica los conceptos clave que usa el predictor.
    Si ves un número o término que no entiendes, aquí está la respuesta.
    """)

    # ── Cómo leer las probabilidades ────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔢 ¿Cómo leer el pronóstico `X% | Y% | Z%`?")
    st.info(
        "El modelo siempre muestra **tres probabilidades** separadas por `|`:\n\n"
        "```\n"
        "🇨🇴 Colombia  26%  |  Empate 32%  |  41% 🇵🇹 Portugal\n"
        "  ↑ gana la Sel. 1     ↑ empate     ↑ gana la Sel. 2\n"
        "```\n\n"
        "- **El primero** (izquierda) = probabilidad de que **gane la Selección 1**\n"
        "- **El del medio** = probabilidad de **empate** al final de los 90 minutos\n"
        "- **El último** (derecha) = probabilidad de que **gane la Selección 2**\n\n"
        "La suma siempre da **100%**. En el simulador de knockout, si hay empate se van a penales (50/50)."
    )

    st.markdown("---")

    # ── ELO ─────────────────────────────────────────────────────────────────
    with st.expander("🎯 Rating ELO — ¿qué es y cómo se calcula?"):
        st.markdown("""
**ELO** es un sistema de puntuación inventado por el físico Arpad Elo para el ajedrez,
adaptado aquí al fútbol internacional.

**Reglas del ELO:**
- Cada selección empieza con **1500 puntos**
- Ganar suma puntos, perder los resta
- Ganar contra un rival más fuerte da **más puntos** que ganar contra uno más débil
- Se calcula sobre **todos los partidos internacionales desde 1872**

**Fórmula:**
```
ELO_nuevo = ELO_viejo + 32 × (resultado_real − resultado_esperado)
resultado_real   : Victoria=1 | Empate=0.5 | Derrota=0
resultado_esperado : 1 / (1 + 10^((ELO_rival − ELO_propio)/400))
```

**Referencia rápida para el Mundial 2026:**
| ELO | Interpretación |
|-----|----------------|
| > 2000 | Élite mundial (España, Argentina, Francia) |
| 1850–2000 | Muy fuerte (Brasil, Croacia, Portugal…) |
| 1700–1850 | Sólido (Colombia 1930, Alemania…) |
| 1500–1700 | Competitivo |
| < 1500 | Debutante o con poco historial |

> 💡 El `elo_diff` (diferencia de ELOs entre los dos equipos) es la **feature más predictiva** del modelo, con correlación 0.40 con el resultado.
        """)

    # ── Monte Carlo ──────────────────────────────────────────────────────────
    with st.expander("🎲 Simulación Monte Carlo — ¿por qué 1000 torneos?"):
        st.markdown("""
**Monte Carlo** es un método estadístico que usa el azar para estimar probabilidades difíciles de calcular directamente.

**¿Cómo funciona aquí?**
1. Toma el modelo y predice las probabilidades de cada partido (ej: 60% A gana, 25% empate, 15% B gana)
2. En vez de solo tomar el resultado más probable, **sortea** el resultado según esas probabilidades
3. Simula toda la fase de grupos → determina los 32 clasificados → simula el knockout → hay un campeón
4. Repite ese proceso **N veces** (1000 o más)
5. Al final, cuenta: ¿cuántas veces llegó Colombia a cuartos? → eso es su probabilidad real

**¿Por qué no tomar siempre el resultado más probable?**
Porque en fútbol, el "favorito" solo gana ~60% de las veces.
Si siempre eliges al favorito, Argentina ganaría el Mundial 100% de las veces. El Monte Carlo captura esa **incertidumbre real**.

**¿Cuántas simulaciones necesito?**
- 500: rápido, margen de error ~±3%
- 1000: buen equilibrio velocidad/precisión
- 5000: muy preciso, ~±1%
- 10000: estadísticamente sólido, tarda más
        """)

    # ── Fase de Grupos ───────────────────────────────────────────────────────
    with st.expander("🏟️ Fase de grupos — ¿cómo funciona el formato del Mundial 2026?"):
        st.markdown("""
**48 equipos** divididos en **12 grupos de 4** (Grupos A al L).

Dentro de cada grupo, todos se enfrentan contra todos (**6 partidos**):
```
Partido 1: Equipo 1 vs Equipo 2
Partido 2: Equipo 3 vs Equipo 4
Partido 3: Equipo 1 vs Equipo 3
Partido 4: Equipo 2 vs Equipo 4
Partido 5: Equipo 1 vs Equipo 4
Partido 6: Equipo 2 vs Equipo 3
```
**Sistema de puntos:** Victoria = 3 pts · Empate = 1 pt · Derrota = 0 pts

**¿Quién clasifica?**
- **1° y 2° de cada grupo** → clasifica directo (24 equipos)
- **Mejores 8 terceros** entre los 12 grupos → completan los 32 clasificados

**Desempate:** puntos → diferencia de goles → goles a favor → enfrentamiento directo → fair play → sorteo
        """)

    # ── Rondas de knockout ───────────────────────────────────────────────────
    with st.expander("🏆 Rondas de eliminación directa"):
        st.markdown("""
| Ronda | Equipos | Partidos |
|-------|---------|---------|
| **Ronda de 32** (Round of 32) | 32 → 16 | 16 partidos |
| **Octavos de final** (Round of 16) | 16 → 8 | 8 partidos |
| **Cuartos de final** (Quarter-finals) | 8 → 4 | 4 partidos |
| **Semifinal** | 4 → 2 | 2 partidos |
| **Final** | 2 → 1 | 1 partido |

**En el knockout no hay empates.** Si el partido termina empatado al final de 90 minutos:
1. Tiempo extra (2 × 15 min)
2. Si sigue empatado → penales

> El simulador modela el empate a los 90' como penales aleatorios (50/50), que es estadísticamente la aproximación más honesta.
        """)

    # ── Métricas del modelo ──────────────────────────────────────────────────
    with st.expander("📐 Métricas del modelo — accuracy, log-loss, Brier"):
        st.markdown("""
**Accuracy (exactitud):** % de partidos donde el modelo predijo correctamente el resultado (victoria/empate/derrota).
- Nuestro modelo: **50%** en Qatar 2022
- Baseline (siempre predice "local gana"): ~45%
- Un humano experto: ~55–60%

**Log-Loss:** mide qué tan bien calibradas están las probabilidades. **Menor es mejor.**
- Si dices "80% Colombia gana" y Colombia gana → log-loss bajo ✅
- Si dices "80% Colombia gana" y pierde → log-loss alto ❌
- Nuestro modelo: **1.080** (mejor que el baseline de 1.098)

**Brier Score:** promedio del error cuadrático de las probabilidades. **Menor es mejor.**
- Escala 0–1. Nuestro modelo: **0.214** (buena calibración)

> El modelo nunca va a ser "perfecto" — el fútbol tiene mucho azar. El objetivo es que las probabilidades **reflejen la realidad** mejor que el azar puro.
        """)

    # ── Features del modelo ──────────────────────────────────────────────────
    with st.expander("🔬 Features del modelo — las 10 variables de entrada"):
        st.markdown("""
| Feature | Descripción | Importancia |
|---------|-------------|-------------|
| `elo_diff` | Diferencia de ELO entre los dos equipos (local − visitante) | 🥇 27% |
| `is_neutral` | 1 si la sede es neutral (siempre 1 en el Mundial) | 🥈 11% |
| `wc_experience_diff` | Diferencia de partidos jugados en Mundiales previos | 🥉 10% |
| `elo_away` | ELO absoluto del equipo visitante | ↑ 9% |
| `home_goals_scored_avg5` | Promedio de goles anotados en los últimos 5 partidos (Sel. 1) | ↑ 8% |
| `away_goals_conceded_avg5` | Promedio de goles recibidos en los últimos 5 partidos (Sel. 2) | ↑ 8% |
| `elo_home` | ELO absoluto del equipo local | ↑ 8% |
| `away_goals_scored_avg5` | Promedio de goles anotados (Sel. 2) | ↑ 7% |
| `home_goals_conceded_avg5` | Promedio de goles recibidos (Sel. 1) | ↑ 6% |
| `h2h_home_win_pct` | % victorias de Sel. 1 en enfrentamientos directos de WC | 6% |

> El modelo fue entrenado con partidos **hasta Qatar 2018** y evaluado en **Qatar 2022** (sin filtración de datos futuros).
        """)

    st.markdown("---")
    st.markdown("""
    <div class="info-box">
    💡 <b>¿Tienes más preguntas?</b> Este es un proyecto open-source de portafolio.
    El código completo está en GitHub. La predicción perfecta no existe en el fútbol —
    si no, ¿para qué jugar los partidos? 😄
    </div>
    """, unsafe_allow_html=True)


# ─── TAB 4: Datos Curiosos ────────────────────────────────────────────────────

def tab_datos_curiosos(df_wc: pd.DataFrame, df_features: pd.DataFrame, T: dict) -> None:
    st.markdown(f"### {T['curiosos_title']}")

    # ── Preparación de datos ────────────────────────────────────────────────
    df = df_wc.copy()
    df["total_goals"] = df["home_score"] + df["away_score"]
    df["margin"] = (df["home_score"] - df["away_score"]).abs()
    df["year"] = df["date"].dt.year

    by_year = df.groupby("year").agg(
        total=("total_goals", "sum"),
        matches=("total_goals", "count"),
    ).reset_index()
    by_year["avg"] = by_year["total"] / by_year["matches"]

    best_total_row = by_year.loc[by_year["total"].idxmax()]
    best_avg_row = by_year.loc[by_year["avg"].idxmax()]
    max_goals_row = df.loc[df["total_goals"].idxmax()]
    max_margin_row = df.loc[df["margin"].idxmax()]

    # ── KPIs ────────────────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""<div class="stat-box">
            <div class="val">{int(best_total_row['total'])} ⚽</div>
            <div class="lbl">{T['rec_mas_goles_ed']}</div>
            <div style="font-size:0.7rem;opacity:0.6">Mundial {int(best_total_row['year'])}</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="stat-box">
            <div class="val">{best_avg_row['avg']:.2f}</div>
            <div class="lbl">{T['rec_avg_goles_max']}</div>
            <div style="font-size:0.7rem;opacity:0.6">Mundial {int(best_avg_row['year'])}</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        hs = int(max_goals_row["home_score"])
        as_ = int(max_goals_row["away_score"])
        st.markdown(f"""<div class="stat-box">
            <div class="val">{int(max_goals_row['total_goals'])} ⚽</div>
            <div class="lbl">{T['rec_partido_goles']}</div>
            <div style="font-size:0.7rem;opacity:0.6">
                {flag(max_goals_row['home_team'])} {hs}–{as_} {flag(max_goals_row['away_team'])}<br>
                {int(max_goals_row['year'])}
            </div>
        </div>""", unsafe_allow_html=True)
    with c4:
        hs_m = int(max_margin_row["home_score"])
        as_m = int(max_margin_row["away_score"])
        st.markdown(f"""<div class="stat-box">
            <div class="val">+{int(max_margin_row['margin'])}</div>
            <div class="lbl">{T['rec_goleada_max']}</div>
            <div style="font-size:0.7rem;opacity:0.6">
                {flag(max_margin_row['home_team'])} {hs_m}–{as_m} {flag(max_margin_row['away_team'])}<br>
                {int(max_margin_row['year'])}
            </div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Goles por Mundial ──────────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_avg_label']}")

    fig_goals = go.Figure()
    fig_goals.add_bar(
        x=by_year["year"],
        y=by_year["avg"],
        marker=dict(
            color=by_year["avg"],
            colorscale=[[0, "#003087"], [0.5, "#C8102E"], [1, "#F5D300"]],
            showscale=False,
        ),
        text=by_year["avg"].apply(lambda x: f"{x:.2f}"),
        textposition="outside",
        hovertemplate="<b>%{x}</b><br>%{y:.2f} goles/partido<extra></extra>",
    )
    # Línea de tendencia
    fig_goals.add_scatter(
        x=by_year["year"],
        y=by_year["avg"].rolling(3, center=True, min_periods=1).mean(),
        mode="lines",
        line=dict(color="rgba(245,211,0,0.8)", width=3, dash="dot"),
        name="Media móvil 3 ediciones",
        hoverinfo="skip",
    )
    fig_goals.add_annotation(
        x=1954, y=by_year.loc[by_year["year"] == 1954, "avg"].values[0],
        text="🔥 1954: 5.38/partido",
        showarrow=True, arrowhead=2,
        ax=40, ay=-40,
        font=dict(color="#F5D300", size=11),
        arrowcolor="#F5D300",
    )
    fig_goals.update_layout(
        showlegend=False,
        xaxis=dict(title="", tickmode="linear", dtick=4),
        yaxis=dict(title="", range=[0, by_year["avg"].max() * 1.25]),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=20, b=10, l=10, r=10),
        height=310,
    )
    st.plotly_chart(fig_goals, use_container_width=True)

    # ── Tendencia por décadas ──────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_era_title']}")

    df["decade"] = (df["year"] // 10 * 10)
    by_decade = df.groupby("decade").agg(
        hw=("outcome", lambda x: (x == "home_win").sum()),
        d=("outcome", lambda x: (x == "draw").sum()),
        aw=("outcome", lambda x: (x == "away_win").sum()),
        total=("outcome", "count"),
    ).reset_index()
    by_decade["hw_pct"] = by_decade["hw"] / by_decade["total"] * 100
    by_decade["d_pct"] = by_decade["d"] / by_decade["total"] * 100
    by_decade["aw_pct"] = by_decade["aw"] / by_decade["total"] * 100
    by_decade["decade_lbl"] = by_decade["decade"].astype(str) + "s"

    fig_era = go.Figure()
    for col, color, lbl in [
        ("hw_pct", "#C8102E", T["curiosos_home_win_lbl"]),
        ("d_pct", "#888888", T["curiosos_draw_lbl"]),
        ("aw_pct", "#003087", T["curiosos_away_win_lbl"]),
    ]:
        fig_era.add_trace(go.Bar(
            x=by_decade["decade_lbl"],
            y=by_decade[col],
            name=lbl,
            marker_color=color,
            text=by_decade[col].apply(lambda x: f"{x:.0f}%"),
            textposition="inside",
            textfont_color="white",
        ))
    fig_era.update_layout(
        barmode="stack",
        showlegend=True,
        legend=dict(orientation="h", y=1.05),
        xaxis_title="",
        yaxis=dict(title="", ticksuffix="%"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=40, b=10, l=10, r=10),
        height=300,
    )
    st.plotly_chart(fig_era, use_container_width=True)

    st.divider()

    # ── Equipos más goleadores ─────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_goals_title']}")

    all_teams_hist = sorted(set(df["home_team"].tolist() + df["away_team"].tolist()))
    goal_rows = []
    for team in all_teams_hist:
        home_m = df[df["home_team"] == team]
        away_m = df[df["away_team"] == team]
        n = len(home_m) + len(away_m)
        if n < 5:
            continue
        gf = int(home_m["home_score"].sum() + away_m["away_score"].sum())
        ga = int(home_m["away_score"].sum() + away_m["home_score"].sum())
        goal_rows.append({
            T["curiosos_goals_team"]: f"{flag(team)} {team}",
            T["curiosos_goals_matches"]: n,
            T["curiosos_goals_gf"]: gf,
            T["curiosos_goals_ga"]: ga,
            T["curiosos_goals_diff"]: gf - ga,
            T["curiosos_goals_avg"]: round(gf / n, 2),
        })

    df_goals = (
        pd.DataFrame(goal_rows)
        .sort_values(T["curiosos_goals_gf"], ascending=False)
        .head(15)
    )

    col_tbl, col_chart = st.columns([2, 3])
    with col_tbl:
        st.dataframe(df_goals, use_container_width=True, hide_index=True)
    with col_chart:
        top10 = df_goals.head(10).copy()
        fig_gf = go.Figure(go.Bar(
            y=top10[T["curiosos_goals_team"]],
            x=top10[T["curiosos_goals_gf"]],
            orientation="h",
            marker_color="#C8102E",
            text=top10[T["curiosos_goals_gf"]],
            textposition="outside",
        ))
        fig_gf.update_layout(
            yaxis=dict(autorange="reversed"),
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=10, b=10, l=10, r=40),
            height=340,
            showlegend=False,
        )
        st.plotly_chart(fig_gf, use_container_width=True)

    st.divider()

    # ── Mayores sorpresas ELO ─────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_upsets_title']}")

    df_feat = df_features.copy()
    df_feat["underdog_won"] = (
        ((df_feat["elo_diff"] > 0) & (df_feat["outcome"] == "away_win")) |
        ((df_feat["elo_diff"] < 0) & (df_feat["outcome"] == "home_win"))
    )
    upsets = df_feat[df_feat["underdog_won"]].copy()
    upsets["upset_magnitude"] = upsets["elo_diff"].abs()
    top_upsets = upsets.nlargest(10, "upset_magnitude")

    # Merge para obtener marcadores
    merged_upsets = top_upsets.merge(
        df_wc[["date", "home_team", "away_team", "home_score", "away_score"]],
        on=["date", "home_team", "away_team"],
        how="left",
    )

    upset_rows = []
    for _, r in merged_upsets.iterrows():
        yr = r["date"].year if hasattr(r["date"], "year") else str(r["date"])[:4]
        hs_u = int(r["home_score"]) if pd.notna(r.get("home_score")) else "?"
        as_u = int(r["away_score"]) if pd.notna(r.get("away_score")) else "?"
        if r["elo_diff"] > 0:
            favored = r["home_team"]
            winner = r["away_team"]
            elo_fav = r["elo_home"]
        else:
            favored = r["away_team"]
            winner = r["home_team"]
            elo_fav = r["elo_away"]

        upset_rows.append({
            T["curiosos_upsets_date"]: int(yr),
            T["curiosos_upsets_match"]: f"{flag(r['home_team'])} {r['home_team']} vs {flag(r['away_team'])} {r['away_team']}",
            T["curiosos_upsets_score"]: f"{hs_u}–{as_u}",
            T["curiosos_upsets_favored"]: f"{flag(favored)} {favored} ({elo_fav:.0f})",
            T["curiosos_upsets_winner"]: f"{flag(winner)} {winner}",
            T["curiosos_upsets_diff"]: f"+{r['upset_magnitude']:.0f} ELO",
        })

    st.dataframe(pd.DataFrame(upset_rows), use_container_width=True, hide_index=True)

    st.divider()

    # ── ¿Sabías que? ──────────────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_facts_title']}")

    # Datos computados del dataset para validar los facts
    total_goals_all = int(df["total_goals"].sum())
    total_matches_all = len(df)
    n_editions = df["year"].nunique()
    # Equipo con más partidos
    team_match_counts = pd.concat([
        df["home_team"], df["away_team"]
    ]).value_counts()
    most_played_team = team_match_counts.index[0]
    most_played_n = int(team_match_counts.iloc[0])

    # Equipo con más victorias
    hw = df[df["outcome"] == "home_win"].groupby("home_team").size()
    aw = df[df["outcome"] == "away_win"].groupby("away_team").size()
    total_wins_all = hw.add(aw, fill_value=0).astype(int)
    most_wins_team = total_wins_all.idxmax()
    most_wins_n = int(total_wins_all.max())

    # Edición con menos goles
    least_avg_row = by_year.loc[by_year["avg"].idxmin()]

    facts = [
        (
            "🌍",
            "Brasil" if T.get("tab_curiosos") == "🤩 Curiosidades" else "Brazil",
            f"{'🇧🇷 Brasil es el único país que ha participado en TODAS las Copas del Mundo — las' if T.get('tab_curiosos') == '🤩 Curiosidades' else '🇧🇷 Brazil is the only nation to have participated in EVERY World Cup — all'} {n_editions} {'ediciones.' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'editions.'}",
        ),
        (
            "🏟️",
            str(int(total_goals_all)),
            f"{'En total se han anotado' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'A total of'} **{total_goals_all:,}** {'goles en los' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'goals have been scored across the'} {total_matches_all} {'partidos de fase final de Mundial del dataset.' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'World Cup matches in this dataset.'}",
        ),
        (
            "📉",
            f"{least_avg_row['avg']:.2f}",
            f"{'El Mundial con MENOS goles/partido fue' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'The World Cup with the FEWEST goals/match was'} **{int(least_avg_row['year'])}** ({least_avg_row['avg']:.2f} {'goles/partido' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'goals/match'}). {'El fútbol moderno es más defensivo que en los años 50.' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'Modern football is far more defensive than the 1950s.'}",
        ),
        (
            "🏆",
            f"{flag(most_played_team)} {most_wins_n}",
            f"**{flag(most_wins_team)} {most_wins_team}** {'tiene más victorias en Mundiales del dataset:' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'has the most World Cup victories in this dataset:'} **{most_wins_n}** {'triunfos en' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'wins across'} {most_played_n} {'partidos.' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'matches.'}",
        ),
        (
            "⚡",
            "1954",
            f"{'El Mundial de Suiza 1954 es el más loco de la historia:' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'The 1954 World Cup in Switzerland is the wildest ever:'} **{best_avg_row['avg']:.2f}** {'goles/partido' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'goals/match'}. {'Partido más memorable: Austria 7–5 Suiza (12 goles en 90 minutos).' if T.get('tab_curiosos') == '🤩 Curiosidades' else 'Most memorable: Austria 7–5 Switzerland (12 goals in 90 minutes).'}",
        ),
        (
            "🇨🇴",
            "Colombia",
            f"{'🇨🇴 Colombia llega al Mundial 2026 con ELO 1930 — su rating histórico más alto, top 8 mundial. El mejor momento en la historia de la Tricolor.' if T.get('tab_curiosos') == '🤩 Curiosidades' else '🇨🇴 Colombia enters World Cup 2026 with ELO 1930 — their all-time highest rating, top 8 globally. The golden era of La Tricolor.'}",
        ),
    ]

    for idx in range(0, len(facts), 2):
        cols = st.columns(2)
        for j, col in enumerate(cols):
            if idx + j >= len(facts):
                break
            emoji, highlight, text = facts[idx + j]
            with col:
                st.markdown(f"""
<div class="bracket-match" style="padding:16px 18px;min-height:90px">
  <span style="font-size:2rem">{emoji}</span>&nbsp;
  <span style="font-weight:900;font-size:1.3rem;color:#F5D300">{highlight}</span>
  <div style="margin-top:8px;font-size:0.88rem;line-height:1.5">{text}</div>
</div>""", unsafe_allow_html=True)

    st.divider()

    # ── Colombia en cifras ────────────────────────────────────────────────
    st.markdown(f"#### {T['curiosos_col_title']}")

    col_mask = (df["home_team"] == "Colombia") | (df["away_team"] == "Colombia")
    df_col = df[col_mask].copy()

    if df_col.empty:
        st.info("Colombia no tiene partidos en el dataset.")
    else:
        col_home = df_col[df_col["home_team"] == "Colombia"]
        col_away = df_col[df_col["away_team"] == "Colombia"]
        c_total = len(df_col)
        c_wins = int(
            (col_home["outcome"] == "home_win").sum() +
            (col_away["outcome"] == "away_win").sum()
        )
        c_draws = int((df_col["outcome"] == "draw").sum())
        c_losses = c_total - c_wins - c_draws
        c_gf = int(col_home["home_score"].sum() + col_away["away_score"].sum())
        c_ga = int(col_home["away_score"].sum() + col_away["home_score"].sum())
        c_win_pct = c_wins / c_total * 100

        # Mini récords Colombia
        col_goleada = df_col.copy()
        col_goleada["col_goals"] = col_goleada.apply(
            lambda r: r["home_score"] if r["home_team"] == "Colombia" else r["away_score"], axis=1
        )
        col_goleada["rival_goals"] = col_goleada.apply(
            lambda r: r["away_score"] if r["home_team"] == "Colombia" else r["home_score"], axis=1
        )
        col_goleada["margin"] = col_goleada["col_goals"] - col_goleada["rival_goals"]

        best_win_row = col_goleada.loc[col_goleada["margin"].idxmax()]
        worst_loss_row = col_goleada.loc[col_goleada["margin"].idxmin()]

        ca1, ca2, ca3, ca4 = st.columns(4)
        with ca1:
            st.markdown(f"""<div class="stat-box">
                <div class="val">{c_wins}V {c_draws}E {c_losses}D</div>
                <div class="lbl">Récord histórico</div>
            </div>""", unsafe_allow_html=True)
        with ca2:
            st.markdown(f"""<div class="stat-box">
                <div class="val">{c_gf}/{c_ga}</div>
                <div class="lbl">Goles F/C</div>
            </div>""", unsafe_allow_html=True)
        with ca3:
            st.markdown(f"""<div class="stat-box">
                <div class="val">{c_win_pct:.0f}%</div>
                <div class="lbl">Win rate</div>
            </div>""", unsafe_allow_html=True)
        with ca4:
            elo_col = 1930.48
            st.markdown(f"""<div class="stat-box">
                <div class="val">🇨🇴 {elo_col:.0f}</div>
                <div class="lbl">ELO actual (máximo histórico)</div>
            </div>""", unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Gráfico de resultados de Colombia
        col_results = []
        for _, row in col_goleada.sort_values("date").iterrows():
            rival = row["away_team"] if row["home_team"] == "Colombia" else row["home_team"]
            res_num = 1 if row["margin"] > 0 else (-1 if row["margin"] < 0 else 0)
            col_results.append({
                "date": row["date"],
                "rival": rival,
                "gf": int(row["col_goals"]),
                "gc": int(row["rival_goals"]),
                "margin": row["margin"],
                "resultado": "Victoria" if res_num == 1 else ("Derrota" if res_num == -1 else "Empate"),
            })

        df_col_res = pd.DataFrame(col_results)
        color_map_res = {"Victoria": "#22c55e", "Empate": "#f59e0b", "Derrota": "#ef4444"}
        fig_col = px.scatter(
            df_col_res, x="date", y="margin",
            color="resultado",
            color_discrete_map=color_map_res,
            hover_data={"rival": True, "gf": True, "gc": True, "date": False},
            labels={"date": "", "margin": "Diferencia de goles", "resultado": ""},
            size_max=12,
        )
        fig_col.add_hline(y=0, line_color="rgba(255,255,255,0.3)", line_dash="dot")
        fig_col.update_layout(
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(t=20, b=10, l=10, r=10),
            height=260,
            legend=dict(orientation="h", y=1.05),
        )
        st.plotly_chart(fig_col, use_container_width=True)
        st.caption(
            f"🏆 Mejor resultado: {flag('Colombia')} {int(best_win_row['col_goals'])}–{int(best_win_row['rival_goals'])} "
            f"{flag(best_win_row['away_team'] if best_win_row['home_team']=='Colombia' else best_win_row['home_team'])} "
            f"({int(best_win_row['date'].year)})  |  "
            f"💔 Peor resultado: {flag('Colombia')} {int(worst_loss_row['col_goals'])}–{int(worst_loss_row['rival_goals'])} "
            f"({int(worst_loss_row['date'].year)})"
        )


# ─── Sidebar ─────────────────────────────────────────────────────────────────

def render_sidebar() -> str:
    with st.sidebar:
        st.markdown("""<div style="text-align:center;padding:12px 0 8px 0">
            <span style="font-size:2.5rem">⚽</span>
            <div style="font-weight:800;font-size:1.1rem;margin-top:4px">Mundial 2026</div>
            <div style="font-size:0.78rem;opacity:0.6">Predictor ML</div>
        </div>""", unsafe_allow_html=True)
        st.divider()

        lang = st.selectbox("🌐 Idioma / Language", list(STRINGS.keys()), index=0)
        st.divider()

        st.markdown("**📈 Modelo — Qatar 2022**")
        try:
            with open(DATA_PROCESSED / "metrics.json") as f:
                metrics = json.load(f)
            xgb = metrics.get("xgb_calibrated", {})
            c1, c2 = st.columns(2)
            c1.metric("Accuracy", f"{xgb.get('accuracy', 0):.1%}")
            c2.metric("Log-Loss", f"{xgb.get('log_loss', 0):.3f}")
        except Exception:
            pass

        st.divider()
        st.markdown("""
        **🔬 Fuentes de datos**
        - Kaggle: 49k+ partidos (1872–2026)
        - openfootball: Fixture WC 2026
        - ELO propio calculado

        **🤖 Modelo**
        XGBoost calibrado · 10 features
        """)
        st.divider()
        st.caption("by Luis Miguel · 2026")
    return lang


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    lang = render_sidebar()
    T = STRINGS[lang]

    st.markdown(f"""<div class="wc-hero">
        <h1>{T["title"]}</h1>
        <p>{T["subtitle"]}</p>
    </div>""", unsafe_allow_html=True)

    try:
        model = get_model()
        df_features = get_features()
        df_wc = get_wc_matches()
        elo_ratings = get_elo_ratings()
        df_goalscorers = get_goalscorers()
    except Exception as e:
        st.error(f"{T['model_err']}\n\n`{e}`")
        return

    # Pre-computar cachés una sola vez (st.cache_resource los mantiene en memoria)
    with st.spinner("Iniciando predictor…"):
        team_stats, h2h_stats, probs_cache = get_prediction_caches(model)

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        T["tab_pred"], T["tab_sim"], T["tab_hist"], T["tab_curiosos"], T["tab_glos"],
    ])

    with tab1:
        tab_predictor(model, df_features, df_wc, elo_ratings, T, team_stats, h2h_stats, probs_cache)
    with tab2:
        tab_simulator(model, df_features, elo_ratings, T, probs_cache)
    with tab3:
        tab_historico(df_wc, df_goalscorers, T)
    with tab4:
        tab_datos_curiosos(df_wc, df_features, T)
    with tab5:
        tab_glosario()


if __name__ == "__main__":
    main()
