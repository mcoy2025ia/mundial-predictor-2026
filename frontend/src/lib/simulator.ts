import type { FixedResults, SimResult, TeamInfo } from "@/types";
import { pairKey } from "@/lib/live";

type Probs = { home_win: number; draw: number; away_win: number };
type PredictionsMap = Record<string, Probs>;
type Groups = Record<string, string[]>;
type PenRates = Record<string, number>;

function getProbs(predictions: PredictionsMap, t1: string, t2: string): Probs {
  return (
    predictions[`${t1}|${t2}`] ??
    (predictions[`${t2}|${t1}`]
      ? {
          home_win: predictions[`${t2}|${t1}`].away_win,
          draw: predictions[`${t2}|${t1}`].draw,
          away_win: predictions[`${t2}|${t1}`].home_win,
        }
      : { home_win: 0.34, draw: 0.32, away_win: 0.34 })
  );
}

function sampleOutcome(p: Probs): "home" | "draw" | "away" {
  const r = Math.random();
  if (r < p.home_win) return "home";
  if (r < p.home_win + p.draw) return "draw";
  return "away";
}

/**
 * Win rate histórico en tandas de penales, suavizado hacia 0.5
 * (Laplace: +2 victorias / +4 tandas). Equipos sin historial → 0.5.
 */
export function buildPenRates(teams: Record<string, TeamInfo>): PenRates {
  const rates: PenRates = {};
  for (const [name, t] of Object.entries(teams)) {
    rates[name] = ((t.pen_wins ?? 0) + 2) / ((t.pen_total ?? 0) + 4);
  }
  return rates;
}

/** Empate en knockout → penales ponderados por historial (Bradley-Terry). */
function sampleKnockout(p: Probs, t1: string, t2: string, pens?: PenRates): string {
  const o = sampleOutcome(p);
  if (o === "draw") {
    const r1 = pens?.[t1] ?? 0.5;
    const r2 = pens?.[t2] ?? 0.5;
    return Math.random() < r1 / (r1 + r2) ? t1 : t2;
  }
  return o === "home" ? t1 : t2;
}

function simulateGroup(
  teams: string[],
  predictions: PredictionsMap,
  elos: Record<string, number>,
  fixed?: FixedResults
): { standings: string[]; points: Record<string, number> } {
  const pts: Record<string, number> = Object.fromEntries(teams.map((t) => [t, 0]));
  for (let i = 0; i < teams.length; i++) {
    for (let j = i + 1; j < teams.length; j++) {
      const t1 = teams[i], t2 = teams[j];
      // partido ya jugado en el torneo real → resultado fijo, no se simula
      const key = pairKey(t1, t2);
      if (fixed?.has(key)) {
        const winner = fixed.get(key);
        if (winner === null) { pts[t1]++; pts[t2]++; }
        else if (winner !== undefined) pts[winner] += 3;
        continue;
      }
      const p = getProbs(predictions, t1, t2);
      const o = sampleOutcome(p);
      if (o === "home") pts[t1] += 3;
      else if (o === "draw") { pts[t1]++; pts[t2]++; }
      else pts[t2] += 3;
    }
  }
  const standings = [...teams].sort(
    (a, b) => pts[b] - pts[a] || (elos[b] ?? 1500) - (elos[a] ?? 1500)
  );
  return { standings, points: pts };
}

export function runMonteCarlo(
  predictions: PredictionsMap,
  groups: Groups,
  teams: Record<string, TeamInfo>,
  n = 1000,
  fixedResults?: FixedResults
): SimResult[] {
  const allTeams = Object.values(groups).flat();
  const stages = ["r32", "r16", "qf", "sf", "final", "champion"] as const;
  const positions = ["first", "second", "third", "fourth"] as const;
  const counts: Record<string, Record<string, number>> = {};
  for (const t of allTeams) {
    counts[t] = Object.fromEntries([...stages, ...positions].map((s) => [s, 0]));
  }

  const elos = Object.fromEntries(allTeams.map((t) => [t, teams[t]?.elo ?? 1500]));
  const penRates = buildPenRates(teams);

  for (let sim = 0; sim < n; sim++) {
    const thirds: Array<{ team: string; pts: number; elo: number }> = [];
    const r32: string[] = [];

    for (const gteams of Object.values(groups)) {
      const { standings, points } = simulateGroup(gteams, predictions, elos, fixedResults);
      // track group finish positions (0=1st, 1=2nd, 2=3rd, 3=4th)
      standings.forEach((t, i) => { counts[t][positions[Math.min(i, 3)]]++; });
      r32.push(standings[0], standings[1]);
      thirds.push({ team: standings[2], pts: points[standings[2]] ?? 0, elo: elos[standings[2]] ?? 1500 });
    }

    thirds.sort((a, b) => b.pts - a.pts || b.elo - a.elo);
    const bracket = [...r32, ...thirds.slice(0, 8).map((x) => x.team)];
    for (const t of bracket) counts[t].r32++;

    // shuffle bracket for knockout draw
    for (let i = bracket.length - 1; i > 0; i--) {
      const j = Math.floor(Math.random() * (i + 1));
      [bracket[i], bracket[j]] = [bracket[j], bracket[i]];
    }

    const roundKeys: (typeof stages[number])[] = ["r16", "qf", "sf", "final", "champion"];
    let current = bracket;
    for (const stage of roundKeys) {
      const next: string[] = [];
      for (let i = 0; i < current.length; i += 2) {
        const p = getProbs(predictions, current[i], current[i + 1]);
        next.push(sampleKnockout(p, current[i], current[i + 1], penRates));
      }
      for (const t of next) counts[t][stage]++;
      current = next;
      if (stage === "champion") break;
    }
  }

  return allTeams
    .map((team) => ({
      team,
      flag: teams[team]?.flag ?? "🏳️",
      group: teams[team]?.group ?? "?",
      confederation: teams[team]?.confederation ?? "?",
      elo: elos[team],
      first:   counts[team].first   / n,
      second:  counts[team].second  / n,
      third:   counts[team].third   / n,
      fourth:  counts[team].fourth  / n,
      r32:     counts[team].r32     / n,
      r16:     counts[team].r16     / n,
      qf:      counts[team].qf      / n,
      sf:      counts[team].sf      / n,
      final:   counts[team].final   / n,
      champion: counts[team].champion / n,
    }))
    .sort((a, b) => b.champion - a.champion);
}
