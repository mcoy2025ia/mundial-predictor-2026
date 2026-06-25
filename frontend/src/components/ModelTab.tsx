"use client";

import { useEffect, useMemo, useState } from "react";
import type { GroupMatch, TeamInfo } from "@/types";
import type { ScoreMap } from "@/lib/live";
import { orientScore, modelVerdict } from "@/lib/live";
import { computeAgentResults, computeAgentStatsByAgent, flattenAgentResults, type AgentDebateMatch, type AgentMatchResult } from "@/lib/agentDebate";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  teams: Record<string, TeamInfo>;
}

type MdMap = Record<number, { hits: number; played: number }>;

function buildByMd(results: { groupMd: number; hit: boolean }[]): MdMap {
  const map: MdMap = {};
  for (const r of results) {
    if (!map[r.groupMd]) map[r.groupMd] = { hits: 0, played: 0 };
    map[r.groupMd].played++;
    if (r.hit) map[r.groupMd].hits++;
  }
  return map;
}

interface MatchResult {
  group: string;
  groupMd: number;   // 1, 2 or 3 (internal group matchday)
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

const cardBg = { background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.06)" };

function Pill({ value, label, color }: { value: string; label: string; color: string }) {
  return (
    <div className="rounded-xl p-4 text-center" style={cardBg}>
      <div className="font-mono text-base font-black leading-tight" style={{ color }}>{value}</div>
      <div className="text-[0.6rem] mt-1 leading-snug" style={{ color: "var(--color-ink-muted)" }}>{label}</div>
    </div>
  );
}

/* ── Bloque reutilizable: precisión por jornada (ML o Agentes) ── */
function MatchdayAccuracy({ title, byMd }: { title: string; byMd: MdMap }) {
  const hasAny = [1, 2, 3].some((md) => byMd[md]);
  return (
    <div className="rounded-xl p-5 space-y-3" style={cardBg}>
      <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>{title}</h3>
      {!hasAny ? (
        <p className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
          Sin partidos evaluados todavía.
        </p>
      ) : (
        <div className="space-y-2">
          {[1, 2, 3].map((md) => {
            const data = byMd[md];
            if (!data) return null;
            const p = Math.round((data.hits / data.played) * 100);
            const prev = byMd[md - 1];
            const delta = prev ? p - Math.round((prev.hits / prev.played) * 100) : null;
            return (
              <div key={md} className="flex items-center gap-3">
                <span className="shrink-0 font-mono text-[0.65rem]" style={{ color: "var(--color-ink-muted)", width: 40 }}>
                  JOR {md}
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

function Arrow({ delta }: { delta: number | null }) {
  if (delta === null) return <span style={{ color: "var(--color-ink-muted)", fontSize: "0.7rem" }}>—</span>;
  if (delta > 0)  return <span style={{ color: "#34d399", fontSize: "0.7rem" }}>▲ +{delta}pp</span>;
  if (delta < 0)  return <span style={{ color: "var(--color-wc-red)", fontSize: "0.7rem" }}>▼ {delta}pp</span>;
  return <span style={{ color: "var(--color-ink-muted)", fontSize: "0.7rem" }}>= 0pp</span>;
}

export default function ModelTab({ groupMatches, liveScores, teams }: Props) {
  const results = useMemo(
    () => computeResults(groupMatches, liveScores, teams),
    [groupMatches, liveScores, teams]
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

  const agentResults: AgentMatchResult[] = useMemo(
    () => computeAgentResults(groupMatches, liveScores, agentDebateResults),
    [groupMatches, liveScores, agentDebateResults]
  );
  const agentByMd = useMemo(() => buildByMd(flattenAgentResults(agentResults)), [agentResults]);

  // ── Desempeño por agente individual ─────────────────────────────────────
  const agentStatsByAgent = useMemo(() => computeAgentStatsByAgent(agentResults), [agentResults]);
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

  // ── Marcadores por partido: qué predijo cada agente, partido por partido ──
  const agentMatchRows = useMemo(
    () => [...agentResults].sort((a, b) => b.groupMd - a.groupMd || a.group.localeCompare(b.group)),
    [agentResults]
  );

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

      {/* Progresión por jornada: Modelo ML vs Agentes */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <MatchdayAccuracy title="📈 Precisión por jornada · Modelo ML" byMd={byMd} />
        <MatchdayAccuracy title="🤖 Precisión por jornada · Agentes" byMd={agentByMd} />
      </div>

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

          {/* Marcadores por partido: qué predijo cada agente vs el resultado real */}
          {agentMatchRows.length > 0 && (
            <div className="space-y-2 pt-2" style={{ borderTop: "1px solid rgba(255,255,255,0.06)" }}>
              <h4 className="text-xs font-bold" style={{ color: "var(--color-ink)" }}>
                🎯 Marcadores por partido
              </h4>
              <div className="space-y-2">
                {agentMatchRows.map((r) => (
                  <div
                    key={`${r.team1}|${r.team2}`}
                    className="rounded-lg p-3 space-y-1.5"
                    style={{ background: "rgba(255,255,255,0.025)", border: "1px solid rgba(255,255,255,0.06)" }}
                  >
                    <div className="flex items-center justify-between gap-2 flex-wrap">
                      <span className="text-[0.7rem] font-bold" style={{ color: "var(--color-ink)" }}>
                        {teams[r.team1]?.flag} {r.team1} {r.score1}–{r.score2} {r.team2} {teams[r.team2]?.flag}
                      </span>
                      <span className="font-mono text-[0.55rem]" style={{ color: "var(--color-ink-muted)" }}>
                        GRP {r.group} · J{r.groupMd}
                      </span>
                    </div>
                    <div className="grid grid-cols-2 lg:grid-cols-4 gap-1.5">
                      {agentNames.map((agentName) => {
                        const g = r.goals[agentName];
                        const hit = r.hits[agentName];
                        if (!g) return null;
                        const emoji = agentName === "Group Analyst" ? "🔵" : agentName === "Tactical Scout" ? "🟠" : agentName === "Sentiment Reader" ? "🟡" : "🏆";
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
                              {emoji} {agentName}
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
            </div>
          )}
        </div>
      )}

    </div>
  );
}
