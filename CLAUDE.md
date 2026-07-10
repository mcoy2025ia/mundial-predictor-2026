# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🟡 TOURNAMENT STATUS
**WC 2026 KNOCKOUT PHASE IN PROGRESS** (Group Stage completed Jun 27; R32 done 16/16; R16 done 8/8; Quarter-finals underway as of 2026-07-09 — France 2-0 Morocco played, Spain-Belgium/Norway-England/Argentina-Switzerland pending; Final is Jul 19, 2026)
- **Bracket resolution:** The knockout fixture (`data/external/wc2026_fixture.json`) ships with placeholders (`1A`, `2B`, `3A/B/C/D/F`, `W73`) instead of real teams. `src/bracket.py` resolves them progressively from `wc2026_live_results.csv` as each round is played — `predict_live.py` and `agent_debate.py` consume the resolved bracket automatically. See [Knockout Bracket Resolution](#knockout-bracket-resolution) under Architecture.
- **Current ops:** Full matchday cycle applies for every knockout round (no more `update_third_place_probs.py` 3×/day — that was group-stage-only). After `predict_live.py --export`, also run `export_knockout_bracket.py` and `run_upset_agent.py` (see Quick Reference below).
- **Known permanent gap (R32/R16/QF1):** Agent Debate is forward-only by design and didn't run at all during the Jun 28–Jul 9 CI outage (see below), so those ~25 already-played knockout matches were never debated *before* being played. The Modelo tab's per-round agent-accuracy breakdown will show sparse/empty data for R32/R16/QF1 — this cannot be fixed retroactively, only going forward from QF2 onward.
- **CI outage (fixed 2026-07-09):** The workflow's cron schedule was hand-crafted per exact group-stage kickoff and had zero entries after Jun 28 — the pipeline didn't run once for the entire knockout phase until this was caught and fixed with a periodic bounded schedule. See the Critical Gotchas section below ("Knockout Result Fetching Needs Multiple Passes").
- **Knockout dialects:** Restricted to `bogotano` only (`DIALECTS_KNOCKOUT` in `precompute_narrations.py`) — changed 2026-07-09 by explicit user decision. Knockout has many matches in quick succession (R32→Final) without the group stage's slack; 5 dialects/match was 5x the cost/time for no proportional benefit.
- **Agent Debate:** High-priority for knockout matches (budget 0.08–0.10 USD/match); run before each R32/R16/QF/SF/Final. A 4th voice, **Cazador de Sorpresas** (`src/upset_agent.py`), always argues the underdog's case — separate from the 3-agent debate/consensus.
- **Frontend:** **Grupos** tab, best-thirds, and group narratives are hidden during knockout. **Eliminatorias** (R32) and **Octavos** (R16) tabs render `KnockoutBracket.tsx` from `knockout_bracket.json`.
- **Memory System:** Auto-memory at `~/.claude/projects/mundial-predictor-master/memory/` tracks roadmap phases, UI changes, and model improvements across conversations — check it for the latest known match/round status, since this file is not re-verified against live data on every edit.
- **See Also:** `docs/runbook.md` for daily operational cycles, `docs/finops.md` for AI cost tracking

> ⚠️ This document is tournament-specific (WC 2026: Jun 11 – Jul 19, 2026) and describes an operational system with daily data-refresh cycles. Dates, phases (J1/J2/J3, R32/R16/QF/SF), and "current" match state go stale between edits — treat them as directional, and check `git log`, `data/external/wc2026_live_results.csv`, or the memory system for the actual current state before assuming a specific round is "next."

---

## Quick Reference: Daily Matchday Cycle

```bash
# After each matchday (group or knockout), run this sequence (~90s total):
python scripts/live_update.py              # Fetch results → retrain model
python scripts/predict_live.py --export    # Update live predictions (anti-leakage cutoff)
python scripts/precompute_narrations.py    # Regenerate narrations × dialects (all 5 in knockout)
cd frontend && npx vercel --prod           # Deploy
```

**Knockout phase (Jun 28–Jul 19):** Same full cycle above, plus the bracket export. The knockout fixture uses placeholders (`1A`, `2B`, `3A/B/C/D/F`, `W73`) that `src/bracket.py` resolves from real results — `predict_live.py` and `agent_debate.py` consume this automatically. After `predict_live.py --export`, also run:

```bash
python scripts/export_knockout_bracket.py     # → knockout_bracket.json (R32 + R16 feeders, drives Eliminatorias/Octavos tabs)
python scripts/run_agent_debate.py "Home" "Away" ...   # cross-group debates now work (knockout framing)
python scripts/run_upset_agent.py                       # Cazador de Sorpresas → upset_predictions.json (4ª voz en el panel)
python scripts/export_frontend_data.py                  # publishes agent debate results
cd frontend && npx vercel --prod
```

Frontend in knockout: the **Grupos** tab, best-thirds, and group narratives are hidden; **Eliminatorias** (R32) and **Octavos** (R16) tabs render the resolved bracket with model probs + AgentDebatePanel (which now also shows the Cazador de Sorpresas upset pick).

**Ensemble recalibration** (run after every ~4 played WC 2026 matches to improve weights):
```bash
python scripts/calibrate_ensemble_2026.py --apply   # updates ensemble.py weights in-place
```

**MD2 Double-Run (Jun 18–23 afternoon/evening blocks):** *(historical — group stage complete)* Run the full cycle twice per day to capture afternoon results before evening predictions.

**MD3 Simultaneous Matches (Jun 24–27):** *(historical — complete)* CI ran `update_third_place_probs.py` 3×/day.

---

## Quick Command Reference

| Task | Command |
|------|---------|
| **Setup** | `python -m venv .venv && .venv\Scripts\activate && pip install -r requirements.txt && cd frontend && npm install` |
| **Full pipeline** | `python scripts/run_pipeline.py` |
| **Live update (all steps)** | `python scripts/live_update.py` |
| **Live predictions only** | `python scripts/predict_live.py --export` |
| **Narrations only** | `python scripts/precompute_narrations.py` |
| **Agent debate** | `python scripts/run_agent_debate.py "Team1" "Team2" && python scripts/export_frontend_data.py` |
| **Recalibrate ensemble** | `python scripts/calibrate_ensemble_2026.py --apply` |
| **Export knockout bracket** | `python scripts/export_knockout_bracket.py` |
| **Run upset agent (Cazador de Sorpresas)** | `python scripts/run_upset_agent.py` |
| **All tests** | `pytest` |
| **Single test** | `pytest tests/test_model.py::test_temporal_split_no_leakage` |
| **Frontend dev** | `cd frontend && npm run dev` (http://localhost:3000) |
| **Streamlit app** | `streamlit run src/app.py` |
| **Vercel status** | `vercel status` |
| **Vercel deploy preview** | `vercel` (from project root) |
| **Vercel deploy production** | `vercel --prod` or `cd frontend && npx vercel --prod` |

---

## Task Decision Tree

| I need to... | Run this | Why |
|---|---|---|
| See what's playing today / current standings | `cd frontend && npm run dev`, check "Live" tab | Frontend loads live results from `/api/live`; no script needed |
| Sync predictions + narratives after a matchday | Full cycle (see Quick Reference above) | Predictions, narrations, and bracket must stay in sync with each other |
| Get fresh 1X2 probabilities without a full retrain | `python scripts/predict_live.py --export` | Uses live ELO cutoff; cheap, no LLM cost |
| Add reasoning/debate to specific upcoming matches | `python scripts/run_agent_debate.py "Home" "Away"` | Forward-only, ~$0.08–0.10/match — reserve for high-profile matches |
| Get the underdog case for a knockout cross | `python scripts/run_upset_agent.py` | Cazador de Sorpresas — always argues the less-favored team |
| Resolve/refresh the knockout bracket (who plays whom) | `python scripts/export_knockout_bracket.py` | Reads `src/bracket.py` resolution, writes `knockout_bracket.json` for the frontend |
| Improve model accuracy after ~4 new played matches | `python scripts/calibrate_ensemble_2026.py --apply` | Recalibrates ELO/Poisson/XGB blend weights in-place |
| Diagnose a prediction that looks wrong | See "Debugging Predictions" under Troubleshooting | Checks leakage, component disagreement, ELO sanity, calibration |
| Ship changes to production | Full cycle + `cd frontend && npx vercel --prod` | Static JSON must be regenerated *and* deployed — code changes alone don't update predictions |

---

## Critical Gotchas

### JSON Encoding (UTF-8)
**IMPORTANT:** Files under `frontend/public/data/` must use UTF-8 encoding. **Do NOT rewrite JSON with PowerShell `Get-Content | Set-Content`** — this causes encoding corruption (mojibake: `MÃ©xico`, `arrancÃ³`, `Â`, `â€`, `ðŸ`). Always use Python scripts (`Path.write_text(..., encoding="utf-8")`) or Node.js for JSON generation.

### Live Predictions Anti-Leakage
`scripts/predict_live.py` enforces a strict cutoff: `features_cutoff = kickoff - 60s`. Any match where `features_cutoff >= match_kickoff` aborts with an error. This prevents using a match's own result as a feature in its own prediction.

### DeepSeek-Reasoner Token Limits
`deepseek-reasoner` (used in group narratives and agent debate) counts thinking tokens against `max_tokens`. If the reasoning phase consumes the entire budget, the final `content` returns as an empty string with a 200 OK (no exception). `precompute_narrations.py` falls back to `deepseek-chat` if this occurs, and treats empty strings as "not generated yet" to allow retries.

### Agent Debate Forward-Only
Agent Debate runs *before* a match is played and accumulates results into `data/processed/agent_debate_results.json`. There is no retroactive backfill of already-played matches (cost/time tradeoff). Accuracy tracking in "Modelo" tab only reflects matches debated *and then played after* the debate ran.

### Frontend Data Flow
Pre-computed data (narrations, group previews, predictions) must be exported to `frontend/public/data/` and deployed. Local `frontend/src/lib/live.ts` fetches live results from `/api/live` (server-side proxy to football-data.org). The simulator uses client-side Monte Carlo — no backend call needed.

### Knockout Result Fetching Needs Multiple Passes
`update_wc_results.py` only resolves and appends a knockout cross to `results.csv` once its feeder round is already filled (R32 unlocks R16, R16 unlocks QF, etc.). If you're catching up after a gap of more than one round, **a single run will not converge** — it fetches one round's worth, appends the newly-unlocked next round's crosses, but doesn't loop within the same run. Run it repeatedly (`for i in 1 2 3 4; do python scripts/update_wc_results.py; done` or similar) until it reports "Sin cambios — todos los partidos ya están al día." `live_update.py`'s single internal call has this same limitation.

---

## Troubleshooting

| Problem | Diagnosis | Fix |
|---------|-----------|-----|
| **Live predictions are stale** | Run `git status` to check if `frontend/public/data/live_predictions.json` is out of date | `python scripts/predict_live.py --export && cd frontend && npx vercel --prod` |
| **Narrations show mojibake (MÃ©xico)** | PowerShell rewrote a JSON file with wrong encoding | Delete the corrupted file and regenerate: `rm frontend/public/data/narrations.json && python scripts/precompute_narrations.py` |
| **Chat/API failing silently** | Check rate limiter (20 req/hour/IP), cache, topic filter in order | See `frontend/src/app/api/chat/route.ts` layers 1–3; test with curl: `curl -X POST http://localhost:3000/api/chat -d '{"message":"..."}' -H "Content-Type: application/json"` |
| **Agent Debate produced empty string** | deepseek-reasoner hit token limit (max_tokens=4500 for consensus) | Reduce context size or retry later; fallback to `deepseek-chat` (no reasoning phase) is automatic |
| **live_update.py returns exit code 1** | Data fetch or model training failed | Check `logs/pipeline_runs.jsonl` for error entry; re-run with `--dry-run` to preview |
| **Model RPS is worse than baseline** | Feature set or temporal split is broken | Verify test set is Qatar 2022 (not random), FEATURE_COLS are present, no leakage via `pytest tests/test_model.py::test_temporal_split_no_leakage` |
| **Narrations missing for knockout** | Pre-computed narrations only run for *today's* matches | `python scripts/precompute_narrations.py --days 1` to include tomorrow; narration endpoint has LLM fallback for missing keys |
| **Tournament context stale in chat** | Chat injects `group_standings.json` + today's `group_matches.json` at runtime | Verify `export_frontend_data.py` ran and files are deployed |
| **Knockout match shows placeholder teams (e.g. "1A vs 2B")** | That fixture slot's feeder group/round hasn't finished yet | Expected — `src/bracket.py` only resolves a slot once its source group/match is complete; re-run `export_knockout_bracket.py` once the feeder match is played |

### Debugging Predictions

If a specific prediction looks wrong or inconsistent:

1. **Check anti-leakage first.** If the match already kicked off, `predict_live.py` should still predict it correctly (cutoff = kickoff − 60s), but verify no assertion was silently caught upstream. For knockout matches, predictions run *even after kickoff* (no agents = zero leakage risk); group matches skip already-played fixtures.
2. **Inspect which ensemble component is driving it.** `streamlit run src/app.py` shows the ELO / Poisson / XGB breakdown — a prediction that looks off is often one component disagreeing sharply with the other two (e.g., Poisson sees a high-scoring history the ELO diff doesn't reflect).
3. **Check ELO sanity.** Look up both teams in `data/processed/elo_current.json`. A team that looks underrated is usually missing a recent result in `results.csv` — confirm `live_update.py` actually ran after the last matchday.
4. **Verify no leakage in the test harness.** `pytest tests/test_model.py::test_temporal_split_no_leakage` — a regression here would systematically bias every prediction, not just one match.
5. **For knockout crosses, confirm the bracket resolved correctly.** Check `frontend/public/data/knockout_bracket.json` — a mis-assigned third-place team or wrong feeder match will produce a prediction for the wrong pair of teams. `wc2026_knockout_fixture.json` (cached from the football-data.org API) is the source of truth for third-place slot assignment, not the local backtracking algorithm.

---

## Table of Contents
- [Tournament Status & Quick Reference](#🔴-tournament-status)
- [Quick Command Reference](#quick-command-reference)
- [Task Decision Tree](#task-decision-tree)
- [Critical Gotchas](#critical-gotchas)
- [Troubleshooting](#troubleshooting)
- [Project Overview](#project-overview)
- [Documentation Guide](#documentation-guide)
- [WC 2026 Operations](#during-wc-2026-operations)
- [Development Commands](#development-commands)
- [Architecture](#architecture)
- [Vercel Deployment](#vercel-deployment)
- [Key Decisions & Patterns](#key-decisions--patterns)
- [File Structure](#file-structure-summary)
- [Common Workflows](#common-workflows)
- [Testing Strategy](#testing-strategy)
- [Environment & Secrets](#environment--secrets)

---

## Project Overview

**Mundial Predictor 2026** is an end-to-end ML pipeline for predicting FIFA World Cup results using XGBoost with custom ELO ratings, feature engineering, Monte Carlo tournament simulation, live match tracking, and an AI chat assistant.

**Key characteristics:**
- Python backend: data extraction → ELO calculation → feature engineering → XGBoost training/evaluation
- Next.js frontend: live tournament tracking, match predictor, Monte Carlo projections, multi-dialect (bogotano/paisa/boyaco/costeño/en)
- Live update pipeline: fetches WC 2026 results from football-data.org → updates CSV → retrains model automatically
- Client-side Monte Carlo simulator (runs in browser on pre-calculated team pairs)
- Temporal split strategy (test = Qatar 2022 to avoid leakage in time-series data)
- **Narrator AI** — pre-computed match narrations and group previews (DeepSeek, run once/twice per day depending on matchday) stored in `narrations.json` and `group_narratives.json`; zero LLM calls per user for cached content, Bogotá/neutral Spanish during group-stage stabilization, group standings context from MD2 onward
- AI chat assistant (DeepSeek + RAG with DashScope embeddings) with topic filter, response cache, rate limiting, and live tournament context injection
- Multi-agent system (Orchestrator + 7 specialists) that enrich predictions with contextual analysis when API budget allows. Agents are fed real derived evidence (form, H2H, goal trends, scorers, third-place math) via `src/agents/match_intel.py` — they reason from data, not team names
- Knockout bracket resolution (`src/bracket.py`) resolves fixture placeholders (`1A`, `2B`, `3A/B/C/D/F`, `W73`) to real teams as each round completes, feeding both `predict_live.py` and `agent_debate.py`
- 157 pytest tests covering extraction, features, model training, agents, simulation, integrity, bracket resolution, and live prediction

---

## Documentation Guide

This repository includes supporting documents organized by purpose. **Consult them when**:

### Operational & Architecture (docs/)
- **`docs/runbook.md`** — **Daily WC 2026 operations.** Complete cycle, J2/J3 double-run protocols, verification checklist, emergency fallback. Start here if you're deploying after a matchday.
- **`docs/architecture.md`** — **System thesis:** 4-layer design (Statistical Benchmark → Tournament Context → Cached Narratives → Agent Debate & Evaluation). Clarifies which layer produces which claim (ML vs agents vs simulator vs narrator).
- **`docs/finops.md`** — **AI cost strategy & budget tracking.** Current spend snapshot, cost-per-match breakdown (Agent Debate ~0.08–0.10 USD, Narrator ~0.016 USD, Specialists ~0.01–0.02 USD), projections through knockout, model use boundaries.
- **`docs/ml-validation.md`** — Model validation approach and performance benchmarks.

### Project & Model Design
- **`proyecto.md`** — Project definition, deliverables (E1–E5), acceptance criteria. Essential for WC 2026 window priorities (Jun 11 – Jul 19, 2026).
- **`model_card.md`** — Model performance, walk-forward validation results, ensemble weights (22% ELO + 58% Poisson + 20% XGB), feature ablation.
- **`guia.md`** — Technical roadmap (Phases 0–6) and design decisions (D1–D6).
- **`methodology.md`** — Model limitations and responsible-use statement.

### Implementation Reference
- **`contracts/`** — Data schemas and contracts (prevent silent failures). `data_contracts.md` specifies `results.csv`, features, and exported JSONs format; `module_contracts.md` specifies feature/model input-output contracts (incl. `DEFAULT_WEIGHTS`); `core_model_contracts.md` covers the must-have deterministic core (ELO/Poisson/XGB/Ensemble/Simulator); `agent_enrichment_contracts.md` covers the optional LLM agent layer (degrades to delta=0, never required).
- **`agent/*.md`** — Each specialist agent (e.g., `IntMatch-Analytics-Pro.md`, `FinOps-Market-Calibration-Validator.md`) documents role, input context, output (delta_P adjustment), and cost profile. `orchestrator.md` documents the routing/blending logic itself. Note: `GroupScenario-Reasoner` (classification pressure + third-place math) has no spec file yet — infer its contract from `src/agents/specialists/group_scenario.py`.
- **`README.md`** — Quick-start for new developers; external marketing.
- **`QUICK_START.md`** — 2-minute external-facing summary (what it is, what it does, is it production-ready) for evaluators/recruiters who won't read the full README.
- **`docs/system_overview.md`** — 10-minute deep-dive for AI architects/recruiters/new devs: full architecture, data flow, and design-decision walkthrough in one document.
- **`retrospective.md`** — Post-tournament template (model baseline vs. walk-forward vs. actual WC 2026 RPS); intentionally blank until after the Jul 19 final.
- **`AGENTS.md`** — Equivalent of this file for OpenAI Codex; kept in sync with CLAUDE.md by convention (see commit history for "sync AGENTS.md" commits). If you update architecture/ops content here, mirror it there.
- **`instructivo-github-actions.md`** — One-time setup guide for the 6 GitHub Actions secrets (`FOOTBALL_DATA_TOKEN`, `DEEPSEEK_API_KEY`, `ANTHROPIC_API_KEY`, `VERCEL_TOKEN`, etc.) that `.github/workflows/wc2026-live-update.yml` needs to run scheduled updates. Consult if the CI workflow is failing with an auth/missing-secret error.

---

## During WC 2026 Operations (Jun 11 – Jul 19, 2026)

**See `docs/runbook.md` for daily protocols.** The tournament has three phases with distinct workflows:

### Matchday Cycles (J1, J2, J3)
Run **after each group-stage matchday** to sync predictions and narratives with real results:

```bash
python scripts/live_update.py                # Fetch results, retrain model
python scripts/predict_live.py --export      # Update probabilities with live ELO cutoff
python scripts/precompute_narrations.py      # Regenerate match + group narratives
cd frontend && npx vercel --prod             # Deploy
```

### J2 Double-Run Protocol
Matchday 2 (Jun 18–23) has afternoon and evening blocks in the same day. **Run twice:**
1. **Before afternoon matches:** Full cycle with morning predictions
2. **After afternoon results:** Re-run `predict_live.py --export` + `precompute_narrations.py` so evening matches see updated pressure and qualification paths

### J3 Simultaneous Matches (Jun 24–27)
Matchday 3 has group matches kicking off simultaneously. Narratives must emphasize:
- Direct qualification scenarios (not assumed sequential results)
- Goal difference and best-third qualification pressure
- Scenarios and probabilities, not deterministic claims

**Third-place updates run 3×/day** (not the full cycle). Since simultaneous matches don't change narrations, the CI runs `scripts/update_third_place_probs.py` (Monte Carlo only, ~5s) at the fixture's three daily windows to refresh best-third probabilities. The workflow auto-detects J3 (Jun 24–27) and takes the light path; outside J3 it runs the full cycle. Timings are in `.github/workflows/wc2026-live-update.yml` and documented in `instrucciones2.md`.

### Cost & Agent Debate
- **Group stage:** Narrator in Bogotá/neutral Spanish only (budget stability)
- **Knockout stage:** Bogotano only (changed 2026-07-09 — too many matches in quick succession to justify 5x cost/time per match)
- **Agent Debate:** Reserve for high-context matches; costs 0.08–0.10 USD per match (5–6× more than narration)

See `docs/finops.md` for current spend snapshot and projections.

---

## Development Commands

### Setup

```bash
# Python environment
python -m venv .venv
.venv\Scripts\activate  # Windows
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
cd ..
```

### Pipeline & Model Training

```bash
# Run full pipeline: raw data → ELO → features → model training → metrics
python scripts/run_pipeline.py

# Export pre-computed data for frontend (JSONs with model predictions)
python scripts/export_frontend_data.py

# Live predictions with anti-leakage (cutoff = kickoff - 60s)
python scripts/predict_live.py            # pending matches only
python scripts/predict_live.py --all      # all matches (including played)
python scripts/predict_live.py --export   # also write to frontend/public/data/
python scripts/predict_live.py --add-result HOME AWAY HS AS DATE  # record a result

# Feature ablation: test whether rest-days improve RPS before adding to FEATURE_COLS
python scripts/ablation_features.py

# (Optional) Enrich goalscorer stats
python scripts/enrich_goalscorers.py
```

### Live Update (WC 2026 — use after each matchday)

```bash
# Full cycle: fetch results → retrain → export JSONs (runs ~90s)
python scripts/live_update.py

# Preview what would be fetched without writing anything
python scripts/live_update.py --dry-run

# Force retrain even if no new matches
python scripts/live_update.py --force

# Only fetch and update results.csv (skip retrain)
python scripts/update_wc_results.py --dry-run
```

### Daily Narrations & Group Previews (run after live_update + predict_live)

```bash
# Generate narrations for TODAY's matches × dialects → frontend/public/data/narrations.json
# Group stage: Bogotá/neutral Spanish only while the flow is stable.
# Knockout: all 5 dialects auto (~$0.015/run).
python scripts/precompute_narrations.py

# Extend window to include tomorrow's matches (default is today only)
python scripts/precompute_narrations.py --days 1

# Recompute only group narrative previews → frontend/public/data/group_narratives.json (today only)
python scripts/precompute_narrations.py --groups-only
```

The script targets **today's matches and group previews only** (no future days). It uses **context-based caching**: a today narration/preview is regenerated only if that group's context changed since the last run of the day (standings, points, pressure, agent notes) — tracked by signature in `data/processed/narrations_sig.json` and `group_narratives_sig.json` (internal, gitignored). If nothing changed for a group, the morning's narration is kept as-is and no tokens are spent. This is what makes the MD2 afternoon re-run cheap: it only regenerates the group that actually played in the afternoon, not all of today's groups. Delete the `*_sig.json` files to force a full regeneration. This mirrors `predict_live.py`'s agent cache (same principle: re-call the LLM only when a match's group context actually changed; `--force-agents` to override).

Group previews must analyze each team individually, not only the group as a whole. The payload includes standings, match schedule, local venue, live predictions, prior group results, and deterministic `team_profiles` with:
- current points and goal difference
- previous result and opponent
- estimated strength of the previous opponent using model probabilities
- result quality (`muy alta`, `positiva`, `normal`, `preocupante`, or no evidence)
- likely mood, pressure, dependency, next opponent, and next match probability

J2/MD2 has a double-run protocol: run the full cycle before the first match window, then run it again after the first two results are in so evening predictions and narratives reflect real qualification pressure. J3/MD3 focuses on simultaneous group matches and best-third qualification scenarios.

Encoding rule: JSON files under `frontend/public/data/` must remain UTF-8. Do not rewrite generated JSON with PowerShell `Get-Content | Set-Content`; use Python scripts or `Path.write_text(..., encoding="utf-8")`. Watch for mojibake markers such as `MÃ©xico`, `arrancÃ³`, `Â`, `â€`, or `ðŸ`.

Full deploy cycle:
```bash
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py
cd frontend && npx vercel --prod
```

### Agent Debate System (logic-based predictions, run after the cycle above)

```bash
# Run the 3-agent debate for specific matches (HOME AWAY pairs)
# Captures 4 predictions per match: Group Analyst, Tactical Scout, Sentiment Reader, + Consensus
# Accumulates into data/processed/agent_debate_results.json — idempotent, skips matches
# already debated unless --force
python scripts/run_agent_debate.py "Mexico" "South Korea" "Scotland" "Morocco"

# Re-run a specific match even if already debated (e.g. after a prompt change)
python scripts/run_agent_debate.py --force "Mexico" "South Korea"

# Publish results to the frontend (also exports teams/predictions/etc as usual)
python scripts/export_frontend_data.py
```

**Output format:** Each match now includes 4 structured predictions:
- `group_analyst`: Group classification context prediction
- `tactical_scout`: Tactical/matchup prediction
- `sentiment_reader`: Psychological/momentum-based prediction
- `consensus`: Blended ranking from all 3 agentes

Forward-only by design: the debate only runs for matches you explicitly pass on the CLI (typically upcoming ones). There is no retroactive backfill of already-played matches — accuracy tracking in the "Modelo" tab only reflects matches debated *and* played after the debate ran.

### Testing

```bash
# Run all tests
pytest

# Run tests for a specific module
pytest tests/test_model.py
pytest tests/test_features.py
pytest tests/test_simulator.py
pytest tests/test_extractor.py
pytest tests/test_agents.py
pytest tests/test_cost_guard.py
pytest tests/test_integrity.py
pytest tests/test_poisson.py
pytest tests/test_predict_live.py
pytest tests/test_simulator_parity.py
pytest tests/test_agent_debate.py
pytest tests/test_match_intel.py
pytest tests/test_pipeline_logger.py
pytest tests/test_precompute_narrations.py
pytest tests/test_bracket.py

# Verbose with output
pytest -v

# Run a single test
pytest tests/test_model.py::test_temporal_split_no_leakage

# Test count: 157 tests across core pipeline, agents, cost guard, bracket resolution, and integrity checks
```

### Development Servers

```bash
# Streamlit demo app (local, shows model output)
streamlit run src/app.py

# Next.js frontend dev server (http://localhost:3000)
cd frontend
npm run dev
```

### Build

```bash
# Build Next.js for production
cd frontend
npm run build
npm start
```

### Linting

```bash
cd frontend
npm run lint
```

---

## Vercel Deployment

**Deployment Context:** This is a Vercel-hosted Next.js 15 app with Python backend scripts (ML model, narrations, agent debate). Frontend data is pre-computed and deployed as static JSON. No real-time LLM calls per user except chat/narrator (cached).

### Deploy Sequence (After Matchday)

```bash
# 1. Update model + export data (~90s)
python scripts/live_update.py              # Fetch results, retrain, export JSONs
python scripts/predict_live.py --export    # Update live predictions
python scripts/precompute_narrations.py    # Regenerate narrations

# 2. Verify files exist and are UTF-8 clean
ls -la frontend/public/data/*.json

# 3. Deploy to production (from frontend dir or project root)
cd frontend && npx vercel --prod
# OR from project root:
vercel --prod --cwd frontend

# 4. Verify deployment succeeded
vercel status
# Check Vercel dashboard: vercel.com/projects/mundial-predictor
```

### Preview vs. Production

- **Preview deployment** (`vercel` or `vercel --confirm=false`): Generates a unique URL for testing, doesn't update live site
- **Production deployment** (`vercel --prod`): Updates the live `mundial-predictor.vercel.app` domain — impacts all users immediately

During tournament operations, always use `--prod` after testing locally.

### Environment Variables (Vercel Dashboard)

All secrets are stored in Vercel project settings, not in code:

| Var | Scope | Purpose |
|-----|-------|---------|
| `FOOTBALL_DATA_TOKEN` | Production | Live match results from football-data.org |
| `DEEPSEEK_API_KEY` | Production | AI narrations, chat, agent debate |
| `DASHSCOPE_API_KEY` | Production | Query embeddings for chat RAG (Qwen3) |
| `ANTHROPIC_API_KEY` | Production | Fallback LLM for agents + narrator |

To sync local dev:
```bash
# Pull env vars from Vercel into .env.local
vercel env pull
# Or install CLI: npm i -g vercel && vercel login
```

### Common Deployment Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| **Build fails: "next.js not found"** | `npm install` not run in `frontend/` dir | `cd frontend && npm install && cd ..` then redeploy |
| **504 timeout on `/api/live`** | football-data.org API is slow or down | Check status at football-data.org; `/api/live` has 30s timeout by default |
| **Stale data on site** | Static JSON files not deployed | Verify files in `frontend/public/data/` exist and `npx vercel --prod` actually ran (check Vercel dashboard deployment list) |
| **Narrations show mojibake** | JSON encoding corruption during export | Re-run `python scripts/precompute_narrations.py` (forces UTF-8 via Python, not PowerShell) and redeploy |
| **Chat/API returns 429 (rate limit)** | 20 requests/hour/IP limit hit | Rate limit is per client IP; test with different browser/incognito; limit is intended for abuse prevention |

### Rollback (if production breaks)

```bash
# View recent deployments
vercel deployments

# Rollback to previous deployment (replace DEPLOYMENT_ID)
vercel rollback DEPLOYMENT_ID

# OR revert code and redeploy
git revert HEAD
# ... fix code ...
vercel --prod
```

### Monitoring

```bash
# Check live logs
vercel logs frontend --production

# View function invocations (API calls)
vercel logs frontend --follow
```

---

## Architecture

### Three Prediction Systems at a Glance

There are **three separate systems** that produce predictions — don't confuse them:

1. **EnsembleModel** (statistical, always runs, zero LLM cost): ELO (22%) + Poisson (58%) + XGBoost (20%). Powers `live_predictions.json` and the client-side Monte Carlo simulator. This is the fallback whenever budget is exceeded or an LLM call fails.
2. **Orchestrator + specialists** (contextual enrichment, runs automatically inside `predict_live.py`): routes each match to up to 5 specialist agents (2 in knockout) fed by `MatchIntel`'s free derived evidence (form, H2H, goal trends, third-place math). Each agent returns a `delta_P` adjustment to the Ensemble prior, clamped to 12% max total shift. No manual trigger needed — it's part of the standard live-update cycle.
3. **Agent Debate** (logic-based, opt-in, expensive): 3 personas (Group Analyst, Tactical Scout, Sentiment Reader) debate a specific match over 3 rounds using `deepseek-reasoner`, reasoning from tournament pressure/narrative rather than the trained model's probabilities. Forward-only — must be triggered explicitly per match (`run_agent_debate.py`) before it's played. In knockout, a 4th independent voice, **Cazador de Sorpresas** (`src/upset_agent.py`), always argues the underdog's case.

**When to use each:** EnsembleModel is always-on and free. Orchestrator enrichment is automatic — no action needed. Agent Debate is reserved for high-profile/high-context matches because of cost (~$0.08–0.10/match); run it deliberately, not on every match.

### Data Flow Overview

```
Raw match results → ELO ratings → Features → EnsembleModel → live_predictions.json → Frontend
                                                    ↑
                        MatchIntel evidence → Orchestrator delta_P (automatic, in predict_live.py)

Knockout only:  wc2026_fixture.json (placeholders) + live results → src/bracket.py → resolved bracket
                                                                          ↓
                                                    predict_live.py / agent_debate.py consume it

Narrations:     Match/group context → DeepSeek → narrations.json / group_narratives.json (pre-computed, cached)

Agent Debate:   Match + group standings → 3 agents × 3 rounds (deepseek-reasoner) → agent_debate_results.json
                Knockout cross → src/upset_agent.py → upset_predictions.json (4th, independent voice)
```

**See `docs/architecture.md` for the complete thesis.** The system has 4 distinct layers, each producing different claims:

| Layer | Purpose | Produces | Source |
|-------|---------|----------|--------|
| **Layer 1: Statistical Benchmark** | ML predictions without LLM calls | `live_predictions.json` (1X2 probabilities) | XGBoost + ELO + Poisson ensemble |
| **Layer 2: Tournament Context** | Current standings, pressure, qualification paths | `group_standings.json`, `group_matches.json` with scores | Real match results + fixture logic |
| **Layer 3: Cached Narratives** | Explanations and storytelling (pre-computed) | `narrations.json`, `group_narratives.json` | DeepSeek (1 call/match, cached) |
| **Layer 4: Agent Debate** | Logic-based predictions with reasoning | `agent_debate_results.json` (4 predictions: 3 agents + consensus) | DeepSeek Reasoner (9 calls/match, eval after) |

**Boundary principle:** Frontend must make clear which layer produced each claim. Don't mix agent opinions with model probabilities; don't invent narratives when LLM budget fails.

### Data Pipeline

```
data/raw/results.csv  (49k+ internationals, WC 2026 fixture pre-loaded with NA scores)
    ↓ [load_results + normalize team names]
    ↓ [filter_world_cups]
    ↓ [add_outcome: map scores to home_win/draw/away_win]
data/processed/wc_clean.csv
    ↓ [compute_elo_ratings: chronological ELO update]
data/processed/elo_current.json
    ↓ [build_feature_matrix: add H2H, form, experience]
data/processed/features.parquet
    ↓ [temporal_split: train < 2018 | calib = 2018 | test = WC 2022]
    ↓ [train XGBoost + CalibratedClassifierCV]   → models/xgb_calibrated.pkl
    ↓ [fit PoissonModel on tournament data]       → models/poisson_model.pkl
    ↓ [EnsembleModel: ELO 22% + Poisson 58% + XGB 20%]
models/{xgb_calibrated, xgb_v1, poisson_model, ensemble}.pkl
```

**Key files:**
- `src/extractor.py`: Data loading, World Cup filtering, outcome mapping, team name normalization
- `src/features.py`: ELO (K by tournament + margin multiplier + home advantage), rolling form, H2H, WC experience, tournament_weight
- `src/model.py`: XGBoost + TimeSeriesSplit calibration, temporal 3-way split (train/calib/test), RPS metric
- `src/poisson_model.py`: Bivariate Poisson (attack/defense strengths), scoreline matrix, top-5 scorelines, 1X2 aggregation
- `src/ensemble.py`: `EnsembleModel` blends ELO + Poisson + XGB with configurable weights; falls back to ELO+Poisson if XGB unavailable
- `src/simulator.py`: Monte Carlo simulation (official 2026 bracket, host home advantage)
- `src/pipeline_logger.py`: JSONL observability — appends one entry per run to `logs/pipeline_runs.jsonl` via `run_context()`
- `src/cost_guard.py`: `CostGuard` reads `configs/budget.yaml`, tracks LLM spend in `logs/llm_costs.jsonl`, raises `BudgetExceeded` to trigger deterministic fallback
- `src/agents/`: Multi-agent system — Orchestrator routes to max 2 specialists, each produces delta_P adjustments

### Live Update Pipeline

`scripts/update_wc_results.py` fetches finished WC 2026 matches from football-data.org and fills in the NA scores in `results.csv`. The CSV has the full WC 2026 fixture pre-loaded — only the `home_score`/`away_score` columns are NA until matches are played.

`scripts/live_update.py` orchestrates the full cycle:
1. `update_wc_results.py` — fills NA scores for finished matches
2. `run_pipeline.py` — recomputes ELO ratings incorporating new results, retrains XGBoost
3. `export_frontend_data.py` — regenerates all JSON files for the frontend

Exit codes from `update_wc_results.py`: `0` = no new matches, `2` = matches updated, `1` = error. `live_update.py` only re-runs the pipeline if exit code is `2` (or `--force`).

**Name normalization:** football-data.org uses different team names. `FD_NAME_MAP` in `update_wc_results.py` handles all known variants (e.g., `"Bosnia-Herzegovina"` → `"Bosnia and Herzegovina"`, `"Korea Republic"` → `"South Korea"`).

### Knockout Bracket Resolution

`data/external/wc2026_fixture.json` ships knockout crosses as placeholders instead of real teams: `1A`/`2B` (group winner/runner-up), `3A/B/C/D/F` (best third assigned from a set of groups), `W73`/`L101` (winner/loser of match #73/#101). `src/bracket.py` resolves these progressively as real results come in:

- Computes final group standings from `wc2026_live_results.csv` with FIFA tiebreakers (points → GD → GF → head-to-head) and picks the 8 best thirds.
- **Best-third assignment is API-authoritative, not self-computed.** The naive backtracking approach doesn't replicate FIFA's fixed 495-combination lookup table and mis-pairs thirds. `update_wc_results.py` caches the real bracket from football-data.org into `data/external/wc2026_knockout_fixture.json` (`stage: "LAST_32"` entries); `bracket._assign_thirds_with_api` uses that cache as the source of truth for which third-place team lands in which slot. The backtracking algorithm is only a fallback when the cache is unavailable.
- A slot only resolves once its feeder group/match is actually complete — R32 resolves as soon as groups finish; R16/QF/SF/Final resolve progressively as `W##` placeholders get real winners.
- `predict_live.py`'s `load_fixture()` calls into `bracket.py` instead of skipping every placeholder match. Knockout predictions are generated **even after kickoff** (no agents involved = zero leakage risk; the anti-leakage cutoff still excludes each match's own result). Group-stage matches still skip if already played.
- `agent_debate.py`'s `_maybe_knockout_context()` reuses `bracket.py` to build cross-group elimination framing (each team's own group campaign, no shared table or third-place pressure) — the 3 agents + consensus have `is_knockout` branches for win-or-go-home / extra-time / penalties framing.
- `scripts/export_knockout_bracket.py` publishes the resolved bracket to `frontend/public/data/knockout_bracket.json` (R32 rounds carry full ML predictions; R16+ show feeder labels like "Brazil / Japan" until both feeders resolve). It also attaches actual results + model verdict ("✓/✗ Modelo acertó") once a knockout match is played — `update_wc_results.py` materializes resolved crosses as rows in `results.csv` (`_append_knockout_fixtures`) so the live API fill picks them up like group matches.
- `frontend/src/components/KnockoutBracket.tsx` renders it; the **Eliminatorias** (R32) and **Octavos** (R16) frontend tabs replace **Grupos** once the tournament enters knockout.
- **Cazador de Sorpresas** (`src/upset_agent.py`, run via `scripts/run_upset_agent.py`): a 4th, independent agent — separate from the 3-agent debate — that always argues the underdog's case for each knockout cross with an honest plausibility score (≥0.35 = "live upset case"). Output: `upset_predictions.json`, shown as a 4th voice in `AgentDebatePanel`.
- Tests: `tests/test_bracket.py`.

### Feature Engineering

**Features used in XGBoost:**
- `elo_diff`, `elo_home`, `elo_away`: ELO ratings (pre-match)
- `home_goals_scored_avg5`, `away_goals_scored_avg5`: Average goals scored in last 5 games
- `home_goals_conceded_avg5`, `away_goals_conceded_avg5`: Average goals conceded in last 5 games
- `h2h_home_win_pct`: Head-to-head home win percentage
- `is_neutral`: Binary flag for neutral venue
- `wc_experience_diff`: Difference in World Cup appearances

**Label mapping:**
```python
{"home_win": 0, "draw": 1, "away_win": 2}
```

### Model Training

- **Train/test split:** 3-way temporal: train < 2018 | calib = 2018 | test = WC 2022 (64 games)
- **Training data:** All 49k+ internationals (use_all_matches=True); WC games weighted 1.0, friendlies 0.20
- **Base model:** XGBoost multi-class softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)
- **Ensemble:** `EnsembleModel` (default weights: ELO 22% + Poisson 58% + XGB 20%, per walk-forward validation 2026-06-17) — Poisson provides robust goal-distribution signal independent of ELO; XGB captures non-linear patterns but does not consistently improve global RPS
- **Baseline:** Logistic Regression + ELO-only for comparison
- **Metrics:** Accuracy, log-loss, Brier score, **RPS** (Ranked Probability Score — primary metric)
- **Walk-forward validation:** `scripts/walk_forward_validation.py` — folds 2006→2022, XGB vs ELO baseline
- **Feature ablation:** `scripts/ablation_features.py` — tests a candidate feature set against the base FEATURE_COLS; a feature enters `FEATURE_COLS` only if it improves global RPS

### Proyecciones tab (partially static)

The "Proyecciones" tab has two views:
- **Por ronda (Knockout)** — fully static; shows pre-computed probabilities from `predictions.json` / `live_predictions.json`. Only refreshes on deploy.
- **Simulador (Monte Carlo)** — partially dynamic; `fixedResults` (built from `liveMatches`, refreshes every 5 min) locks in played results automatically, but the probabilities for unplayed matches still come from the last `predict_live.py --export` run. Running `predict_live.py --export` + deploy is what updates the Proyecciones probabilities after each matchday.

### Simulator (Backend)

- Reads fixture (48 teams, 12 groups, knockout rounds) from `data/external/wc2026_fixture.json`
- For each simulation run:
  1. Sample match outcomes using model probabilities
  2. Update group standings (tiebreakers: goal diff, head-to-head)
  3. Advance qualified teams to knockout
  4. Penalties for draws (weighted by historical penalty conversion rates)
- Output: Win probability for each team in each round, champion distribution

### Frontend Architecture

**Technology:** Next.js 15 + React 19 + Tailwind CSS + Recharts + Framer Motion

**Data model — pre-computed, not real-time.** `frontend/public/data/` holds static JSON generated by Python scripts. The frontend reads these at page load; there are **no per-user LLM calls** for predictions, narrations, or agent debate. Chat and the narrator endpoint are the only exceptions, and even they only call an LLM live when a pre-computed key is missing. To change what users see, you always run a Python script → export JSON → deploy — editing frontend code alone never updates predictions or narratives.

| JSON file | Produced by |
|---|---|
| `live_predictions.json` | `scripts/predict_live.py --export` |
| `narrations.json`, `group_narratives.json` | `scripts/precompute_narrations.py` |
| `agent_debate_results.json` | `scripts/run_agent_debate.py` |
| `upset_predictions.json` | `scripts/run_upset_agent.py` |
| `knockout_bracket.json` | `scripts/export_knockout_bracket.py` |
| `group_standings.json`, `group_matches.json`, `teams.json`, `matches.json`, `stats.json`, `predictions.json` | `scripts/export_frontend_data.py` |

**Key files:**
- `src/app/page.tsx`: Main tabbed interface (Live Tournament, Predictor, Groups, Simulator, ChatTab, etc.)
- `src/app/api/live/route.ts`: Server-side proxy to football-data.org (no-store cache, BOM-safe token parsing)
- `src/app/api/chat/route.ts`: AI chat endpoint — topic filter + response cache + rate limit + RAG + DeepSeek streaming
- `src/app/api/narrator/route.ts`: Scenario detection & contextual metadata (stadium names, historical matchups, confederation info) for match presentation
- `src/app/api/agent-debate/route.ts`: Serves `agent_debate_results.json` (60s in-memory cache, never calls DeepSeek per request)
- `src/app/api/og/route.tsx`: Dynamic Open Graph social-share image (`@vercel/og` `ImageResponse`)
- `src/lib/simulator.ts`: Client-side Monte Carlo (runs 5,000 simulations in browser)
- `src/lib/live.ts`: Fetches live match results via `/api/live` endpoint
- `src/lib/i18n.tsx`: Dialect context — `Lang = "bogotano"|"paisa"|"boyaco"|"costeño"|"en"`. Base `_es` + 4 dialect narrator overlays; `useI18n()` / `useLang()` hooks
- `src/components/Predictor.tsx`: Match predictor UI — NarratorBanner (scenario detection + stadium info), CelebrationBurst, ColombiaPortugalOverlay, StadiumOverlay SVG, AgentDebatePanel
- `src/components/ChatTab.tsx`: Tabbed AI conversation interface with topic filtering and response caching
- `src/components/StatsTab.tsx`: WC 2026 live stats dashboard — goals KPIs, top scoring teams (bar chart), top scoring matches, score distribution, upsets (model misses sorted by lowest actual-winner probability). All computed client-side from `liveMatches` + `groupMatches` + `liveScores`. Replaces the ChatTab in the "Stats" tab (`curiosidades`).
- `src/components/ModelTab.tsx`: Live model accuracy — KPI pills, per-matchday bars, per-group grid with J1/J2/J3/FG columns (FG = group total %, count, delta vs J1), surprises section
- `src/components/KnockoutBracket.tsx`: Renders the resolved knockout bracket from `knockout_bracket.json` — model predictions for resolved R32 crosses, feeder labels (e.g. "Brazil / Japan") for unresolved later rounds, actual result + model verdict once played. Powers the **Eliminatorias**/**Octavos** tabs that replace **Grupos** during knockout.

**Data flow:**
1. Pipeline exports JSON files (`export_frontend_data.py`) to `frontend/public/data/`
2. `precompute_narrations.py` generates `narrations.json` (one DeepSeek call per match, cached) and `group_narratives.json` (one DeepSeek call per group/day preview)
3. Frontend loads pre-computed model predictions, ELO ratings, and narrations at page load
4. Live results fetched from `/api/live` (server-side proxy to football-data.org)
5. Monte Carlo runs on client-side with current standings
6. Chat questions → `/api/chat` → topic filter → cache check → tournament context injection → RAG → DeepSeek streaming
7. Predictor narration: checks `narrations[home|away|dialect]` first; only calls `/api/narrator` if missing

### CostGuard & LLM Budget

**See `docs/finops.md` for current spend snapshot and cost projections.**

Budget controls are enforced at 3 levels:

1. **Global budget** — `configs/budget.yaml` declares daily ($2), monthly ($50), and per-run (5 calls) limits plus per-model token costs. `src/cost_guard.py:CostGuard.check_and_record()` raises `BudgetExceeded` before any call that would breach a limit.
2. **Component-level strategy** — Each feature (narrations, chat, agent debate) has explicit cost trade-offs:
   - **Narrations:** Pre-computed once daily (DeepSeek, 1 call/match × dialects). Zero LLM cost per user.
   - **Chat:** Topic filter → cache → rate limit (20 req/hour/IP) before calling LLM. Cached responses cost $0.
   - **Agent Debate:** Reserve for high-value matches only (~0.08–0.10 USD per match). Forward-only (no retroactive backfill of already-played matches).
3. **Observability** — All LLM calls logged to `logs/llm_costs.jsonl`. Pipeline runs appended to `logs/pipeline_runs.jsonl` with duration, status, metrics, and artifacts for post-match evaluation.

If budget is exceeded, deterministic predictions fall back to EnsembleModel (no LLM).

**Decision points before running an expensive operation:**
- Narrations run once/day per active dialect set — both group and knockout are `DIALECTS_* = ["bogotano"]` (~$0.01–0.02/match). Group stage started this way for flow stability; knockout was switched to it 2026-07-09 after briefly running all 5 dialects proved too costly for the pace of knockout matches.
- Agent Debate (~$0.08–0.10/match) and the Cazador de Sorpresas upset agent are the two calls worth thinking about before running in bulk — check `logs/llm_costs.jsonl` for the day's spend if debating many matches at once.
- Orchestrator enrichment (inside `predict_live.py`) is already budget-gated automatically; it degrades to delta=0 per agent rather than failing the run.

### AI Chat API (`/api/chat`)

Three cost-protection layers run in order before any API call:

1. **Topic filter** — keyword regex (Spanish/English/Portuguese football terms). Non-football questions get a canned reply at zero cost.
2. **Response cache** — module-level `Map<sha256, {response, ts}>`, TTL 2h, max 400 entries. Same question within a warm serverless instance returns instantly.
3. **Rate limit** — sliding window 20 requests/hour per IP. Returns HTTP 429 with `Retry-After: 3600` if exceeded.

RAG pipeline (when `DASHSCOPE_API_KEY` is set):
- Embeds query with Qwen3 `text-embedding-v3` (512 dims)
- Cosine similarity over `frontend/public/data/rag_index.json`
- Top-5 chunks injected into DeepSeek system prompt

Without `DASHSCOPE_API_KEY` or without `rag_index.json`, the chat falls back to DeepSeek's general knowledge. In all cases, **tournament context is injected directly** into the system prompt: today's fixtures (UTC date filter on `group_matches.json`) and group standings (`group_standings.json`). This ensures the chat always knows what's playing today and the current table — independent of RAG.

### Narrator Endpoint (`/api/narrator`)

Serves pre-computed narrations from `narrations.json`. Flow:
1. Checks `narrations[home|away|dialect]` key in the static JSON file
2. If found: returns the text immediately (zero LLM cost per user)
3. If missing (knockout match not yet pre-computed, or new dialect): calls DeepSeek to generate on-the-fly

The static file is regenerated daily by `scripts/precompute_narrations.py`. The Predictor component passes `narrations` prop down to `UnifiedNarration`, which has its own `localLang` state (per-match dialect selector, synced to global on mount but independently switchable). Dialect cost strategy: group stage → Bogotá/neutral Spanish only while the flow is stable; knockout → all 5 dialects auto-activated by stage field.

### Group Narrative Previews

`frontend/public/data/group_narratives.json` stores pre-computed narrative previews for the group tab and live tournament cards. Key format: `"GROUP|YYYY-MM-DD|bogotano"`, for example `"A|2026-06-18|bogotano"`.

Generation:
```bash
python scripts/precompute_narrations.py --groups-only --days 1
```

These previews use heavier DeepSeek reasoning than single-match blurbs because they must combine standings, prior results, local venue, model probabilities, and per-team pressure. They should never invent data: if a team has not played, the output must say there is no recent tournament evidence rather than classifying only by historical name.

`deepseek-reasoner` counts its thinking tokens against `max_tokens`; with a tight budget the reasoning phase can consume the whole allowance and the final `content` comes back as an **empty string with a 200 OK** (no exception raised). `_call_group_narrative()` uses `max_tokens=3200` and falls back to `deepseek-chat` (no reasoning phase, so it can't truncate itself) if the reasoner response is empty. The skip-check before generating (`if key in group_narratives`) also treats an empty stored string as "not generated yet" rather than "already done" — otherwise a single bad run permanently blocks that group/date key from ever being retried.

Frontend rendering:
- `frontend/src/components/GroupNarrativeCard.tsx` renders the Markdown-like output as styled sections, tables, team blocks, and narrator phrases.
- `frontend/src/components/LiveTournament.tsx` shows compact previews for the current day — `selectDailyGroupNarratives()` filters strictly to `entry.date === today` (not `>=`) with no result cap, so a group with no narrative generated for today doesn't get backfilled with a future-dated entry that dilutes/displaces the groups actually playing today.
- `frontend/src/components/Groups.tsx` shows the full group narrative.

Operational expectations:
- J1: preview focuses on baseline favorites, uncertainty, venue, and first-match risk.
- J2: preview must reflect current points, previous results, pressure to win/draw, and how evening matches change after afternoon results.
- J3: preview must emphasize simultaneous matches, goal difference, direct qualification, and best-third scenarios.
- The prompt requires per-team fields: points, previous result, previous opponent strength, result quality, mood, pressure, dependency, danger category, and narrative reading.

---

## Key Decisions & Patterns

### Temporal Split Over K-Fold
Time-series data (match history) requires temporal validation to prevent leakage. Test set is always Qatar 2022 (never in training), not random K-folds.

### Custom ELO vs FIFA Rankings
ELO is computed from all internationals chronologically. K varies by tournament importance (WC=60, friendly=20). A margin-of-victory multiplier `log(1+|GD|)` scales each update. Home advantage adds 100 ELO points to the expected score for non-neutral venues.

### Live Learning Strategy
The model doesn't do online learning — XGBoost is re-trained from scratch each update. What changes meaningfully with each WC 2026 matchday is the ELO ratings: a team that beats a stronger opponent gains ELO, which feeds into updated features for subsequent predictions. Run `python scripts/live_update.py` after each matchday.

### Live Prediction Mode (`scripts/predict_live.py`)

Separate from the full pipeline. Reads `data/external/wc2026_live_results.csv` (WC 2026 results only, distinct from `results.csv`) and the full historical dataset, then re-computes ELO + form with a strict cutoff `= kickoff - 60s`. The anti-leakage assertion aborts if `features_cutoff >= match_kickoff`. Outputs `data/processed/live_predictions.json`; with `--export` also writes to `frontend/public/data/live_predictions.json`.

To add a result manually: `python scripts/predict_live.py --add-result "Argentina" "France" 3 3 2026-07-19`

### CostGuard & Observability

- **`configs/budget.yaml`**: declares daily ($2), monthly ($50), and per-run (5 calls) LLM limits plus per-model token costs
- **`src/cost_guard.py`**: `CostGuard.check_and_record()` raises `BudgetExceeded` before any call that would breach a limit; the Orchestrator catches it and falls back to the deterministic Ensemble
- **`src/pipeline_logger.py`**: `run_context(run_type, artifacts)` context manager wraps every pipeline/live run and appends a JSONL entry to `logs/pipeline_runs.jsonl` with duration, status, metrics, and artifacts
- **`logs/llm_costs.jsonl`**: one entry per LLM call (model, tokens, cost, ts)
- **`logs/pipeline_runs.jsonl`**: one entry per pipeline run

### Multi-Agent Architecture (src/agents/)
The Orchestrator is the single API gateway. It routes each match to up to 5 sub-agents in group stage (2 in knockout) based on context. Each agent returns a `delta_P` (adjustment to the Ensemble prior). The Orchestrator blends deltas with per-agent weights × confidence, clamped to 12% max total shift, then renormalizes to sum=1.

**MatchIntel evidence layer (`src/agents/match_intel.py`) — IMPORTANT.** The agents used to be *starved*: `MatchContext` only carried ELO + group points, so IntMatch/Media guessed from team names and Roster skipped (no injury feed). `MatchIntel` now computes **rich, zero-cost signals from data already on disk** and injects them into `MatchContext` (12 new fields): recent form with scores + opponent quality tier (elite/strong/mid/weak by ELO), goal-scoring/conceding trends, momentum (hot/rising/falling/cold), head-to-head record, current-tournament results, goal-source concentration from `goalscorers.csv` (one-man dependency vs squad depth), and the **exact best-third math** (cross-group cutoff in points + GD). Built once per `predict_live.py` run and passed into `enrich_with_orchestrator`. This lifted agent confidence from ~0.2 to 0.5–0.9 in practice.

- **LLM agents**: IntMatch-Analytics-Pro (tactics from form/trends/H2H/goal-source), GroupScenario-Reasoner (classification pressure + third-place math, `deepseek-reasoner`), Roster-Data-Scout (**repurposed** to goal-source dependency + fatigue, since we have no injury feed), Media-Sentiment-Parser (morale derived from real results), Travel-Logistics-Quant (deterministic + LLM for altitude) — all route through `src/agents/specialists/_llm.py`
- **LLM provider**: DeepSeek (`DEEPSEEK_API_KEY`) is primary; Anthropic Claude (`ANTHROPIC_API_KEY`) is fallback. Claude model aliases in `_MODEL_MAP` are remapped to `deepseek-chat` automatically. **`_llm.py` retries `deepseek-reasoner` with `deepseek-chat` when reasoning truncation returns empty content (200 OK)** — this is what was making GroupScenario-Reasoner return all-zeros.
- **Deterministic agents** (no LLM): FinOps-Market-Calibration-Validator (odds math, inactive without odds), FIFA-Regs-Strategist (altitude/bracket/classification pressure), Travel-Logistics-Quant (haversine fallback)
- Agents fail gracefully (delta=0) when their required signal is missing (no injuries, no odds, no API key).
- **Design specs**: see `agent/*.md` files (one per specialist) for role, input context, output schema, and cost profile. Consult when modifying or adding a new specialist.

### Agent Debate System (src/agent_debate.py) — logic-based predictions, no ML

Separate from the ML ensemble and from the `src/agents/` Orchestrator above. Three expert personas debate a match in three rounds using **deepseek-reasoner** (extended thinking), reasoning purely from tournament logic — group standings, classification pressure, and MD1/MD2 momentum — never from the trained model's probabilities. Built because the Poisson/XGB ensemble was underpredicting goal variability (see "Poisson Overdispersion" note below) and the user wanted an alternative grounded in pressure/narrative logic rather than statistics.

- **Agents**: Group Analyst (classification pressure, points, GD, what each team needs to advance), Tactical Scout (styles/tactics modulated by that pressure), Sentiment Reader (morale derived from the real MD1/MD2 result, e.g. "WIN vs South Africa (2-0)" reads differently than a 1-0 squeaker).
- **3 rounds**: independent initial positions → each agent rebuts the other two → consensus round produces a ranked top-3 scoreline with classification impact ("¿quién avanza? ¿quién queda eliminado?").
- **Structured output (4 predictions per match)**: Each agent proposes an individual prediction, plus a consensus. The consensus prompt emits:
  ```json
  {"group_analyst": {...}, "tactical_scout": {...}, "sentiment_reader": {...}, "consensus": {...}}
  ```
  Parsed by `AgentDebateSystem.parse_predictions()` into all 4 predictions with agent attribution. The frontend evaluates **individual agent accuracy** vs. consensus. `max_tokens=4500` for the consensus call — deepseek-reasoner counts its thinking tokens against the budget.
- **Real context, not generic**: `get_group_context()` computes actual standings from `data/external/wc2026_live_results.csv` (not from the frontend's pre-tournament Monte Carlo `group_standings.json`), matched to groups via `data/external/wc2026_fixture.json`. Status is granular, not just points: `"Need to WIN to secure 1st (pressure)"` vs `"Can secure 1st with DRAW (comfortable)"` vs `"Critical (0 pts, must win or OUT)"` — a team with 3 points after MD1 is not automatically "comfortable" if a draw in MD2 would let a rival overtake it on goal difference.
- **Name normalization**: `TEAM_NAME_MAPPING` in `agent_debate.py` (`"USA" → "United States"`) bridges the fixture's naming with the live-results CSV's naming — both `get_group_context()` and the frontend's `lib/agentDebate.ts` `normalizeTeamName()` must stay in sync if more aliases are added.
- **Running it**: `python scripts/run_agent_debate.py "Home" "Away" ...` — accumulates into `data/processed/agent_debate_results.json` (does not overwrite), is idempotent (skips a pair that already has a non-error result unless `--force`), and deduplicates by team pair on every run (guards against the Windows console crashing mid-print on emoji output, which previously produced a spurious duplicate error entry alongside the real result).
- **Forward-only**: by design there is no retroactive backfill of already-played matches (cost/time tradeoff — 3 agents × 3 rounds × deepseek-reasoner per match). The "Modelo" tab's agent accuracy tables only reflect matches that were debated *before* being played.
- **Frontend wiring**: `frontend/src/app/api/agent-debate/route.ts` serves the exported static JSON (`frontend/public/data/agent_debate_results.json`, 60s in-memory cache — never calls DeepSeek per request). `frontend/src/components/AgentDebatePanel.tsx` renders it: `variant="compact"` is a collapsed `<details>` (just a "Ver consenso completo" arrow) used in `Predictor.tsx` (right after "Marcador más probable" / altitude badge) and in `LiveTournament.tsx`'s "Próximos" tab (under each fixture's forecast badge); it returns `null` silently when no debate exists for that match, so the upcoming-matches list isn't cluttered with "not available" placeholders. `frontend/src/lib/agentDebate.ts` mirrors `lib/live.ts`'s `modelVerdict`/`orientScore` pattern (`agentVerdict`, `computeAgentResults`) so `ModelTab.tsx` can show the same per-matchday/per-group accuracy breakdown for agents side-by-side with the ML model's.

### Pre-computed Narrations (Zero LLM Cost Per User)
`narrations.json` is built once per day by `scripts/precompute_narrations.py` (DeepSeek, 1 call per match × dialects). Key format: `"home|away|dialect"`. The frontend loads the full JSON at page load and passes it as a prop to `Predictor → UnifiedNarration`. The narrator endpoint serves static keys and only falls back to a live LLM call when a key is missing (e.g., knockout matches before their narration is generated). Both `DIALECTS_GROUP` and `DIALECTS_KNOCKOUT` are currently `["bogotano"]` — group stage started this way for flow stability; knockout briefly ran all 5 dialects (`bogotano`, `paisa`, `boyaco`, `costeño`, `en`) via a `match.stage != "group"` branch before being restricted to bogotano-only on 2026-07-09 (too many matches in quick succession for 5x cost/time per match to be worth it).

**Important — the match-selection filter had a real bug until 2026-07-09:** the code that builds the candidate list for the date-window check filtered `live_preds` to `stage == "group"` only. Once the group stage ended, `live_predictions.json` stopped containing any `stage: "group"` entries at all (only `stage: "knockout"`), so every run silently reported "0 partidos a narrar" — even with matches correctly inside the `--days` window — despite the downstream dialect-selection logic already branching correctly on `is_group`. Fixed by removing the stage filter from the candidate list (dialect selection still branches per-match on `is_group`).

### Isotonic Calibration
Probabilities matter more than accuracy in a tournament simulator. Isotonic calibration ensures the model's predicted probabilities match observed win rates.

### Client-Side Simulation
1,128 pre-calculated team-pair matchups are embedded in frontend. Monte Carlo runs client-side (no server load) for instant projections and exploration.

### Temporal Split in Tests
Tests use the same temporal strategy: fixture data with year=2014/2018/2022 to verify no leakage occurs between train and test sets.

---

## File Structure Summary

```
├── src/
│   ├── extractor.py        # Data loading + team name normalization
│   ├── features.py         # ELO (K by tournament + margin mult + home adv), H2H, form, weights
│   ├── model.py            # XGBoost + TimeSeriesSplit calibration, RPS metric
│   ├── poisson_model.py    # Bivariate Poisson: attack/defense strengths, scoreline matrix
│   ├── ensemble.py         # EnsembleModel: ELO + Poisson + XGB blend
│   ├── pipeline_logger.py  # JSONL run ledger → logs/pipeline_runs.jsonl
│   ├── cost_guard.py       # CostGuard: reads budget.yaml, enforces LLM spend limits
│   ├── simulator.py        # Tournament simulation (official 2026 bracket, host advantage)
│   ├── app.py              # Streamlit demo interface
│   ├── agent_debate.py     # Agent Debate System: 3-round logic-based debate (deepseek-reasoner)
│   ├── bracket.py          # Resolves knockout fixture placeholders (1A/2B/3X/W##) from live results
│   ├── upset_agent.py      # Cazador de Sorpresas: 4th independent agent, always argues the underdog
│   └── agents/
│       ├── base.py         # MatchContext (+ MatchIntel fields), AgentResult, BaseAgent ABC
│       ├── match_intel.py  # Free derived evidence: form, H2H, goal trends, scorers, third-place math
│       ├── orchestrator.py # Routing (up to 5 in group stage), delta blending, OrchestratorOutput
│       └── specialists/
│           ├── intmatch.py        # Tactics from form/trends/H2H/goal-source
│           ├── group_scenario.py  # Classification pressure + third-place math (deepseek-reasoner)
│           ├── roster.py          # Goal-source dependency + fatigue (repurposed; no injury feed)
│           ├── media.py           # Morale derived from real results
│           ├── travel.py          # Fatigue/altitude (deterministic + LLM)
│           ├── finops.py          # Odds implied probs (deterministic, inactive without odds)
│           ├── fifa_regs.py       # Bracket/altitude/classification math (deterministic)
│           └── _llm.py            # LLM gateway: DeepSeek→Claude, reasoner-empty fallback
├── agent/                  # Agent design specs (one .md per specialist, PascalCase-hyphenated names)
│   ├── orchestrator.md
│   ├── IntMatch-Analytics-Pro.md
│   ├── Roster-Data-Scout.md
│   ├── Media-Sentiment-Parser.md
│   ├── Travel-Logistics-Quant.md
│   ├── FinOps-Market-Calibration-Validator.md
│   └── FIFA-Regs-Strategist.md
│   # (GroupScenario-Reasoner has no spec file yet — see src/agents/specialists/group_scenario.py)
├── contracts/              # Formal data + feature schemas (prevent silent failures)
│   ├── data_contracts.md   # Bronze/silver/gold schemas for CSVs, parquets, JSONs
│   ├── module_contracts.md # Feature + model input/output contracts (incl. DEFAULT_WEIGHTS)
│   ├── core_model_contracts.md      # Must-have deterministic core (ELO/Poisson/XGB/Ensemble/Simulator)
│   └── agent_enrichment_contracts.md # Optional LLM agent layer (never required, degrades to delta=0)
├── configs/
│   └── budget.yaml         # LLM cost limits (daily/monthly/per-run) + token costs
├── scripts/
│   ├── run_pipeline.py             # Execute full pipeline
│   ├── export_frontend_data.py     # Generate JSONs for frontend
│   ├── live_update.py              # Orchestrator: fetch results → retrain → export
│   ├── update_wc_results.py        # Fill NA scores in results.csv from football-data.org
│   ├── predict_live.py             # Live predictions with per-match ELO cutoff (anti-leakage) + MatchIntel agents
│   ├── update_third_place_probs.py # Recompute ONLY third-place probs (Monte Carlo ~5s, no narrations) — J3 3x/day
│   ├── precompute_narrations.py    # Daily narrations × dialects → narrations.json (DeepSeek, 1 call/match)
│   ├── run_agent_debate.py         # Runs Agent Debate System for given matches → agent_debate_results.json (accumulative, idempotent)
│   ├── export_knockout_bracket.py  # Publishes resolved knockout bracket → knockout_bracket.json (R32 + feeders)
│   ├── run_upset_agent.py          # Runs Cazador de Sorpresas for knockout crosses → upset_predictions.json
│   ├── ablation_features.py        # Ablation test for candidate features vs base FEATURE_COLS
│   ├── calibrate_ensemble_2026.py  # Recalibrate ensemble weights via mini walk-forward over played WC 2026 matches (--apply writes ensemble.py)
│   ├── ci_debate_targets.py        # Print upcoming group-stage Home/Away pairs within DEBATE_WINDOW_HOURS (CI agent-debate automation; empty = skip)
│   ├── walk_forward_validation.py  # Walk-forward RPS vs ELO baseline
│   ├── build_rag_index.py          # Generate embedding index for chat RAG
│   ├── inspect_rounds.py           # Debug utility: inspect simulator round-by-round probabilities
│   └── enrich_goalscorers.py       # Optional: goalscorer enrichment
├── frontend/               # Next.js 15 + React 19
│   ├── src/app/
│   │   ├── page.tsx        # Main tabbed interface; loads narrations.json and passes as prop
│   │   ├── api/live/       # Proxy to football-data.org
│   │   ├── api/chat/       # AI chat: tournament context injection + topic filter + cache + RAG + DeepSeek
│   │   ├── api/narrator/   # Serves narrations.json; LLM fallback for missing keys only
│   │   ├── api/agent-debate/ # Serves agent_debate_results.json (60s in-memory cache, no live LLM calls)
│   │   └── api/og/         # route.tsx — dynamic Open Graph social-share image (@vercel/og ImageResponse)
│   ├── src/components/
│   │   ├── Predictor.tsx   # Match predictor + UnifiedNarration (localLang + dialect selector) + AgentDebatePanel
│   │   ├── ModelTab.tsx    # Live model accuracy: KPIs, per-matchday bars, per-group J1/J2/J3/FG (ML + Agents side-by-side), surprises
│   │   ├── AgentDebatePanel.tsx # Collapsed-by-default consensus panel (compact: Predictor/Próximos; full: detailed)
│   │   ├── StatsTab.tsx    # WC 2026 stats dashboard: goals, top teams, top matches, score dist, upsets
│   │   ├── KnockoutBracket.tsx # Resolved bracket renderer (Eliminatorias/Octavos tabs) from knockout_bracket.json
│   │   └── ...             # Groups, Simulator, ChatTab, etc.
│   ├── src/lib/
│   │   ├── simulator.ts    # Client-side Monte Carlo
│   │   ├── live.ts         # Live results fetching + orientScore + modelVerdict
│   │   ├── agentDebate.ts  # Agent Debate verdict/accuracy helpers (mirrors live.ts for the ML model)
│   │   └── i18n.tsx        # i18n context + regional dialects
│   └── public/data/        # Exported JSONs: teams, predictions, narrations, group_matches, standings, knockout_bracket, upset_predictions, etc.
├── tests/                  # 157 tests: features, model, agents, cost guard, bracket resolution, integrity, simulator, live prediction
├── data/
│   ├── raw/                # results.csv (incl. WC 2026 fixture), shootouts.csv, goalscorers.csv
│   ├── processed/          # Generated CSVs, parquets, JSONs (regenerable, gitignored)
│   └── external/           # wc2026_fixture.json (group + knockout placeholders); wc2026_knockout_fixture.json (cached real R32 bracket from football-data.org, authoritative for best-third assignment); wc2026_live_results.csv (played WC 2026 only)
├── models/                 # Serialized models (gitignored, regenerable)
├── logs/                   # pipeline_runs.jsonl, llm_costs.jsonl (gitignored)
├── notebooks/              # EDA and analysis
├── instrucciones.md        # Daily ops: MD1/MD2/MD3 cycles, double-run protocol, cost table
├── instrucciones2.md       # J3 CI windows / simultaneous-match protocol detail
├── instructivo-github-actions.md # One-time GitHub Actions secrets setup
├── proyecto.md             # Project definition, deliverables (E1–E5), and status
├── model_card.md           # Model performance, walk-forward results, feature ablation
├── methodology.md          # Model methodology, limitations, responsible-use statement
├── guia.md                 # Technical roadmap (Phases 0–6), design decisions (D1–D6)
├── retrospective.md        # Post-tournament template (blank until after Jul 19 final)
├── QUICK_START.md          # 2-min external-facing summary for evaluators
├── AGENTS.md               # Codex equivalent of this file — keep in sync
├── requirements.txt        # Python dependencies
└── README.md
```

---

## Common Workflows

### Updating Model After a WC 2026 Matchday

```bash
# 1. Fetch new results, retrain, export JSONs (~90s; skips if no new matches)
python scripts/live_update.py

# 2. Recalculate live predictions with multi-agent enrichment
python scripts/predict_live.py --export

# 3. Pre-compute match narrations + group previews for today's context
python scripts/precompute_narrations.py

# Optional: group previews only, after prompt/context changes or MD2 afternoon results
python scripts/precompute_narrations.py --groups-only --days 1

# Optional: agent debate for specific upcoming matches (forward-only, no backfill)
python scripts/run_agent_debate.py "Mexico" "South Korea"
python scripts/export_frontend_data.py

# 4. Deploy
cd frontend && npx vercel --prod
```

**MD2 double-run protocol** (Jun 18–23, 4 matches/day split afternoon/evening): run the full cycle once in the morning before any match, then run steps 1–4 again in the afternoon after the first 2 results are in. This ensures evening match predictions and group previews reflect qualification pressure from the afternoon results. See `instrucciones.md` for the full MD2/MD3 calendar and cost table.

**MD3 simultaneous protocol:** group matches kick off at the same hour, so standings must be interpreted as scenario probabilities rather than sequential results. Group previews should emphasize direct qualification, goal difference, and best-third pressure.

### Live Predictions Without Full Retrain (between matchdays)

```bash
# Predict pending matches using current model + live ELO cutoff per match
python scripts/predict_live.py --export

# Add a result manually and re-predict
python scripts/predict_live.py --add-result "Mexico" "Poland" 0 0 2026-06-14
python scripts/predict_live.py --export
```

### Training a New Model

1. `python scripts/run_pipeline.py` — Regenerates features and trains all models
2. Check metrics output (accuracy, log-loss, Brier score, calibration error)
3. Verify test set is Qatar 2022 (temporal split, no leakage)

### Debugging Model Predictions

- Check `src/model.py`: FEATURE_COLS, LABEL_MAP
- Review feature values in `data/processed/features.parquet`
- Use Streamlit app (`streamlit run src/app.py`) to inspect predictions
- Compare baseline (LogisticRegression) vs XGBoost to isolate non-linear improvements

### Building the RAG Index (requires DashScope key)

```bash
# Set key in frontend/.env.local: DASHSCOPE_API_KEY=<key>
python scripts/build_rag_index.py
# → generates frontend/public/data/rag_index.json
# Chat API uses it automatically on next deploy
```

### Extending Frontend

- Add new component in `src/components/`
- Use `useI18n()` hook for multi-language support
- Client-side simulator in `lib/simulator.ts` handles Monte Carlo; no backend call needed
- Live results in `lib/live.ts` cache via `/api/live` (server-side proxy to football-data.org)

---

## Testing Strategy

- **Temporal split validation:** Ensure train < test_year
- **Feature presence:** All FEATURE_COLS present in feature matrix
- **Calibration checks:** Brier score and log-loss on test set
- **Simulator:** Deterministic seed (random_state=42) for reproducibility
- **No mock DB:** Integration tests run against real data files (CSV, JSON, PKL)
- **Data contracts:** Every pipeline run validates input/output schemas (see `contracts/data_contracts.md`). Silent data quality failures are unacceptable — all assertions are explicit.

---

## Environment & Secrets

All secrets via env vars only — never in code.

| Variable | Where | Purpose |
|---|---|---|
| `FOOTBALL_DATA_TOKEN` | `frontend/.env.local` + Vercel | Live match data from football-data.org |
| `DEEPSEEK_API_KEY` | `frontend/.env.local` + Vercel + `.env` | AI chat (frontend) + primary LLM for Python agents |
| `DASHSCOPE_API_KEY` | `frontend/.env.local` + Vercel | Query embeddings for RAG (Qwen3 text-embedding-v3) |
| `ANTHROPIC_API_KEY` | `.env` + `frontend/.env.local` + Vercel | Fallback LLM for Python agents + frontend narrator when DeepSeek unavailable |

`update_wc_results.py` auto-loads `FOOTBALL_DATA_TOKEN` from `frontend/.env.local` if not set in the environment — no need to export it manually when running locally.

---

## Performance Notes

- **ELO calculation:** O(n) chronological pass over all matches (~49k rows)
- **Feature matrix:** Pandas vectorized operations, no loops
- **XGBoost training:** ~900 samples (World Cup matches only in test), ~1s training time
- **Full live_update.py cycle:** ~90 seconds (dominated by pipeline + export)
- **Frontend simulator:** 5,000 Monte Carlo iterations in browser (~200ms on modern hardware)
- **Chat cache hit rate:** ~70-80% for warm serverless instances (module-level Map, SHA-256 key, TTL 2h)
- **Chat rate limit:** 20 requests/hour/IP — prevents abuse without Redis
