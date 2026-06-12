"""
Enriquece goalscorers.json con la lista de víctimas (equipos a los que les marcó)
para cada goleador histórico de la fase final del Mundial.

Uso:  python scripts/enrich_goalscorers.py
"""
import json
from pathlib import Path
import pandas as pd

ROOT      = Path(__file__).resolve().parent.parent
DATA_RAW  = ROOT / "data" / "raw"
DATA_PROC = ROOT / "data" / "processed"
OUT_FILE  = ROOT / "frontend" / "public" / "data" / "goalscorers.json"

TEAM_FLAGS = {
    "Argentina": "🇦🇷", "Brazil": "🇧🇷", "Colombia": "🇨🇴", "Uruguay": "🇺🇾",
    "Ecuador": "🇪🇨", "Venezuela": "🇻🇪", "Chile": "🇨🇱", "Peru": "🇵🇪",
    "Paraguay": "🇵🇾", "Bolivia": "🇧🇴",
    "Mexico": "🇲🇽", "United States": "🇺🇸", "Canada": "🇨🇦",
    "Panama": "🇵🇦", "Honduras": "🇭🇳", "Costa Rica": "🇨🇷",
    "Spain": "🇪🇸", "France": "🇫🇷", "Germany": "🇩🇪", "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Portugal": "🇵🇹", "Italy": "🇮🇹", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
    "Croatia": "🇭🇷", "Switzerland": "🇨🇭", "Denmark": "🇩🇰", "Sweden": "🇸🇪",
    "Norway": "🇳🇴", "Austria": "🇦🇹", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Serbia": "🇷🇸",
    "Romania": "🇷🇴", "Czech Republic": "🇨🇿", "Turkey": "🇹🇷",
    "West Germany": "🇩🇪", "Soviet Union": "🇷🇺", "Yugoslavia": "🇷🇸",
    "Czechoslovakia": "🇨🇿", "East Germany": "🇩🇪",
    "Morocco": "🇲🇦", "Senegal": "🇸🇳", "Nigeria": "🇳🇬", "Ivory Coast": "🇨🇮",
    "Ghana": "🇬🇭", "Cameroon": "🇨🇲", "Algeria": "🇩🇿", "Tunisia": "🇹🇳",
    "DR Congo": "🇨🇩", "Zaire": "🇨🇩", "Egypt": "🇪🇬", "South Africa": "🇿🇦",
    "Japan": "🇯🇵", "South Korea": "🇰🇷", "Iran": "🇮🇷", "Saudi Arabia": "🇸🇦",
    "Australia": "🇦🇺", "Iraq": "🇮🇶", "Qatar": "🇶🇦", "New Zealand": "🇳🇿",
    "United Arab Emirates": "🇦🇪", "Kuwait": "🇰🇼",
    "Haiti": "🇭🇹", "Cuba": "🇨🇺", "El Salvador": "🇸🇻",
    "Hungary": "🇭🇺", "Poland": "🇵🇱", "Bulgaria": "🇧🇬",
    "Russia": "🇷🇺", "Ukraine": "🇺🇦", "Greece": "🇬🇷",
    "Northern Ireland": "🇬🇧", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿", "Ireland": "🇮🇪",
    "United States of America": "🇺🇸",
    "Korea Republic": "🇰🇷",
}


def main():
    # ── 1. Leer datos crudos ──────────────────────────────────────────────
    df_gs  = pd.read_csv(DATA_RAW / "goalscorers.csv",  parse_dates=["date"])
    df_wc  = pd.read_csv(DATA_PROC / "wc_clean.csv",    parse_dates=["date"])

    # Fechas únicas de partidos de la fase final del Mundial
    wc_dates = set(df_wc["date"].dt.strftime("%Y-%m-%d"))

    # ── 2. Filtrar a fase final + sin autogoles ───────────────────────────
    df_gs["date_str"] = df_gs["date"].dt.strftime("%Y-%m-%d")
    mask = (
        df_gs["date_str"].isin(wc_dates) &
        (df_gs["own_goal"].astype(str).str.upper() != "TRUE")
    )
    df_wc_gs = df_gs[mask].copy()

    # Oponente de cada gol
    df_wc_gs["opponent"] = df_wc_gs.apply(
        lambda r: r["away_team"] if r["team"] == r["home_team"] else r["home_team"],
        axis=1,
    )

    # ── 3. Leer goalscorers.json actual ──────────────────────────────────
    current = json.loads(OUT_FILE.read_text(encoding="utf-8"))

    # ── 4. Calcular víctimas para cada goleador ───────────────────────────
    enriched = []
    for entry in current:
        scorer  = entry["scorer"]
        country = entry["country"]

        # Goles de este jugador en fase final del Mundial
        df_scorer = df_wc_gs[
            (df_wc_gs["scorer"] == scorer) &
            (df_wc_gs["team"]   == country)
        ]

        victims_raw = (
            df_scorer
            .groupby("opponent")
            .size()
            .reset_index(name="goals")
            .sort_values("goals", ascending=False)
        )

        victims = [
            {
                "team":  row["opponent"],
                "flag":  TEAM_FLAGS.get(row["opponent"], "🏳️"),
                "goals": int(row["goals"]),
            }
            for _, row in victims_raw.iterrows()
        ]

        enriched.append({**entry, "victims": victims})

    # ── 5. Guardar ────────────────────────────────────────────────────────
    OUT_FILE.write_text(
        json.dumps(enriched, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[OK] {len(enriched)} goleadores enriquecidos con víctimas.")
    print(f"     -> {OUT_FILE}")

    # Muestra resumen
    for g in enriched[:5]:
        v_str = ", ".join(
            f"{v['flag']} {v['team']} ({v['goals']})" for v in g["victims"][:3]
        )
        print(f"   {g['scorer']:20s} → {v_str}")


if __name__ == "__main__":
    main()
