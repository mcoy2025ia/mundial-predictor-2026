# Agent Name: FinOps-Market-Calibration-Validator

> **IMPORTANT:** This agent does NOT recommend bets or capital allocation.  
> It only detects if market implied probabilities diverge from our Ensemble model.

---

## Role: Market Probability Validator & Overround Detection

**Purpose:** Compare bookmaker odds with the Ensemble prior. Detect market consensus divergence.

**NOT a betting tool.** This is a CALIBRATION CHECK.

---

## Core Variables & Methodology

### A. Overround Calculation

The bookmaker's margin (overround) inflates probabilities artificially:

```
raw_implied = [1/O_home, 1/O_draw, 1/O_away]  (inverse odds)
overround = sum(raw_implied)                  (>1.0 if margin > 0)
clean_implied = raw_implied / overround       (removes margin)
```

**Why it matters:** Market odds embed a margin. We remove it to get true market consensus.

### B. Edge Detection

Compare clean market probabilities to our model prior:

```
edge_home = clean_implied_home - p_ensemble_home
edge_draw = clean_implied_draw - p_ensemble_draw
edge_away = clean_implied_away - p_ensemble_away

max_edge = max(|edge_home|, |edge_draw|, |edge_away|)
```

**Interpretation:**
- max_edge > 0.05: Market consensus diverges meaningfully from model
- max_edge < 0.05: Market is aligned with model (no signal)

### C. Confidence Scaling

Confidence is proportional to edge magnitude (with conservative Kelly Criterion scaling):

```
kelly_fraction = max_edge / p_model_at_max_edge
kelly_conservative = min(kelly_fraction × 0.25, 0.50)  (never >50% of capital)
confidence = round(kelly_conservative, 2)
```

**Interpretation:** High edge → high confidence that market differs from model.

---

## Output Directive

Return a JSON with:
```json
{
  "delta_home": float,      // adjustment to P(home win), ∈ [-0.15, +0.15]
  "delta_draw": float,      // adjustment to P(draw), ∈ [-0.15, +0.15]
  "delta_away": float,      // adjustment to P(away win), ∈ [-0.15, +0.15]
  "confidence": float,      // [0.0, 1.0] — how much to trust this adjustment
  "notes": string          // Market calibration findings (max 2 sentences)
}
```

**Constraints:**
1. Deltas must sum to 0 (redistribution, not creation)
2. Max total shift: ±15% (clamped by Orchestrator to ±12%)
3. No betting recommendations; only calibration signal
4. If no odds provided: return delta=0

---

## Example Walkthrough

**Input:**
```json
{
  "team_home": "Argentina",
  "team_away": "Mexico",
  "p_home": 0.65,
  "p_draw": 0.20,
  "p_away": 0.15,
  "home_odds": 1.50,
  "draw_odds": 3.50,
  "away_odds": 5.50
}
```

**Computation:**
```
raw_implied = [1/1.50, 1/3.50, 1/5.50] = [0.6667, 0.2857, 0.1818]
overround = 0.6667 + 0.2857 + 0.1818 = 1.1342 (13.42% margin)
clean_implied = [0.588, 0.252, 0.160]

edges = [0.588 - 0.65, 0.252 - 0.20, 0.160 - 0.15]
      = [-0.062, +0.052, +0.010]

max_edge = 0.062 (home win is OVERPRICED relative to model)
```

**Output:**
```json
{
  "delta_home": -0.075,
  "delta_draw": +0.040,
  "delta_away": +0.035,
  "confidence": 0.32,
  "notes": "Market overprices Argentina home win (-6.2%); modest price drift."
}
```

**Interpretation:** Our Ensemble thinks Argentina's win is less likely than market implies. Market consensus diverges by 6%, suggesting possible value.

---

## Limitation & Responsible Use

**This is a CALIBRATION CHECK, not a betting recommendation.**

- ❌ DO NOT interpret as: "Buy Argentina if edge > 5%"
- ✅ DO interpret as: "Market consensus differs from model by this magnitude"

Market edges could reflect:
1. **Model limitation:** Our model missed something (injuries, momentum, etc.)
2. **Wisdom of crowds:** Betting market aggregates real-time human judgment
3. **Arbitrage:** Professional traders moved odds based on non-public information

We don't know which. The agent reports the divergence; humans must interpret.

---

## Implementation Notes

- **Deterministic agent:** No LLM call, no API key needed
- **Always available:** Runs even if budget exhausted (never incurs cost)
- **Graceful missing data:** If odds not provided, returns delta=0
- **Renormalization:** Orchestrator clamps and renormalizes final probs

---

**Status:** Deterministic calibration check (no betting recommendations)  
**Cost:** $0 (deterministic)  
**Risk:** Low (conservative output; impact on predictions capped at ±12%)
