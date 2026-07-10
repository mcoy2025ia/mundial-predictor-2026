# Retrospective — Mundial Predictor 2026

**Tournament:** FIFA World Cup 2026 (June 11 – July 19, 2026)
**Status:** Pre-filled 2026-07-10 with everything known through QF1 (97 of 104 matches played). Sections marked _pending final_ get completed after July 19.

---

## 1. Model Baseline

| Model | Walk-Forward RPS | WC 2026 RPS (97 matches)¹ |
|---|---|---|
| ELO baseline | 0.1966 | 0.1691 |
| Poisson-only | — | 0.1767 |
| XGBoost calibrated | 0.2167 | 0.1691 |
| **Ensemble 22/58/20** | **0.1958**² | **0.1665** |

> **Primary metric:** RPS (lower = better). Benchmark: naive 1/3 uniform = 0.222.
> ¹ From `calibrate_ensemble_2026.py` run 2026-07-09 over all played WC 2026 matches. The grid search found a marginal potential improvement (+0.0027) below its own significance threshold, so weights stayed at 22/58/20.
> ² Walk-forward number predates the 2026-06-17 recalibration from 35/35/30 to 22/58/20.

---

## 2. WC 2026 Results vs Predictions

Computed 2026-07-10 from the published prediction JSONs vs official results.³

| Round | N | Ensemble correct (1X2) | RPS |
|---|---|---|---|
| Group JOR 1 | 24 | 11 (46%) | 0.1706 |
| Group JOR 2 | 24 | 19 (79%) | 0.1336 |
| Group JOR 3 | 24 | 16 (67%) | 0.1349 |
| Round of 32 | 16 | 14 (88%) | 0.1474 |
| Round of 16 | 8 | 7 (88%) | 0.1753 |
| Quarter-finals | 4 | 1/1 _(3 pending)_ | 0.1233 |
| Semi-finals | 2 | _pending final_ | _pending final_ |
| Third place + Final | 2 | _pending final_ | _pending final_ |
| **Total played so far** | **97** | **68 (70%)** | **0.1487** |

> ³ Group-stage probabilities are the latest published export (they regenerate with each retrain, not frozen pre-match snapshots). Knockout probabilities are cutoff-clean retro predictions: ELO/form cut at kickoff−60s, Poisson refit per match-date (see §5). JOR 1's 46% was the model's worst stretch — cold-start with zero tournament evidence; accuracy jumped ~30pp once real 2026 results fed the ELO.

---

## 3. Champion Probability at Tournament Start

_pending final._ The pre-tournament champion distribution was computed client-side (Monte Carlo in browser) and not persisted as a JSON artifact. To reconstruct: check out the first tournament commit and run `src/simulator.py` with the pre-tournament model, or read it off the earliest deployed Proyecciones tab snapshot.

---

## 4. What Worked

- [x] Ensemble (ELO + Poisson + XGB) beat pure ELO (0.1665 vs 0.1691 through QF1)
- [x] Temporal calibration (no leakage, no random K-fold)
- [x] Tournament weights in training (WC=1.0, friendly=0.20)
- [x] Host advantage detection (USA/Mexico/Canada is_neutral=0)
- [x] Live update pipeline (predict_live.py) — anti-leakage cutoff design paid off repeatedly (§5)
- [x] Knockout bracket resolution (`src/bracket.py`) — placeholders (1A/2B/3X/W##) resolved progressively from real results; API cache as authority for best-third slot assignment
- [x] Temporal-cutoff backfill (`run_agent_debate.py --cutoff`) — made honest retroactive agent evaluation possible after the CI outage
- [x] MatchIntel evidence layer — lifted agent confidence from ~0.2 to 0.5–0.9 by feeding real derived signals instead of team names

---

## 5. What Didn't Work / Surprises

**Operational:**
- **The 11-day CI blackout (Jun 28 – Jul 9).** The workflow's cron schedule was hand-crafted, one line per group-stage kickoff, and nobody added knockout entries — the pipeline silently never ran during R32/R16/QF1. Root lesson: *never* enumerate per-event cron lines for a bounded window; use a periodic schedule (`0 */2 1-21 7 *`) where over-triggering is a cheap no-op. Discovered because the Eliminatorias tab showed matches "POR JUGAR" that had been played days earlier.
- **Narration filter bug:** `precompute_narrations.py` filtered candidates to `stage == "group"`, so once groups ended every run reported "0 partidos a narrar" — silently. Same class of bug as the cron: code that expires when the tournament advances.
- **CI debate automation was group-only:** `ci_debate_targets.py` had the same `stage == "group"` filter; knockout matches would never have been auto-debated.
- **Multi-pass fetch requirement:** `update_wc_results.py` only unlocks each knockout round once its feeder round is filled — catching up after a multi-round gap took 4 sequential passes.

**Leakage found and fixed:**
- **Agent Debate context leaked results for already-played matches** — the France-Morocco QF debate "predicted" the exact 2-0 it could see in its own context. Fixed with `--cutoff` (context filtered to dates strictly before the match); leaked entry replaced with a clean re-run (1-0 — winner right, score honest).
- **Poisson retro leakage:** the global pkl is fitted on all played matches, so retroactive predictions carried each match's own goals inside the attack/defense strengths (58% of ensemble weight). Fixed 2026-07-09: `fit_poisson_before_date()` refits per match-date (n_iter=30 ≈ 22s, <0.6pp drift vs full fit). Shifts were sub-1pp — small, but the claim "cutoff-clean" is now actually true.

**Football:**
- JOR 1 cold-start: 46% accuracy, the model's floor for the tournament.
- R16 was upset city and the agents (backfilled blind) went 3/8 on consensus: Norway 2-1 Brazil, Belgium 4-1 USA, Morocco 3-0 Canada, England 3-2 México, Switzerland 4-3 Colombia — the model itself still hit 7/8 that round (it had Norway as favorite vs Ivory Coast, etc.).
- Paraguay eliminated Germany in R32's wildest scoreline.

---

## 6. Feature Ablation Post-Tournament

| Feature | Was it worth adding? | Evidence |
|---|---|---|
| `days_since_last_match` | Rejected pre-tournament (gate +0.0005) | _reassess with 2026 data after final_ |
| FIFA ranking integration | Not built (Etapa C backlog) | _pending final_ |
| Weather/altitude (FIFA-Regs agent) | Built, rarely triggered | Deterministic agent; fired mainly for Mexico City venue matches. No measured RPS contribution. |

---

## 7. Operational Notes

- **Automation:** GitHub Actions (`wc2026-live-update.yml`) — full cycle fetch → retrain → predict → bracket → upset agent → narrations → debates → commit → Vercel deploy. Ran reliably through groups, died silently for knockout (see §5), fixed + extended 2026-07-09/10 and validated end-to-end with a manual dispatch.
- **LLM spend:** local `llm_costs.jsonl` shows 2,328 calls / ~$0.49, but CI runs log to ephemeral runners, so the real total is higher — budget ceiling was $50/month and actual spend stayed far below it. Biggest single-day spend: 2026-07-09 catch-up (8 R16 backfill debates + 3 QF debates + France-Morocco redo + upset agent + narrations ≈ $1.20–1.50).
- **Pipeline runs:** 63 local runs logged, 0 errors. CI runs additional (see Actions history; 5 scheduled runs failed Jun 26–27 during J3, then the Jun 28+ silence).
- **Deploy platform:** Vercel (`mundial-predictor` project). Static pre-computed JSON + serverless API routes; zero per-user LLM calls for cached content.

---

## 8. Next Tournament (Euros 2028 / WC 2030) Backlog

- [ ] FIFA ranking features (ablate with 2026 data first)
- [x] Automated live result ingestion (football-data.org + GitHub Actions) — **but** use periodic cron from day one, never per-kickoff lines
- [ ] Injury data pipeline (Roster agent as real feature, not just LLM)
- [ ] Scoreline predictions exposed in frontend (Poisson top-5 already computed)
- [ ] Walk-forward including WC 2026 in folds
- [ ] Grep for `stage == "group"`-style filters before knockout starts — three separate bugs in one tournament came from code that silently expired when the phase changed
- [ ] Persist the pre-tournament champion distribution as a JSON artifact (couldn't fill §3 because it only ever lived client-side)
- [ ] Poisson per-date refit and `--cutoff` debate backfill are now built-in — retroactive evaluation after any future outage is a solved problem

---

_Template created 2026-06-13. Pre-filled 2026-07-10 through QF1; finish after July 19._
