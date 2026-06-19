import type { GroupMatch } from "@/types";
import type { ScoreMap, Verdict } from "@/lib/live";
import { orientScore } from "@/lib/live";

/* ── Tipos ─────────────────────────────────────────────────────────────── */

export interface AgentTopPrediction {
  home_goals: number;
  away_goals: number;
  probability: number;
  predicted_winner: "home" | "draw" | "away";
  agent?: string; // Nombre del agente que propuso esta predicción
}

export interface AgentDebateMatch {
  match: string;
  home?: string;
  away?: string;
  context?: {
    home_team?: { name: string; points: number; goal_diff: number; status: string; md1_result?: string };
    away_team?: { name: string; points: number; goal_diff: number; status: string; md1_result?: string };
  };
  consensus: string;
  /** Compat hacia atrás: igual a predictions[0]. */
  top_prediction?: AgentTopPrediction | null;
  /** Todas las predicciones: 3 agentes individuales + 1 consenso. */
  predictions?: AgentTopPrediction[];
}

/* ── Normalización de nombres (mismo mapeo que el backend Python) ───────── */

const TEAM_NAME_MAPPING: Record<string, string> = {
  USA: "United States",
  "United States": "United States",
};

export function normalizeTeamName(name: string): string {
  return TEAM_NAME_MAPPING[name] ?? name;
}

function debateTeams(r: AgentDebateMatch): { home: string; away: string } | null {
  const home = r.home ?? r.context?.home_team?.name;
  const away = r.away ?? r.context?.away_team?.name;
  if (home && away) return { home, away };
  if (r.match?.includes(" vs ")) {
    const [matchHome, matchAway] = r.match.split(" vs ", 2).map((part) => part.trim());
    if (matchHome && matchAway) return { home: matchHome, away: matchAway };
  }
  return null;
}

function pairKey(t1: string, t2: string): string {
  return `${normalizeTeamName(t1)}|${normalizeTeamName(t2)}`;
}

/* ── Búsqueda de debate para un partido (orden-independiente) ───────────── */

export function findAgentMatch(
  results: AgentDebateMatch[],
  team1: string,
  team2: string
): AgentDebateMatch | undefined {
  const key = pairKey(team1, team2);
  const keyRev = pairKey(team2, team1);
  return results.find((r) => {
    const teams = debateTeams(r);
    if (!teams) return false;
    const rk = pairKey(teams.home, teams.away);
    return rk === key || rk === keyRev;
  });
}

/* ── Orienta una predicción (home/away del debate) al orden team1/team2 ── */

function orientPrediction(
  debateMatch: AgentDebateMatch,
  m: GroupMatch,
  pred: AgentTopPrediction
): { g1: number; g2: number; winner: "t1" | "draw" | "t2" } {
  const teams = debateTeams(debateMatch);
  const debateHome = teams?.home ?? m.team1;
  const debateIsSameOrder = normalizeTeamName(debateHome) === normalizeTeamName(m.team1);
  const g1 = debateIsSameOrder ? pred.home_goals : pred.away_goals;
  const g2 = debateIsSameOrder ? pred.away_goals : pred.home_goals;
  const winner: "t1" | "draw" | "t2" = g1 > g2 ? "t1" : g1 < g2 ? "t2" : "draw";
  return { g1, g2, winner };
}

/* ── Veredicto del agente vs resultado real (1X2) ────────────────────────
   Espejo de modelVerdict en lib/live.ts, pero usando el top_prediction
   estructurado del consenso de los 3 agentes en lugar de las probs ML. ── */

export function agentVerdict(
  debateMatch: AgentDebateMatch,
  m: GroupMatch,
  s: { s1: number; s2: number }
): Verdict | null {
  const top = debateMatch.top_prediction;
  if (!top) return null;

  const actual = s.s1 > s.s2 ? "t1" : s.s1 < s.s2 ? "t2" : "draw";
  const { winner: predicted } = orientPrediction(debateMatch, m, top);

  return { hit: predicted === actual, predicted, prob: top.probability };
}

/** Marcador exacto: hit si el resultado real coincide con CUALQUIERA de las
 * top-2 predicciones de los agentes (🥇 o 🥈), no solo la favorita. */
export function agentScoreHit(
  debateMatch: AgentDebateMatch,
  m: GroupMatch,
  s: { s1: number; s2: number }
): boolean | null {
  const preds = debateMatch.predictions?.slice(0, 2) ?? [];
  if (!preds.length) return null;

  return preds.some((p) => {
    const { g1, g2 } = orientPrediction(debateMatch, m, p);
    return g1 === s.s1 && g2 === s.s2;
  });
}

/* ── Resultado de un partido evaluado por los agentes (para tablas) ─────── */

export interface AgentMatchResult {
  group: string;
  groupMd: number;
  team1: string;
  team2: string;
  /** Acertó quién gana (1X2) para cada predicción (por agente + consenso). */
  hits: Record<string, boolean>;
  /** Acertó el marcador exacto para cada predicción. */
  scoreHits: Record<string, boolean | null>;
}

export interface AgentStats {
  hits: number;
  played: number;
}

function roundToJor(round: string): number {
  const n = parseInt(round.replace(/\D/g, ""), 10);
  if (n <= 7) return 1;
  if (n <= 13) return 2;
  return 3;
}

export function computeAgentResults(
  groupMatches: Record<string, GroupMatch[]>,
  liveScores: ScoreMap,
  agentResults: AgentDebateMatch[]
): AgentMatchResult[] {
  const out: AgentMatchResult[] = [];
  for (const [group, matches] of Object.entries(groupMatches)) {
    for (const m of matches) {
      const score = orientScore(m, liveScores);
      if (!score) continue; // partido no jugado aún

      const debateMatch = findAgentMatch(agentResults, m.team1, m.team2);
      if (!debateMatch || !debateMatch.predictions?.length) continue; // sin predicciones parseadas

      const hits: Record<string, boolean> = {};
      const scoreHits: Record<string, boolean | null> = {};

      // Evaluar cada predicción (4: 3 agentes + consenso)
      for (const pred of debateMatch.predictions) {
        const agentName = pred.agent ?? "Unknown";
        const { g1, g2, winner } = orientPrediction(debateMatch, m, pred);
        const actual = score.s1 > score.s2 ? "t1" : score.s1 < score.s2 ? "t2" : "draw";

        hits[agentName] = winner === actual;
        scoreHits[agentName] = g1 === score.s1 && g2 === score.s2;
      }

      out.push({
        group,
        groupMd: roundToJor(m.round ?? "Matchday 1"),
        team1: m.team1,
        team2: m.team2,
        hits,
        scoreHits,
      });
    }
  }
  return out;
}

/** Agrupa resultados por nombre de agente para evaluar desempeño individual. */
export function computeAgentStatsByAgent(
  agentResults: AgentMatchResult[]
): Record<string, AgentStats> {
  const stats: Record<string, AgentStats> = {};
  for (const r of agentResults) {
    for (const [agent, hit] of Object.entries(r.hits)) {
      if (!stats[agent]) {
        stats[agent] = { hits: 0, played: 0 };
      }
      stats[agent].played++;
      if (hit) stats[agent].hits++;
    }
  }
  return stats;
}
