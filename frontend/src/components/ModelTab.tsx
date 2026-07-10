"use client";

import { useEffect, useMemo, useState } from "react";
import type { GroupMatch, TeamInfo } from "@/types";
import type { ScoreMap } from "@/lib/live";
import { orientScore, modelVerdict } from "@/lib/live";
import { computeAgentResults, computeAgentStatsByAgent, computeAgentStatsByPhase, findAgentMatch, phaseKeyOf, type AgentDebateMatch, type AgentMatchResult, type AgentStats, type AgentTopPrediction } from "@/lib/agentDebate";
import type { BracketData, KnockoutMatch } from "@/components/KnockoutBracket";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  teams: Record<string, TeamInfo>;
  bracket?: BracketData | null;
}

type RoundMap = Record<string, { hits: number; played: number }>;

function buildByRound(results: { roundKey: string; hit: boolean }[]): RoundMap {
  const map: RoundMap = {};
  for (const r of results) {
    if (!map[r.roundKey]) map[r.roundKey] = { hits: 0, played: 0 };
    map[r.roundKey].played++;
    if (r.hit) map[r.roundKey].hits++;
  }
  return map;
}

interface MatchResult {
  group: string;
  groupMd: number;   // 1, 2 or 3 (internal group matchday)
  phase: "group" | "knockout";
  /** Clave de ronda del bracket (round_order), ej. "Round of 32". Solo en knockout. */
  roundKey?: string;
  round: string;
  team1: string;
  team2: string;
  t1_flag: string;
  t2_flag: string;
  score1: number;
  score2: number;
  predicted: "t1" | "draw" | "t2";
  actual: "t1" | "draw" | "t2";
  prob: number;
  hit: boolean;
}

function computeResults(
  groupMatches: Record<string, GroupMatch[]>,
  liveScores: ScoreMap,
  teams: Record<string, TeamInfo>
): MatchResult[] {
  const out: MatchResult[] = [];
  for (const [group, matches] of Object.entries(groupMatches)) {
    // Map global matchday number to internal JOR (1/2/3).
    // Groups B and D have JOR-1 games split across two global matchday dates,
    // so unique-date counting breaks for them. Use round number ranges instead:
    //   Matchday 1-7  → JOR 1 (first game of each group)
    //   Matchday 8-13 → JOR 2 (second game of each group)
    //   Matchday 14+  → JOR 3 (third game, simultaneous)
    function roundToJor(round: string): number {
      const n = parseInt(round.replace(/\D/g, ""), 10);
      if (n <= 7)  return 1;
      if (n <= 13) return 2;
      return 3;
    }

    for (const m of matches) {
      const score = orientScore(m, liveScores);
      if (!score) continue;
      const v = modelVerdict(m, score);
      const actual: "t1" | "draw" | "t2" =
        score.s1 > score.s2 ? "t1" : score.s1 < score.s2 ? "t2" : "draw";
      out.push({
        group,
        groupMd: roundToJor(m.round ?? "Matchday 1"),
        phase: "group",
        round: m.round ?? "Fase de grupos",
        team1: m.team1,
        team2: m.team2,
        t1_flag: m.team1_flag,
        t2_flag: m.team2_flag,
        score1: score.s1,
        score2: score.s2,
        predicted: v.predicted,
        actual,
        prob: v.prob,
        hit: v.hit,
      });
    }
  }
  return out;
}

function predictionSide(pred?: KnockoutMatch["pred"]): { side: "home" | "draw" | "away"; prob: number } | null {
  if (!pred) return null;
  const entries: Array<["home" | "draw" | "away", number]> = [
    ["home", pred.p_home],
    ["draw", pred.p_draw],
    ["away", pred.p_away],
  ];
  const [side, prob] = entries.sort((a, b) => b[1] - a[1])[0];
  return { side, prob };
}

function computeKnockoutResults(
  bracket: BracketData | null | undefined,
  teams: Record<string, TeamInfo>
): MatchResult[] {
  const out: MatchResult[] = [];
  const matches = Object.values(bracket?.rounds ?? {}).flat();
  for (const m of matches) {
    if (!m.home || !m.away || !m.pred || !m.result?.played) continue;
    const pick = predictionSide(m.pred);
    if (!pick) continue;
    const predicted = pick.side === "home" ? "t1" : pick.side === "away" ? "t2" : "draw";
    const actual = m.result.home_score > m.result.away_score ? "t1" : m.result.home_score < m.result.away_score ? "t2" : "draw";
    out.push({
      group: m.round,
      groupMd: 4,
      phase: "knockout",
      roundKey: m.round,
      round: m.round_es || m.round,
      team1: m.home,
      team2: m.away,
      t1_flag: teams[m.home]?.flag ?? "",
      t2_flag: teams[m.away]?.flag ?? "",
      score1: m.result.home_score,
      score2: m.result.away_score,
      predicted,
      actual,
      prob: pick.prob,
      hit: predicted === actual,
    });
  }
  return out;
}

/** Rondas de knockout con al menos un cruce resuelto y con predicción, en orden de bracket. */
function resolvedRoundFixtures(
  bracket: BracketData | null | undefined
): { roundKey: string; label: string; fixtures: KnockoutMatch[] }[] {
  const order = bracket?.round_order ?? [];
  const labels = bracket?.round_labels ?? {};
  const out: { roundKey: string; label: string; fixtures: KnockoutMatch[] }[] = [];
  for (const roundKey of order) {
    const fixtures = (bracket?.rounds?.[roundKey] ?? [])
      .filter((m) => m.home && m.away && m.pred)
      .sort((a, b) => a.num - b.num);
    if (fixtures.length > 0) {
      out.push({ roundKey, label: labels[roundKey] ?? roundKey, fixtures });
    }
  }
  return out;
}

const cardBg = { background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.06)" };

function Pill({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className="rounded-xl p-4 text-center" style={cardBg}>
      <div className="font-mono text-base font-black leading-tight" style={{ color }}>{value}</div>
      <div className="text-[0.6rem] mt-1 leading-snug" style={{ color: "var(--color-ink-muted)" }}>{label}</div>
    </div>
  );
}

interface PhaseInfo { key: string; label: string }

/* ── Bloque reutilizable: precisión por fase, grupos + eliminatorias en una sola secuencia ── */
function PhaseAccuracy({
  title,
  phaseOrder,
  byPhase,
}: {
  title: string;
  phaseOrder: PhaseInfo[];
  byPhase: RoundMap;
}) {
  const active = phaseOrder.filter((p) => byPhase[p.key]);
  return (
    <div className="rounded-xl p-5 space-y-3" style={cardBg}>
      <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>{title}</h3>
      {active.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
          Sin partidos evaluados todavía.
        </p>
      ) : (
        <div className="space-y-2">
          {active.map((phase, i) => {
            const data = byPhase[phase.key];
            const p = Math.round((data.hits / data.played) * 100);
            const prevPhase = i > 0 ? active[i - 1] : null;
            const prev = prevPhase ? byPhase[prevPhase.key] : null;
            const delta = prev ? p - Math.round((prev.hits / prev.played) * 100) : null;
            return (
              <div key={phase.key} className="flex items-center gap-3">
                <span className="shrink-0 font-mono text-[0.62rem] truncate" style={{ color: "var(--color-ink-muted)", width: 76 }}>
                  {phase.label}
                </span>
                <div className="flex-1 rounded-full overflow-hidden" style={{ height: 6, background: "rgba(255,255,255,0.06)" }}>
                  <div
                    className="h-full rounded-full transition-all duration-700"
                    style={{ width: `${p}%`, background: p >= 50 ? "var(--color-wc-gold)" : "var(--color-wc-red)" }}
                  />
                </div>
                <span className="shrink-0 font-mono font-bold text-xs" style={{ color: "var(--color-ink)", width: 34, textAlign: "right" }}>
                  {p}%
                </span>
                <span className="shrink-0 text-[0.6rem]" style={{ color: "var(--color-ink-muted)", width: 52 }}>
                  {data.hits}/{data.played}
                </span>
                <div className="shrink-0 w-16 text-right">
                  <Arrow delta={delta} />
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

const AGENT_EMOJI: Record<string, string> = {
  "Group Analyst": "🔵",
  "Tactical Scout": "🟠",
  "Sentiment Reader": "🟡",
  Consensus: "🏆",
};

/* ── Tabla: qué agente acertó más en cada fase del torneo ── */
function AgentPhaseTable({
  phaseOrder,
  agentNames,
  statsByPhase,
  playedPhaseKeys,
}: {
  phaseOrder: PhaseInfo[];
  agentNames: string[];
  statsByPhase: Record<string, Record<string, AgentStats>>;
  /** Fases donde el torneo ya tiene partidos jugados (aunque no haya debates). */
  playedPhaseKeys: Set<string>;
}) {
  // Mostrar toda fase ya jugada, tenga o no debates: una fila de "—" con nota
  // es honesta; ocultar la fila hace parecer que la tabla está rota.
  const active = phaseOrder.filter((p) => statsByPhase[p.key] || playedPhaseKeys.has(p.key));
  const missingDebates = active.filter((p) => !statsByPhase[p.key]);
  return (
    <div className="rounded-xl p-5 space-y-3" style={cardBg}>
      <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
        🤖 Precisión por fase · Agentes
      </h3>
      {active.length === 0 ? (
        <p className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
          Sin partidos evaluados todavía.
        </p>
      ) : (
        <div className="space-y-1.5">
          <div className="grid gap-1 items-center" style={{ gridTemplateColumns: "56px repeat(4, 1fr)" }}>
            <span />
            {agentNames.map((name) => (
              <span key={name} className="text-center text-[0.55rem] truncate" style={{ color: "var(--color-ink-muted)" }} title={name}>
                {AGENT_EMOJI[name] ?? ""}
              </span>
            ))}
          </div>
          {active.map((phase) => {
            const row = statsByPhase[phase.key] ?? {};
            let bestName: string | null = null;
            let bestPct = -1;
            for (const name of agentNames) {
              const s = row[name];
              if (!s || s.played === 0) continue;
              const pct = Math.round((s.hits / s.played) * 100);
              if (pct > bestPct) { bestPct = pct; bestName = name; }
            }
            return (
              <div key={phase.key} className="grid gap-1 items-center" style={{ gridTemplateColumns: "56px repeat(4, 1fr)" }}>
                <span className="font-mono text-[0.58rem] truncate" style={{ color: "var(--color-ink-muted)" }}>
                  {phase.label}
                </span>
                {agentNames.map((name) => {
                  const s = row[name];
                  const pct = s && s.played > 0 ? Math.round((s.hits / s.played) * 100) : null;
                  const isBest = name === bestName && pct !== null;
                  return (
                    <div
                      key={name}
                      className="rounded text-center py-1"
                      style={{
                        background: isBest ? "rgba(201,152,31,0.15)" : "rgba(255,255,255,0.03)",
                        border: isBest ? "1px solid rgba(201,152,31,0.4)" : "1px solid transparent",
                      }}
                    >
                      <span
                        className="font-mono text-[0.6rem] font-bold"
                        style={{ color: pct === null ? "var(--color-ink-muted)" : isBest ? "var(--color-wc-gold)" : "var(--color-ink)" }}
                      >
                        {pct !== null ? `${pct}%` : "—"}
                      </span>
                    </div>
                  );
                })}
              </div>
            );
          })}
          <div className="flex items-center gap-3 pt-1 text-[0.55rem] flex-wrap" style={{ color: "var(--color-ink-muted)" }}>
            {agentNames.map((name) => (
              <span key={name}>{AGENT_EMOJI[name]} {name}</span>
            ))}
          </div>
          {missingDebates.length > 0 && (
            <p className="text-[0.55rem] pt-1" style={{ color: "var(--color-ink-muted)" }}>
              — {missingDebates.map((p) => p.label).join(", ")}: sin debates de agentes. El Agent Debate arrancó en la Jornada 3 y solo evalúa partidos debatidos <em>antes</em> de jugarse (no hay backfill retroactivo).
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function Arrow({ delta }: { delta: number | null }) {
  if (delta === null) return <span style={{ color: "var(--color-ink-muted)", fontSize: "0.7rem" }}>—</span>;
  if (delta > 0)  return <span style={{ color: "#34d399", fontSize: "0.7rem" }}>▲ +{delta}pp</span>;
  if (delta < 0)  return <span style={{ color: "var(--color-wc-red)", fontSize: "0.7rem" }}>▼ {delta}pp</span>;
  return <span style={{ color: "var(--color-ink-muted)", fontSize: "0.7rem" }}>= 0pp</span>;
}

function labelForOutcome(outcome: "t1" | "draw" | "t2", team1: string, team2: string) {
  if (outcome === "t1") return team1;
  if (outcome === "t2") return team2;
  return "Empate";
}

function KnockoutRoundSection({
  roundKey,
  label,
  fixtures,
  allKnockoutResults,
  teams,
}: {
  roundKey: string;
  label: string;
  fixtures: KnockoutMatch[];
  allKnockoutResults: MatchResult[];
  teams: Record<string, TeamInfo>;
}) {
  const results = allKnockoutResults.filter((r) => r.roundKey === roundKey);
  const played = results.length;
  const hits = results.filter((r) => r.hit).length;
  const pct = played ? Math.round((hits / played) * 100) : null;

  return (
    <details className="rounded-xl p-5" style={{ ...cardBg, borderColor: "rgba(201,152,31,0.22)" }}>
      <summary className="flex items-start justify-between gap-3 flex-wrap cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden">
        <div>
          <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
            {label} · Evaluación de eliminatorias
            <span className="ml-2 text-[0.6rem] font-normal" style={{ color: "var(--color-ink-muted)" }}>▾ ver partidos</span>
          </h3>
          <p className="text-[0.6rem] mt-1" style={{ color: "var(--color-ink-muted)" }}>
            El modelo ya cuenta los partidos de esta ronda con resultado oficial del bracket.
          </p>
        </div>
        <div className="rounded-lg px-3 py-2 text-right" style={{ background: "rgba(201,152,31,0.08)", border: "1px solid rgba(201,152,31,0.25)" }}>
          <div className="font-mono font-black text-base" style={{ color: "var(--color-wc-gold)" }}>
            {pct !== null ? `${pct}%` : "-"}
          </div>
          <div className="text-[0.58rem]" style={{ color: "var(--color-ink-muted)" }}>
            {hits}/{played} aciertos
          </div>
        </div>
      </summary>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-4">
        {fixtures.map((m) => {
          const result = results.find((r) => r.team1 === m.home && r.team2 === m.away);
          const pick = predictionSide(m.pred);
          const predicted =
            pick?.side === "home" ? m.home :
            pick?.side === "away" ? m.away :
            pick?.side === "draw" ? "Empate" : "-";
          const playedLabel = result
            ? `${result.score1}-${result.score2}`
            : "Pendiente";
          const hitColor = result?.hit ? "#34d399" : "var(--color-wc-red)";

          return (
            <div
              key={m.num}
              className="rounded-lg p-3 space-y-2"
              style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-[0.55rem]" style={{ color: "var(--color-ink-muted)" }}>
                  #{m.num} · {m.date}
                </span>
                <span className="font-mono text-[0.58rem] font-bold" style={{ color: result ? hitColor : "var(--color-ink-muted)" }}>
                  {result ? (result.hit ? "ACIERTO" : "FALLO") : "POR JUGAR"}
                </span>
              </div>
              <div className="flex items-center justify-between gap-2 text-xs font-bold" style={{ color: "var(--color-ink)" }}>
                <span>{teams[m.home ?? ""]?.flag} {m.home}</span>
                <span className="font-mono" style={{ color: result ? "var(--color-ink)" : "var(--color-ink-muted)" }}>{playedLabel}</span>
                <span>{m.away} {teams[m.away ?? ""]?.flag}</span>
              </div>
              <div className="flex items-center justify-between gap-2 text-[0.62rem]" style={{ color: "var(--color-ink-muted)" }}>
                <span>Predicción: <strong style={{ color: "var(--color-ink)" }}>{predicted}</strong></span>
                <span className="font-mono">{pick ? `${Math.round(pick.prob * 100)}%` : "-"}</span>
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
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

function orientAgentPrediction(
  debateMatch: AgentDebateMatch,
  team1: string,
  pred: AgentTopPrediction
): { g1: number; g2: number; winner: "t1" | "draw" | "t2" } {
  const teams = debateTeams(debateMatch);
  const debateHome = teams?.home ?? team1;
  const sameOrder = debateHome === team1;
  const g1 = sameOrder ? pred.home_goals : pred.away_goals;
  const g2 = sameOrder ? pred.away_goals : pred.home_goals;
  const winner = g1 > g2 ? "t1" : g1 < g2 ? "t2" : "draw";
  return { g1, g2, winner };
}

function computeKnockoutAgentResults(
  bracket: BracketData | null | undefined,
  agentDebateResults: AgentDebateMatch[]
): AgentMatchResult[] {
  const out: AgentMatchResult[] = [];
  for (const m of Object.values(bracket?.rounds ?? {}).flat()) {
    if (!m.home || !m.away || !m.result?.played) continue;
    const debateMatch = findAgentMatch(agentDebateResults, m.home, m.away);
    if (!debateMatch?.predictions?.length) continue;

    const actual = m.result.home_score > m.result.away_score ? "t1" : m.result.home_score < m.result.away_score ? "t2" : "draw";
    const hits: Record<string, boolean> = {};
    const scoreHits: Record<string, boolean | null> = {};
    const goals: Record<string, { g1: number; g2: number }> = {};

    for (const pred of debateMatch.predictions) {
      const agentName = pred.agent ?? "Unknown";
      const { g1, g2, winner } = orientAgentPrediction(debateMatch, m.home, pred);
      hits[agentName] = winner === actual;
      scoreHits[agentName] = g1 === m.result.home_score && g2 === m.result.away_score;
      goals[agentName] = { g1, g2 };
    }

    out.push({
      group: m.round,
      groupMd: 4,
      phase: "knockout",
      roundKey: m.round,
      team1: m.home,
      team2: m.away,
      score1: m.result.home_score,
      score2: m.result.away_score,
      hits,
      scoreHits,
      goals,
    });
  }
  return out;
}

export default function ModelTab({ groupMatches, liveScores, teams, bracket }: Props) {
  const groupResults = useMemo(
    () => computeResults(groupMatches, liveScores, teams),
    [groupMatches, liveScores, teams]
  );
  const knockoutResults = useMemo(
    () => computeKnockoutResults(bracket, teams),
    [bracket, teams]
  );
  const results = useMemo(
    () => [...groupResults, ...knockoutResults],
    [groupResults, knockoutResults]
  );
  const roundFixtures = useMemo(() => resolvedRoundFixtures(bracket), [bracket]);

  // ── Fases unificadas: JOR 1/2/3 (grupos) + R32/R16/QF/SF/Final (eliminatorias),
  // en una sola secuencia continua para poder ver la progresión completa. ──
  const phaseOrder: PhaseInfo[] = useMemo(() => {
    const groupPhases: PhaseInfo[] = [
      { key: "jor1", label: "JOR 1" },
      { key: "jor2", label: "JOR 2" },
      { key: "jor3", label: "JOR 3" },
    ];
    const knockoutPhases: PhaseInfo[] = (bracket?.round_order ?? []).map((rk) => ({
      key: rk,
      label: bracket?.round_labels?.[rk] ?? rk,
    }));
    return [...groupPhases, ...knockoutPhases];
  }, [bracket]);

  // ── Precisión por fase (Modelo ML): grupos (JOR) + eliminatorias, combinadas ──
  const mlByRound = useMemo(
    () =>
      buildByRound(
        knockoutResults
          .filter((r): r is MatchResult & { roundKey: string } => !!r.roundKey)
          .map((r) => ({ roundKey: r.roundKey, hit: r.hit }))
      ),
    [knockoutResults]
  );

  // ── Global KPIs ────────────────────────────────────────────────────────────
  const played = results.length;
  const hits   = results.filter((r) => r.hit).length;
  const pctGlobal = played > 0 ? Math.round((hits / played) * 100) : null;

  // ── Per internal matchday ──────────────────────────────────────────────────
  const byMd = useMemo(() => {
    const map: Record<number, { hits: number; played: number }> = {};
    for (const r of results) {
      if (!map[r.groupMd]) map[r.groupMd] = { hits: 0, played: 0 };
      map[r.groupMd].played++;
      if (r.hit) map[r.groupMd].hits++;
    }
    return map;
  }, [results]);

  const mlByPhase: RoundMap = useMemo(() => {
    const map: RoundMap = {};
    for (const md of [1, 2, 3]) {
      if (byMd[md]) map[`jor${md}`] = byMd[md];
    }
    Object.assign(map, mlByRound);
    return map;
  }, [byMd, mlByRound]);

  // ── Agent Debate: precisión por jornada ───────────────────────────────────
  const [agentDebateResults, setAgentDebateResults] = useState<AgentDebateMatch[]>([]);

  useEffect(() => {
    let active = true;
    fetch("/api/agent-debate")
      .then((r) => r.json())
      .then((data) => {
        if (active && Array.isArray(data)) setAgentDebateResults(data);
      })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const groupAgentResults: AgentMatchResult[] = useMemo(
    () => computeAgentResults(groupMatches, liveScores, agentDebateResults),
    [groupMatches, liveScores, agentDebateResults]
  );
  const knockoutAgentResults: AgentMatchResult[] = useMemo(
    () => computeKnockoutAgentResults(bracket, agentDebateResults),
    [bracket, agentDebateResults]
  );
  const agentResults: AgentMatchResult[] = useMemo(
    () => [...groupAgentResults, ...knockoutAgentResults],
    [groupAgentResults, knockoutAgentResults]
  );
  // ── Desempeño por agente individual, global y por fase ───────────────────
  const agentStatsByAgent = useMemo(() => computeAgentStatsByAgent(agentResults), [agentResults]);
  const agentStatsByPhase = useMemo(() => computeAgentStatsByPhase(agentResults), [agentResults]);
  const agentNames = useMemo(() => ["Group Analyst", "Tactical Scout", "Sentiment Reader", "Consensus"], []);

  // ── Agente que más acierta (mínimo 1 partido evaluado) ──────────────────
  const bestAgent = useMemo(() => {
    let best: { name: string; pct: number } | null = null;
    for (const name of agentNames) {
      const stats = agentStatsByAgent[name];
      if (!stats || stats.played === 0) continue;
      const pct = Math.round((stats.hits / stats.played) * 100);
      if (!best || pct > best.pct) best = { name, pct };
    }
    return best;
  }, [agentStatsByAgent, agentNames]);

  // ── Marcadores por partido, agrupados por fase (desplegables, la más reciente abierta) ──
  const agentRowsByPhase = useMemo(() => {
    const map: Record<string, AgentMatchResult[]> = {};
    for (const r of agentResults) {
      const k = phaseKeyOf(r);
      if (!map[k]) map[k] = [];
      map[k].push(r);
    }
    for (const rows of Object.values(map)) {
      rows.sort((a, b) => a.group.localeCompare(b.group) || a.team1.localeCompare(b.team1));
    }
    return map;
  }, [agentResults]);
  // Orden inverso al torneo: la fase más reciente primero.
  const agentPhaseSections = useMemo(
    () => [...phaseOrder].reverse().filter((p) => agentRowsByPhase[p.key]?.length),
    [phaseOrder, agentRowsByPhase]
  );
  // Fases del torneo con partidos ya jugados (el modelo ML cubre todas ellas).
  const playedPhaseKeys = useMemo(() => new Set(Object.keys(mlByPhase)), [mlByPhase]);

  if (played === 0) {
    return (
      <div className="max-w-3xl mx-auto text-center py-16">
        <p style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
          Aún no hay partidos jugados con resultados disponibles.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-5 max-w-5xl mx-auto">

      {/* Header */}
      <div>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1rem, 3vw, 1.4rem)", letterSpacing: "0.06em", color: "var(--color-ink)" }}>
          Rendimiento del modelo
        </h2>
        <p className="text-xs mt-1" style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", letterSpacing: "0.04em" }}>
          {played} partidos jugados · actualizado en tiempo real
        </p>
      </div>

      {/* KPIs globales */}
      <div className="grid grid-cols-3 gap-3">
        <Pill
          value={pctGlobal !== null ? `${pctGlobal}%` : "—"}
          label={`${hits}/${played} aciertos WC 2026`}
          color="var(--color-wc-gold)"
        />
        <Pill
          value="48%"
          label="Qatar 2022 · 64 partidos"
          color="var(--color-ink-muted)"
        />
        <Pill
          value="33%"
          label="azar sin modelo"
          color="rgba(255,255,255,0.25)"
        />
      </div>

      {/* Precisión por fase, de punta a punta del torneo: JOR 1/2/3 + eliminatorias */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <PhaseAccuracy
          title="📈 Precisión por fase · Modelo ML"
          phaseOrder={phaseOrder}
          byPhase={mlByPhase}
        />
        <AgentPhaseTable
          phaseOrder={phaseOrder}
          agentNames={agentNames}
          statsByPhase={agentStatsByPhase}
          playedPhaseKeys={playedPhaseKeys}
        />
      </div>

      {/* Detalle partido a partido por ronda de eliminatorias (colapsable) */}
      {roundFixtures.map(({ roundKey, label, fixtures }) => (
        <KnockoutRoundSection
          key={roundKey}
          roundKey={roundKey}
          label={label}
          fixtures={fixtures}
          allKnockoutResults={knockoutResults}
          teams={teams}
        />
      ))}

      {/* Desempeño por agente: 4 predicciones (3 agentes + consenso) */}
      {agentStatsByAgent && Object.keys(agentStatsByAgent).length > 0 && (
        <div className="rounded-xl p-5 space-y-4" style={{ ...cardBg, borderColor: "rgba(101,165,206,0.15)" }}>
          <div>
            <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
              🤖 Precisión por experto (1X2)
            </h3>
            <p className="text-[0.6rem] mt-1" style={{ color: "var(--color-ink-muted)" }}>
              Evaluación de las 4 predicciones: Group Analyst, Tactical Scout, Sentiment Reader, y Consenso
            </p>
          </div>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            {agentNames.map((agentName) => {
              const stats = agentStatsByAgent[agentName];
              if (!stats) return null;
              const pct = stats.played > 0 ? Math.round((stats.hits / stats.played) * 100) : null;
              const isBest = bestAgent?.name === agentName && stats.played > 0;
              const color = pct !== null && pct >= 50 ? "var(--color-wc-gold)" : "var(--color-ink-muted)";
              const emoji = agentName === "Group Analyst" ? "🔵" : agentName === "Tactical Scout" ? "🟠" : agentName === "Sentiment Reader" ? "🟡" : "🏆";
              return (
                <div
                  key={agentName}
                  className="relative rounded-lg p-3 space-y-2"
                  style={{
                    background: isBest ? "rgba(201,152,31,0.10)" : "rgba(255,255,255,0.03)",
                    border: isBest ? "1px solid rgba(201,152,31,0.5)" : "1px solid rgba(255,255,255,0.07)",
                  }}
                >
                  {isBest && (
                    <span
                      className="absolute -top-2 -right-1 text-[0.5rem] font-bold uppercase tracking-wide px-1.5 py-0.5 rounded-full"
                      style={{ background: "var(--color-wc-gold)", color: "#1a1410" }}
                    >
                      🔥 más certero
                    </span>
                  )}
                  <div className="text-xs font-bold whitespace-normal" style={{ color: "var(--color-ink)" }}>
                    {emoji} {agentName}
                  </div>
                  <div className="space-y-1.5">
                    <div className="flex items-baseline gap-2">
                      <div className="font-mono font-black text-base" style={{ color }}>
                        {pct !== null ? `${pct}%` : "—"}
                      </div>
                      <div className="text-[0.55rem]" style={{ color: "var(--color-ink-muted)" }}>
                        {stats.hits}/{stats.played}
                      </div>
                    </div>
                    <div className="rounded-full overflow-hidden" style={{ height: 3, background: "rgba(255,255,255,0.06)" }}>
                      <div
                        className="h-full rounded-full transition-all duration-700"
                        style={{ width: pct !== null ? `${pct}%` : "0%", background: color }}
                      />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>

          {/* Marcadores por partido, agrupados por fase (la más reciente abierta) */}
          {agentPhaseSections.length > 0 && (
            <div className="space-y-2 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <h4 className="text-xs font-bold" style={{ color: "var(--color-ink)" }}>
                🎯 Marcadores por partido
              </h4>
              {agentPhaseSections.map((phase, sectionIdx) => {
                const rows = agentRowsByPhase[phase.key];
                const consensusHits = rows.filter((r) => r.hits["Consensus"]).length;
                return (
                  <details
                    key={phase.key}
                    open={sectionIdx === 0}
                    className="rounded-lg"
                    style={{ background: "rgba(255,255,255,0.015)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <summary className="flex items-center justify-between gap-2 px-3 py-2 cursor-pointer select-none list-none [&::-webkit-details-marker]:hidden">
                      <span className="text-xs font-bold" style={{ color: "var(--color-ink)" }}>
                        {phase.label}
                        <span className="ml-2 text-[0.58rem] font-normal" style={{ color: "var(--color-ink-muted)" }}>▾</span>
                      </span>
                      <span className="font-mono text-[0.58rem]" style={{ color: "var(--color-ink-muted)" }}>
                        {rows.length} partido{rows.length === 1 ? "" : "s"} · consenso {consensusHits}/{rows.length}
                      </span>
                    </summary>
                    <div className="space-y-2 px-3 pb-3">
                      {rows.map((r) => (
                        <div
                          key={`${r.team1}|${r.team2}`}
                          className="rounded-lg p-3 space-y-1.5"
                          style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
                        >
                          <div className="flex items-center justify-between gap-2 flex-wrap">
                            <span className="text-[0.7rem] font-bold" style={{ color: "var(--color-ink)" }}>
                              {teams[r.team1]?.flag} {r.team1} {r.score1}–{r.score2} {r.team2} {teams[r.team2]?.flag}
                            </span>
                            {r.phase === "group" && (
                              <span className="font-mono text-[0.55rem]" style={{ color: "var(--color-ink-muted)" }}>
                                GRP {r.group}
                              </span>
                            )}
                          </div>
                          <div className="grid grid-cols-2 lg:grid-cols-4 gap-1.5">
                            {agentNames.map((agentName) => {
                              const g = r.goals[agentName];
                              const hit = r.hits[agentName];
                              if (!g) return null;
                              return (
                                <div
                                  key={agentName}
                                  className="flex items-center justify-between gap-1 rounded px-2 py-1"
                                  style={{
                                    background: hit ? "rgba(52,211,153,0.08)" : "rgba(207,10,44,0.08)",
                                    border: `1px solid ${hit ? "rgba(52,211,153,0.25)" : "rgba(207,10,44,0.2)"}`,
                                  }}
                                >
                                  <span className="text-[0.58rem] truncate" style={{ color: "var(--color-ink-muted)" }}>
                                    {AGENT_EMOJI[agentName] ?? "⚪"} {agentName}
                                  </span>
                                  <span
                                    className="font-mono text-[0.62rem] font-bold shrink-0"
                                    style={{ color: hit ? "#34d399" : "var(--color-wc-red)" }}
                                  >
                                    {hit ? "✅" : "❌"} {g.g1}-{g.g2}
                                  </span>
                                </div>
                              );
                            })}
                          </div>
                        </div>
                      ))}
                    </div>
                  </details>
                );
              })}
            </div>
          )}
        </div>
      )}

    </div>
  );
}
