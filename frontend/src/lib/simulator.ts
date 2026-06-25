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

// ── Bracket oficial 2026 ──────────────────────────────────────────────────────
// Cruces reales de la Ronda de 32 según el fixture oficial (partidos 73–88).
// "1A"/"2A" = primero/segundo del grupo A; "3:ABCDF" = mejor tercero de A/B/C/D/F.
const R32_SLOTS = [
  ["2A", "2B"],      // 73
  ["1E", "3:ABCDF"], // 74
  ["1F", "2C"],      // 75
  ["1C", "2F"],      // 76
  ["1I", "3:CDFGH"], // 77
  ["2E", "2I"],      // 78
  ["1A", "3:CEFHI"], // 79
  ["1L", "3:EHIJK"], // 80
  ["1D", "3:BEFIJ"], // 81
  ["1G", "3:AEHIJ"], // 82
  ["2K", "2L"],      // 83
  ["1H", "2J"],      // 84
  ["1B", "3:EFGIJ"], // 85
  ["1J", "2H"],      // 86
  ["1K", "3:DEIJL"], // 87
  ["2D", "2G"],      // 88
] as const;

// Rondas siguientes: pares de índices sobre los ganadores de la ronda anterior.
const R16_PAIRS = [[1, 4], [0, 2], [3, 5], [6, 7], [10, 11], [8, 9], [13, 15], [12, 14]] as const; // 89–96
const QF_PAIRS = [[0, 1], [4, 5], [2, 3], [6, 7]] as const; // 97–100
const SF_PAIRS = [[0, 1], [2, 3]] as const; // 101–102

const THIRD_SLOTS: Array<{ r32Index: number; allowed: string[] }> = R32_SLOTS.flatMap(
  ([, away], i) => (away.startsWith("3:") ? [{ r32Index: i, allowed: away.slice(2).split("") }] : [])
);

/**
 * Asigna los 8 mejores terceros a sus slots del bracket respetando las
 * restricciones de grupo del fixture (backtracking; los slots más restringidos
 * primero). Si la combinación no admite asignación perfecta, cae a greedy.
 */
function assignThirds(qualified: Map<string, string>): Record<number, string> {
  const order = [...THIRD_SLOTS].sort(
    (a, b) =>
      a.allowed.filter((g) => qualified.has(g)).length -
      b.allowed.filter((g) => qualified.has(g)).length
  );
  const used = new Set<string>();
  const result: Record<number, string> = {};

  function bt(k: number): boolean {
    if (k === order.length) return true;
    const slot = order[k];
    for (const g of slot.allowed) {
      if (qualified.has(g) && !used.has(g)) {
        used.add(g);
        result[slot.r32Index] = qualified.get(g)!;
        if (bt(k + 1)) return true;
        used.delete(g);
        delete result[slot.r32Index];
      }
    }
    return false;
  }

  if (!bt(0)) {
    used.clear();
    const avail = [...qualified.keys()];
    for (const slot of order) {
      const g =
        slot.allowed.find((x) => qualified.has(x) && !used.has(x)) ??
        avail.find((x) => !used.has(x))!;
      used.add(g);
      result[slot.r32Index] = qualified.get(g)!;
    }
  }
  return result;
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
    counts[t] = Object.fromEntries([...stages, ...positions, "bestThird"].map((s) => [s, 0]));
  }

  const elos = Object.fromEntries(allTeams.map((t) => [t, teams[t]?.elo ?? 1500]));
  const penRates = buildPenRates(teams);

  for (let sim = 0; sim < n; sim++) {
    const firsts: Record<string, string> = {};
    const seconds: Record<string, string> = {};
    const thirds: Array<{ group: string; team: string; pts: number; elo: number }> = [];

    for (const [gname, gteams] of Object.entries(groups)) {
      const { standings, points } = simulateGroup(gteams, predictions, elos, fixedResults);
      // track group finish positions (0=1st, 1=2nd, 2=3rd, 3=4th)
      standings.forEach((t, i) => { counts[t][positions[Math.min(i, 3)]]++; });
      firsts[gname] = standings[0];
      seconds[gname] = standings[1];
      thirds.push({
        group: gname,
        team: standings[2],
        pts: points[standings[2]] ?? 0,
        elo: elos[standings[2]] ?? 1500,
      });
    }

    thirds.sort((a, b) => b.pts - a.pts || b.elo - a.elo);
    const qualifiedThirds = new Map(thirds.slice(0, 8).map((x) => [x.group, x.team]));
    for (const t of qualifiedThirds.values()) counts[t].bestThird++;
    const thirdByR32 = assignThirds(qualifiedThirds);

    // ── Ronda de 32 según el bracket oficial ──
    const r32Matches: Array<[string, string]> = R32_SLOTS.map(([home, away], i) => {
      const resolve = (slot: string): string =>
        slot.startsWith("3:") ? thirdByR32[i] : slot[0] === "1" ? firsts[slot[1]] : seconds[slot[1]];
      return [resolve(home), resolve(away)];
    });
    for (const [t1, t2] of r32Matches) { counts[t1].r32++; counts[t2].r32++; }

    let winners = r32Matches.map(([t1, t2]) =>
      sampleKnockout(getProbs(predictions, t1, t2), t1, t2, penRates)
    );
    for (const t of winners) counts[t].r16++;

    // ── R16 → QF → SF → Final, con los emparejamientos del fixture ──
    const rounds: Array<{ pairs: ReadonlyArray<readonly [number, number]>; stage: typeof stages[number] }> = [
      { pairs: R16_PAIRS, stage: "qf" },
      { pairs: QF_PAIRS, stage: "sf" },
      { pairs: SF_PAIRS, stage: "final" },
      { pairs: [[0, 1]], stage: "champion" },
    ];
    for (const { pairs, stage } of rounds) {
      winners = pairs.map(([i, j]) =>
        sampleKnockout(getProbs(predictions, winners[i], winners[j]), winners[i], winners[j], penRates)
      );
      for (const t of winners) counts[t][stage]++;
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
      bestThird: counts[team].bestThird / n,
      r32:     counts[team].r32     / n,
      r16:     counts[team].r16     / n,
      qf:      counts[team].qf      / n,
      sf:      counts[team].sf      / n,
      final:   counts[team].final   / n,
      champion: counts[team].champion / n,
    }))
    .sort((a, b) => b.champion - a.champion);
}
