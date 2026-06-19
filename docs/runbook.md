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

## Verification Checklist

Before deploy:

- Today's fixtures match the real calendar in Colombia/Bogotá time.
- `group_standings.json` reflects played matches.
- `live_predictions.json` exists and has updated timestamps or changed probabilities.
- `group_narratives.json` does not contain mojibake.
- Chat answers do not invent matches for today.
- Model tab separates ML metrics from agent metrics.

## Emergency Fallback

If LLM APIs fail:

1. Run `predict_live.py --export` without agent enrichment if supported.
2. Keep deterministic predictions visible.
3. Hide or label missing narrative blocks instead of generating stale explanations.
4. Deploy the deterministic state.
