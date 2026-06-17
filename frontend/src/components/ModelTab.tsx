"use client";

import { useMemo } from "react";
import type { GroupMatch, TeamInfo } from "@/types";
import type { ScoreMap } from "@/lib/live";
import { orientScore, modelVerdict } from "@/lib/live";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  teams: Record<string, TeamInfo>;
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

function pct(hits: number, played: number) {
  if (played === 0) return "—";
  return `${Math.round((hits / played) * 100)}%`;
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

  // ── Per group ──────────────────────────────────────────────────────────────
  const byGroup = useMemo(() => {
    const map: Record<string, Record<number, { hits: number; played: number }>> = {};
    for (const r of results) {
      if (!map[r.group]) map[r.group] = {};
      if (!map[r.group][r.groupMd]) map[r.group][r.groupMd] = { hits: 0, played: 0 };
      map[r.group][r.groupMd].played++;
      if (r.hit) map[r.group][r.groupMd].hits++;
    }
    return map;
  }, [results]);

  // ── Surprises (model was most wrong — lowest prob for actual outcome) ───────
  const surprises = useMemo(() => {
    // Sort by how wrong the model was: lowest prob on actual outcome
    return [...results]
      .filter((r) => !r.hit)
      .sort((a, b) => a.prob - b.prob)   // lowest predicted prob = biggest surprise
      .slice(0, 5);
  }, [results]);

  const groups = Object.keys(groupMatches).sort();

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
    <div className="space-y-5 max-w-3xl mx-auto">

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

      {/* Progresión por jornada interna */}
      <div className="rounded-xl p-5 space-y-3" style={cardBg}>
        <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
          📈 Precisión por jornada
        </h3>
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
      </div>

      {/* Por grupo */}
      <div className="rounded-xl p-5 space-y-3" style={cardBg}>
        <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
          🗂️ Por grupo · J1 → J2 → J3 → FG
        </h3>
        <p className="text-[0.6rem]" style={{ color: "var(--color-ink-muted)" }}>
          FG = total del grupo · flecha = mejora vs jornada anterior · FG delta vs J1
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {groups.map((g) => {
            const gData = byGroup[g];
            if (!gData) return null;

            // Totales del grupo para columna FG
            const totalHits   = Object.values(gData).reduce((s, d) => s + d.hits, 0);
            const totalPlayed = Object.values(gData).reduce((s, d) => s + d.played, 0);
            const fgPct  = totalPlayed > 0 ? Math.round((totalHits / totalPlayed) * 100) : null;
            const j1Pct  = gData[1] ? Math.round((gData[1].hits / gData[1].played) * 100) : null;
            const fgDelta = fgPct !== null && j1Pct !== null ? fgPct - j1Pct : null;

            return (
              <div key={g} className="rounded-lg p-3 space-y-2"
                style={{ background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.07)" }}>
                {/* Group header */}
                <span className="font-mono font-bold text-xs" style={{ color: "var(--color-wc-gold)" }}>
                  GRP {g}
                </span>
                {/* J1 | J2 | J3 | FG */}
                <div className="grid grid-cols-4 gap-1">
                  {[1, 2, 3].map((md) => {
                    const d   = gData[md];
                    const prev = gData[md - 1];
                    if (!d) return (
                      <div key={md} className="rounded text-center py-2"
                        style={{ background: "rgba(255,255,255,0.03)", fontSize: "0.56rem", color: "rgba(255,255,255,0.18)" }}>
                        <div>J{md}</div><div style={{ marginTop: 2 }}>—</div>
                      </div>
                    );
                    const p    = Math.round((d.hits / d.played) * 100);
                    const prevP = prev ? Math.round((prev.hits / prev.played) * 100) : null;
                    const delta = prevP !== null ? p - prevP : null;
                    const gold  = p >= 50;
                    return (
                      <div key={md} className="rounded text-center py-1.5"
                        style={{
                          background: gold ? "rgba(201,152,31,0.12)" : "rgba(207,10,44,0.1)",
                          border: `1px solid ${gold ? "rgba(201,152,31,0.2)" : "rgba(207,10,44,0.2)"}`,
                        }}>
                        <div style={{ fontSize: "0.56rem", color: "var(--color-ink-muted)" }}>J{md}</div>
                        <div style={{
                          fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "0.68rem",
                          color: gold ? "var(--color-wc-gold)" : "var(--color-wc-red)",
                        }}>
                          {p}%
                        </div>
                        {delta !== null ? (
                          <div style={{
                            fontSize: "0.5rem",
                            color: delta > 0 ? "#34d399" : delta < 0 ? "var(--color-wc-red)" : "var(--color-ink-muted)",
                          }}>
                            {delta > 0 ? `▲+${delta}` : delta < 0 ? `▼${delta}` : `=`}
                          </div>
                        ) : (
                          <div style={{ fontSize: "0.5rem", color: "transparent" }}>·</div>
                        )}
                      </div>
                    );
                  })}

                  {/* FG — total del grupo */}
                  {fgPct !== null ? (
                    <div className="rounded text-center py-1.5"
                      style={{
                        background: fgPct >= 50 ? "rgba(201,152,31,0.18)" : "rgba(207,10,44,0.14)",
                        border: `2px solid ${fgPct >= 50 ? "rgba(201,152,31,0.35)" : "rgba(207,10,44,0.3)"}`,
                      }}>
                      <div style={{ fontSize: "0.56rem", color: "var(--color-ink-muted)" }}>FG</div>
                      <div style={{
                        fontFamily: "var(--font-mono)", fontWeight: 800, fontSize: "0.7rem",
                        color: fgPct >= 50 ? "var(--color-wc-gold)" : "var(--color-wc-red)",
                      }}>
                        {fgPct}%
                      </div>
                      <div style={{ fontSize: "0.5rem", color: "var(--color-ink-muted)" }}>
                        {totalHits}/{totalPlayed}
                      </div>
                      {fgDelta !== null && (
                        <div style={{
                          fontSize: "0.48rem",
                          color: fgDelta > 0 ? "#34d399" : fgDelta < 0 ? "var(--color-wc-red)" : "var(--color-ink-muted)",
                        }}>
                          {fgDelta > 0 ? `▲+${fgDelta}pp` : fgDelta < 0 ? `▼${fgDelta}pp` : `=`}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="rounded text-center py-2"
                      style={{ background: "rgba(255,255,255,0.03)", fontSize: "0.56rem", color: "rgba(255,255,255,0.18)" }}>
                      <div>FG</div><div style={{ marginTop: 2 }}>—</div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Sorpresas */}
      {surprises.length > 0 && (
        <div className="rounded-xl p-5 space-y-3" style={{ ...cardBg, borderColor: "rgba(207,10,44,0.15)" }}>
          <h3 className="text-sm font-bold" style={{ color: "var(--color-wc-red)" }}>
            ⚡ Sorpresas del torneo
          </h3>
          <p className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>
            Partidos donde el modelo predijo con más confianza y erró
          </p>
          <div className="space-y-2">
            {surprises.map((r, i) => {
              const actualLabel = r.actual === "t1" ? r.team1 : r.actual === "t2" ? r.team2 : "Empate";
              const predictedLabel = r.predicted === "t1" ? r.team1 : r.predicted === "t2" ? r.team2 : "Empate";
              return (
                <div key={i} className="flex items-center gap-3 py-2"
                  style={{ borderBottom: i < surprises.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none" }}>
                  <span className="shrink-0 font-mono text-[0.62rem]" style={{ color: "var(--color-ink-muted)" }}>
                    {r.t1_flag}{r.team1} {r.score1}–{r.score2} {r.t2_flag}{r.team2}
                  </span>
                  <div className="flex-1" />
                  <div className="text-right">
                    <div className="text-[0.6rem]" style={{ color: "var(--color-ink-muted)" }}>
                      Predijo: <span style={{ color: "var(--color-wc-red)" }}>{predictedLabel}</span>
                    </div>
                    <div className="text-[0.6rem]" style={{ color: "var(--color-ink-muted)" }}>
                      Ganó: <span style={{ color: "var(--color-wc-gold)" }}>{actualLabel}</span>
                    </div>
                    <div className="font-mono text-[0.58rem]" style={{ color: "rgba(255,255,255,0.25)" }}>
                      confianza {Math.round(r.prob * 100)}%
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

    </div>
  );
}
