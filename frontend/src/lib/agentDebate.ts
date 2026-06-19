import type { GroupMatch } from "@/types";
import type { ScoreMap, Verdict } from "@/lib/live";
import { orientScore } from "@/lib/live";

/* ── Tipos ─────────────────────────────────────────────────────────────── */

export interface AgentTopPrediction {
  home_goals: number;
  away_goals: number;
  probability: number;
  predicted_winner: "home" | "draw" | "away";
}

export interface AgentDebateMatch {
  match: string;
  home: string;
  away: string;
  context?: {
    home_team?: { name: string; points: number; goal_diff: number; status: string; md1_result?: string };
    away_team?: { name: string; points: number; goal_diff: number; status: string; md1_result?: string };
  };
  consensus: string;
  /** Compat hacia atrás: igual a predictions[0]. */
  top_prediction?: AgentTopPrediction | null;
  /** Top-2 predicciones estructuradas del consenso (🥇 y 🥈). */
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
    const rk = pairKey(r.home, r.away);
    return rk === key || rk === keyRev;
  });
}

/* ── Orienta una predicción (home/away del debate) al orden team1/team2 ── */

function orientPrediction(
  debateMatch: AgentDebateMatch,
  m: GroupMatch,
  pred: AgentTopPrediction
): { g1: number; g2: number; winner: "t1" | "draw" | "t2" } {
  const debateIsSameOrder = normalizeTeamName(debateMatch.home) === normalizeTeamName(m.team1);
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
  /** Acertó quién gana (1X2), comparado contra la predicción favorita (🥇). */
  hit: boolean;
  /** Acertó el marcador exacto con la 🥇 o la 🥈. null si no hay predictions[] parseadas. */
  scoreHit: boolean | null;
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
      if (!debateMatch) continue; // sin debate de agentes para este partido

      const verdict = agentVerdict(debateMatch, m, score);
      if (!verdict) continue; // debate sin top_prediction parseable

      out.push({
        group,
        groupMd: roundToJor(m.round ?? "Matchday 1"),
        team1: m.team1,
        team2: m.team2,
        hit: verdict.hit,
        scoreHit: agentScoreHit(debateMatch, m, score),
      });
    }
  }
  return out;
}
