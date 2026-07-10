# Mundial Predictor 2026 - Live Runbook

## Daily Cycle

Run after match results are available and before publishing updated views.

```bash
python scripts/live_update.py
python scripts/predict_live.py --export
python scripts/precompute_narrations.py
cd frontend
npx vercel --prod
```

## What Each Step Does

| Step | Purpose |
|---|---|
| `live_update.py` | Fetches or applies real scores, retrains when needed and exports frontend data. |
| `predict_live.py --export` | Recalculates match predictions with live ELO cutoff and writes frontend JSON. |
| `precompute_narrations.py` | Refreshes match and group narrations from current standings/fixtures. |
| `npx vercel --prod` | Publishes the frontend with updated static artifacts. |

## J2 Protocol

J2 has two competitive moments in the same day. When there are early and late blocks:

1. Run the full cycle before the first matches.
2. After the first block finishes, update scores.
3. Re-run predictions and narrations for the later block.
4. Deploy again.

Reason: the late matches must understand new pressure, points, goal difference and qualification paths.

## J3 Protocol

J3 is different because matches inside the same group are simultaneous.

Rules for narration and agents:
- Do not assume a team knows the live result from the other simultaneous match unless live minute data is explicitly available.
- Focus on scenarios: direct qualification, goal difference, second place and best third-place qualification.
- Avoid saying a team is mathematically qualified unless the standings prove it.

## Knockout Cycle (Jun 28 – Jul 19)

Same daily cycle as above, plus three extra steps after `predict_live.py --export`:

```bash
python scripts/export_knockout_bracket.py     # resolves bracket -> knockout_bracket.json
python scripts/run_upset_agent.py             # Cazador de Sorpresas -> upset_predictions.json
python scripts/export_frontend_data.py        # publishes agent debate + upset results
```

**Result fetching may need multiple passes.** `update_wc_results.py` only appends a knockout cross to `results.csv` once its feeder round is already filled (R32 unlocks R16, R16 unlocks QF, etc.). Catching up after any gap longer than one round requires running it repeatedly until it reports "Sin cambios — todos los partidos ya están al día." A single `live_update.py` run only does one pass internally and will not converge on its own after a multi-round gap.

## CI Automation

`.github/workflows/wc2026-live-update.yml` runs the cycle automatically on a schedule. **Lesson learned 2026-07-09:** the original schedule was hand-crafted, one cron line per exact group-stage kickoff (Jun 11–28), and nobody added entries for the knockout phase — the pipeline silently did not run once for 11+ days through R32/R16/QF1 before this was caught. It's now a periodic bounded schedule (`0 */2 1-21 7 *`, every 2h through Jul 21) instead of per-kickoff lines, specifically so it can't expire silently again.

**Don't trust the schedule blindly — verify it's actually firing:**
```bash
gh run list --workflow=wc2026-live-update.yml --limit 5
```
If the most recent run is more than a few hours old during an active tournament window, the pipeline has stalled — check `data/external/wc2026_live_results.csv`'s most recent date against the real calendar before assuming the frontend is current.

## Verification Checklist

Before deploy:

- Today's fixtures match the real calendar in Colombia/Bogotá time.
- `group_standings.json` reflects played matches (group stage) or `knockout_bracket.json` reflects the current round (knockout).
- `live_predictions.json` exists and has updated timestamps or changed probabilities.
- `group_narratives.json` does not contain mojibake.
- Chat answers do not invent matches for today.
- Model tab separates ML metrics from agent metrics, and (knockout) shows a per-round phase breakdown, not just JOR 1/2/3.
- Agent Debate accuracy is forward-only: matches played without a prior debate (e.g. during a CI gap) will permanently show no agent data for that round — this is expected, not a bug to chase.

## Emergency Fallback

If LLM APIs fail:

1. Run `predict_live.py --export` without agent enrichment if supported.
2. Keep deterministic predictions visible.
3. Hide or label missing narrative blocks instead of generating stale explanations.
4. Deploy the deterministic state.
