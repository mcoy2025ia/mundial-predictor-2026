"""
Construye el índice RAG para el chat del Mundial 2026.

Lee datos de: teams.json, predictions.json, groups.json, group_standings.json,
              wc2026_fixture.json, wc2026_live_results.csv, wc2026_stadiums.json

Genera embeddings con Qwen3-Embedding (DashScope API, modelo text-embedding-v3,
512 dimensiones Matryoshka) y guarda el índice en:
  frontend/public/data/rag_index.json

Uso:
  export DASHSCOPE_API_KEY=sk-...
  python scripts/build_rag_index.py

El índice se regenera cada vez que se actualicen datos del torneo.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ── Dependencias ───────────────────────────────────────────────────────────────
try:
    from openai import OpenAI
except ImportError:
    sys.exit("ERROR: pip install openai")

try:
    import pandas as pd
except ImportError:
    sys.exit("ERROR: pip install pandas")

# ── Config ─────────────────────────────────────────────────────────────────────
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
EMBED_MODEL       = "text-embedding-v3"
EMBED_DIMS        = 512          # Matryoshka: 64/128/256/512/1024
BATCH_SIZE        = 20           # DashScope max ~25 por llamada
OUT_PATH          = ROOT / "frontend" / "public" / "data" / "rag_index.json"

DATA_DIR    = ROOT / "frontend" / "public" / "data"
EXT_DIR     = ROOT / "data" / "external"

PREDICTIONS_PATH  = DATA_DIR / "predictions.json"
TEAMS_PATH        = DATA_DIR / "teams.json"
GROUPS_PATH       = DATA_DIR / "groups.json"
STANDINGS_PATH    = DATA_DIR / "group_standings.json"
FIXTURE_PATH      = EXT_DIR  / "wc2026_fixture.json"
LIVE_PATH         = EXT_DIR  / "wc2026_live_results.csv"
STADIUMS_PATH     = EXT_DIR  / "wc2026_stadiums.json"


# ── Embedding client ───────────────────────────────────────────────────────────
def get_embed_client() -> OpenAI:
    if not DASHSCOPE_API_KEY:
        sys.exit(
            "ERROR: DASHSCOPE_API_KEY no configurada.\n"
            "  Regístrate en https://dashscope.aliyuncs.com y exporta la variable."
        )
    return OpenAI(
        api_key=DASHSCOPE_API_KEY,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    )


def embed_batch(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embeds un lote de textos, con retry en 429."""
    for attempt in range(3):
        try:
            resp = client.embeddings.create(
                model=EMBED_MODEL,
                input=texts,
                dimensions=EMBED_DIMS,
                encoding_format="float",
            )
            return [item.embedding for item in resp.data]
        except Exception as exc:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"  Retry {attempt+1} ({exc}) — esperando {wait}s…")
            time.sleep(wait)
    return []


def embed_all(client: OpenAI, texts: list[str]) -> list[list[float]]:
    """Embeds todos los textos en batches con progreso."""
    n = len(texts)
    all_vecs: list[list[float]] = []
    for i in range(0, n, BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        print(f"  Embedding {i+len(batch)}/{n}…", end="\r")
        vecs = embed_batch(client, batch)
        all_vecs.extend(vecs)
        if i + BATCH_SIZE < n:
            time.sleep(0.3)  # rate limiting gentil
    print()
    return all_vecs


# ── Generadores de chunks ──────────────────────────────────────────────────────

def chunks_teams(teams: dict) -> list[dict]:
    out = []
    for name, t in teams.items():
        text = (
            f"{name} {t.get('flag','')} — Grupo {t.get('group','?')}, {t.get('confederation','')}\n"
            f"ELO: {t.get('elo',0):.0f} (Ranking #{t.get('rank','?')})\n"
            f"Forma reciente: {t.get('goals_scored',0):.2f} goles/partido marcados, "
            f"{t.get('goals_conceded',0):.2f} concedidos\n"
            f"Experiencia mundialista: {t.get('wc_matches',0)} partidos de Copa del Mundo\n"
            f"Efectividad en penales: {t.get('pen_wins',0)}/{t.get('pen_total',0)} series ganadas"
        )
        out.append({"id": f"team_{name.lower().replace(' ','_')}", "type": "team",
                    "team": name, "text": text})
    return out


def chunks_fixture_predictions(fixture: list[dict], preds: dict, teams: dict) -> list[dict]:
    out = []
    for m in fixture:
        t1, t2 = m.get("team1",""), m.get("team2","")
        if not t1 or not t2 or t1.startswith(("W","1","2","3","4","A","B","C","D","E","F","G","H","I","J","K","L")):
            continue
        key_fwd  = f"{t1}|{t2}"
        key_rev  = f"{t2}|{t1}"
        pred = preds.get(key_fwd) or preds.get(key_rev)
        group    = m.get("group","")
        round_   = m.get("round","")
        date     = m.get("date","")
        ground   = m.get("ground","")
        flag1    = teams.get(t1, {}).get("flag","")
        flag2    = teams.get(t2, {}).get("flag","")

        if pred:
            # Probabilidades del ensemble
            hw = pred.get("ensemble_home_win", pred.get("home_win", 0))
            d  = pred.get("ensemble_draw",     pred.get("draw", 0))
            aw = pred.get("ensemble_away_win", pred.get("away_win", 0))
            # Si el key estaba invertido, voltear
            if key_rev in preds and key_fwd not in preds:
                hw, aw = aw, hw
            prob_str = (
                f"Predicción (ensemble ELO+Poisson+XGB): "
                f"{t1} {hw*100:.0f}% | Empate {d*100:.0f}% | {t2} {aw*100:.0f}%"
            )
        else:
            prob_str = "Predicción no disponible (partido no definido aún)"

        text = (
            f"Partido: {flag1}{t1} vs {flag2}{t2}\n"
            f"Competencia: {group}, {round_}\n"
            f"Fecha: {date} · Sede: {ground}\n"
            f"{prob_str}"
        )
        out.append({"id": f"match_{date}_{t1.lower().replace(' ','_')}_vs_{t2.lower().replace(' ','_')}",
                    "type": "match", "team1": t1, "team2": t2,
                    "date": date, "group": group, "text": text})
    return out


def chunks_groups(groups: dict, standings: dict, teams: dict) -> list[dict]:
    out = []
    for grp, team_list in groups.items():
        flags = " ".join(teams.get(t, {}).get("flag","") + t for t in team_list)
        st_rows = standings.get(f"Group {grp}", standings.get(grp, []))
        st_text = ""
        if st_rows:
            lines = []
            for row in st_rows:
                lines.append(
                    f"  {row.get('pos','?')}. {row.get('team','')} — "
                    f"{row.get('pts',0)}pts "
                    f"({row.get('played',0)}J {row.get('won',0)}G {row.get('drawn',0)}E {row.get('lost',0)}P) "
                    f"GF:{row.get('gf',0)} GC:{row.get('gc',0)} DG:{row.get('gd',0):+d}"
                )
            st_text = "\nClasificación actual:\n" + "\n".join(lines)
        text = (
            f"Grupo {grp}: {flags}\n"
            f"Equipos: {', '.join(team_list)}"
            f"{st_text}\n"
            f"Clasifican: top 2 directo + mejores 8 terceros van a Ronda de 32"
        )
        out.append({"id": f"group_{grp.lower()}", "type": "group",
                    "group": grp, "text": text})
    return out


def chunks_stadiums(stadiums: dict) -> list[dict]:
    out = []
    for ground, s in stadiums.items():
        alt_note = ""
        if s["altitude_m"] > 1500:
            alt_note = f" ⚠️ ALTITUD EXTREMA ({s['altitude_m']}m) — puede afectar el rendimiento."
        elif s["altitude_m"] > 600:
            alt_note = f" (altitud moderada: {s['altitude_m']}m)"
        text = (
            f"Estadio: {s['name']} ({ground})\n"
            f"Ciudad: {s['city']}, {s['country']}\n"
            f"Capacidad: {s['capacity']:,} espectadores{alt_note}\n"
            f"Superficie: {s['surface']}\n"
            f"Nota: {s['note']}"
        )
        out.append({"id": f"stadium_{ground.lower().replace(' ','_').replace('/','_').replace('(','').replace(')','')[:40]}",
                    "type": "stadium", "ground": ground, "text": text})
    return out


def chunks_live_results(live_path: Path) -> list[dict]:
    if not live_path.exists():
        return []
    try:
        df = pd.read_csv(live_path)
    except Exception:
        return []
    out = []
    for _, row in df.iterrows():
        text = (
            f"Resultado oficial: {row['home_team']} {int(row['home_score'])}-{int(row['away_score'])} {row['away_team']}\n"
            f"Fecha: {row['date']} · Sede: {row.get('city','?')}\n"
            f"Torneo: {row.get('tournament','FIFA World Cup 2026')}"
        )
        out.append({"id": f"result_{row['date']}_{row['home_team'].lower().replace(' ','_')}",
                    "type": "result",
                    "text": text})
    return out


def chunks_history() -> list[dict]:
    facts = [
        ("wc_champions", "Campeones del Mundial por edición:\n"
         "2022 Argentina · 2018 Francia · 2014 Alemania · 2010 España · 2006 Italia · "
         "2002 Brasil · 1998 Francia · 1994 Brasil · 1990 Alemania Occ. · 1986 Argentina · "
         "1982 Italia · 1978 Argentina · 1974 Alemania Occ. · 1970 Brasil · 1966 Inglaterra · "
         "1962 Brasil · 1958 Brasil · 1954 Alemania Occ. · 1950 Uruguay · 1938 Italia · "
         "1934 Italia · 1930 Uruguay\n"
         "Más títulos: Brasil 5, Alemania 4, Italia 4, Argentina 3, Francia 2, Uruguay 2, España 1, Inglaterra 1"),
        ("wc_top_scorers", "Máximos goleadores de la historia del Mundial:\n"
         "1. Miroslav Klose (Alemania) 16 goles · 2. Ronaldo (Brasil) 15 · 3. Gerd Müller (Alemania) 14 · "
         "4. Just Fontaine (Francia) 13 · 5. Pelé (Brasil) 12 · 6. Ronaldo (Brasil, dist.) ya contado · "
         "7. Sándor Kocsis (Hungría) 11 · 8. Jürgen Klinsmann (Alemania) 11\n"
         "Goleador de Qatar 2022: Kylian Mbappé (Francia) 8 goles"),
        ("wc_2026_format", "Formato del Mundial 2026:\n"
         "48 equipos divididos en 12 grupos de 4. Clasifican top 2 + mejores 8 terceros = 32 equipos a Ronda de 32 (R32). "
         "Luego R16 (Octavos), Cuartos de final, Semifinales, Final.\n"
         "Sedes: 11 ciudades en USA + 3 en México + 2 en Canadá = 16 estadios.\n"
         "Primer partido: México vs Sudáfrica (11 Jun, Estadio Azteca).\n"
         "Final: 19 Jul 2026, Rose Bowl, Pasadena, California."),
        ("wc_2026_hosts", "Países anfitriones del Mundial 2026:\n"
         "🇺🇸 Estados Unidos (11 sedes): Rose Bowl, MetLife, AT&T, SoFi, Levi's, Lumen Field, "
         "Arrowhead, Lincoln Financial, Gillette, Hard Rock, Mercedes-Benz.\n"
         "🇲🇽 México (3 sedes): Estadio Azteca (CDMX), Estadio Akron (Guadalajara), Estadio BBVA (Monterrey).\n"
         "🇨🇦 Canadá (2 sedes): BC Place (Vancouver), BMO Field (Toronto)."),
        ("wc_altitude_note", "Impacto de la altitud en el fútbol:\n"
         "Estadio Azteca (CDMX): 2,240 metros — nivel de oxígeno ~20% menor que en el nivel del mar. "
         "Equipos europeos y africanos no aclimatados sufren mayor fatiga y pérdida de velocidad. "
         "Estadio Akron (Guadalajara): 1,566 metros — altitud moderada-alta. "
         "Solo México y Canadá juegan al nivel del mar (Toronto, Vancouver) o casi."),
        ("elo_system", "Sistema ELO del predictor:\n"
         "El ELO mide la fortaleza relativa de cada selección basándose en todos sus resultados históricos. "
         "K=60 para partidos de Copa del Mundo (máximo impacto), K=20 para amistosos. "
         "Un ELO alto (>2000) indica equipo de élite mundial. "
         "Los ratings se actualizan después de cada partido con multiplicador por goleada."),
    ]
    return [{"id": f"history_{fid}", "type": "history", "text": txt}
            for fid, txt in facts]


# ── Main ───────────────────────────────────────────────────────────────────────
def main() -> None:
    print("═" * 60)
    print("  build_rag_index.py — Mundial Predictor 2026")
    print("═" * 60)

    # Cargar datos
    print("\n[1/4] Cargando datos…")
    teams    = json.loads(TEAMS_PATH.read_text(encoding="utf-8")) if TEAMS_PATH.exists() else {}
    preds    = json.loads(PREDICTIONS_PATH.read_text(encoding="utf-8")) if PREDICTIONS_PATH.exists() else {}
    groups   = json.loads(GROUPS_PATH.read_text(encoding="utf-8")) if GROUPS_PATH.exists() else {}
    standings = json.loads(STANDINGS_PATH.read_text(encoding="utf-8")) if STANDINGS_PATH.exists() else {}
    fixture_data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8")) if FIXTURE_PATH.exists() else {}
    fixture  = fixture_data.get("matches", [])
    stadiums = json.loads(STADIUMS_PATH.read_text(encoding="utf-8")) if STADIUMS_PATH.exists() else {}

    print(f"  teams: {len(teams)} · predictions: {len(preds)} · fixture: {len(fixture)} partidos")
    print(f"  groups: {len(groups)} · stadiums: {len(stadiums)}")

    # Crear chunks
    print("\n[2/4] Generando chunks de texto…")
    chunks: list[dict] = []
    chunks += chunks_teams(teams)
    chunks += chunks_fixture_predictions(fixture, preds, teams)
    chunks += chunks_groups(groups, standings, teams)
    chunks += chunks_stadiums(stadiums)
    chunks += chunks_live_results(LIVE_PATH)
    chunks += chunks_history()
    print(f"  Total chunks: {len(chunks)}")

    # Embeddings
    print("\n[3/4] Generando embeddings con Qwen3 text-embedding-v3 (dim={EMBED_DIMS})…")
    client = get_embed_client()
    texts = [c["text"] for c in chunks]
    vectors = embed_all(client, texts)
    print(f"  OK — {len(vectors)} vectores de {EMBED_DIMS} dimensiones")

    # Adjuntar embeddings a chunks
    for chunk, vec in zip(chunks, vectors):
        chunk["embedding"] = vec

    # Guardar índice
    print("\n[4/4] Guardando índice…")
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    index = {
        "model":      EMBED_MODEL,
        "dimensions": EMBED_DIMS,
        "created_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
        "n_chunks":   len(chunks),
        "chunks":     chunks,
    }
    OUT_PATH.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    size_kb = OUT_PATH.stat().st_size / 1024
    print(f"  Guardado en: {OUT_PATH}")
    print(f"  Tamaño: {size_kb:.0f} KB ({len(chunks)} chunks)")
    print("\n✓ Índice RAG listo. Ahora puedes usar el Chat en el frontend.")


if __name__ == "__main__":
    main()
