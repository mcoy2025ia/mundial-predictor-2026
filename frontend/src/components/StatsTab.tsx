"use client";

import { useMemo } from "react";
import type { TeamInfo, GroupMatch, LiveMatch } from "@/types";
import type { ScoreMap } from "@/lib/live";
import { orientScore, modelVerdict } from "@/lib/live";

interface Props {
  liveMatches: LiveMatch[];
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  teams: Record<string, TeamInfo>;
}

const cardBg = { background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.06)" };

function Kpi({ value, label, color = "var(--color-wc-gold)" }: {
  value: string; label: string; color?: string;
}) {
  return (
    <div className="rounded-xl p-4 text-center flex-1" style={{ ...cardBg, minWidth: 80 }}>
      <div className="font-mono font-black leading-tight" style={{ fontSize: "clamp(1.1rem,3vw,1.5rem)", color }}>
        {value}
      </div>
      <div className="text-[0.58rem] mt-1 leading-snug" style={{ color: "var(--color-ink-muted)" }}>
        {label}
      </div>
    </div>
  );
}

export default function StatsTab({ liveMatches, groupMatches, liveScores, teams }: Props) {
  // Partidos terminados (cualquier fase)
  const finished = useMemo(
    () => liveMatches.filter((m) => m.score1 !== null && m.score2 !== null),
    [liveMatches]
  );

  // KPIs globales
  const kpis = useMemo(() => {
    const goals = finished.reduce((s, m) => s + m.score1! + m.score2!, 0);
    const zeroes = finished.filter((m) => m.score1 === 0 && m.score2 === 0).length;
    return {
      played: finished.length,
      goals,
      avg: finished.length ? goals / finished.length : 0,
      zeroes,
    };
  }, [finished]);

  // Goles por equipo
  const teamGoals = useMemo(() => {
    const map: Record<string, { gf: number; ga: number; played: number }> = {};
    for (const m of finished) {
      map[m.team1] = map[m.team1] ?? { gf: 0, ga: 0, played: 0 };
      map[m.team2] = map[m.team2] ?? { gf: 0, ga: 0, played: 0 };
      map[m.team1].gf += m.score1!;
      map[m.team1].ga += m.score2!;
      map[m.team1].played++;
      map[m.team2].gf += m.score2!;
      map[m.team2].ga += m.score1!;
      map[m.team2].played++;
    }
    return Object.entries(map)
      .map(([team, s]) => ({ team, ...s }))
      .sort((a, b) => b.gf - a.gf || a.ga - b.ga)
      .slice(0, 10);
  }, [finished]);

  // Partidos más goleadores
  const topMatches = useMemo(() => {
    return finished
      .map((m) => ({ m, total: m.score1! + m.score2! }))
      .sort((a, b) => b.total - a.total || b.m.score1! - a.m.score1!)
      .slice(0, 5);
  }, [finished]);

  // Marcadores más frecuentes (solo fase de grupos)
  const scoreDist = useMemo(() => {
    const map: Record<string, number> = {};
    for (const m of finished) {
      if (!m.group?.startsWith("Group")) continue;
      const key = `${m.score1}-${m.score2}`;
      map[key] = (map[key] ?? 0) + 1;
    }
    return Object.entries(map).sort((a, b) => b[1] - a[1]).slice(0, 8);
  }, [finished]);

  // Sorpresas (modelo erró, ganó el menos favorito según prob)
  const upsets = useMemo(() => {
    const results: Array<{
      team1: string; team2: string; s1: number; s2: number;
      t1_flag: string; t2_flag: string;
      actualProb: number; group: string;
    }> = [];
    for (const [group, matches] of Object.entries(groupMatches)) {
      for (const m of matches) {
        const score = orientScore(m, liveScores);
        if (!score) continue;
        const v = modelVerdict(m, score);
        if (v.hit) continue;
        const actualProb =
          score.s1 > score.s2 ? m.t1_win :
          score.s1 < score.s2 ? m.t2_win :
          m.draw;
        results.push({
          team1: m.team1, team2: m.team2,
          s1: score.s1, s2: score.s2,
          t1_flag: m.team1_flag, t2_flag: m.team2_flag,
          actualProb, group,
        });
      }
    }
    return results.sort((a, b) => a.actualProb - b.actualProb).slice(0, 5);
  }, [groupMatches, liveScores]);

  if (finished.length === 0) {
    return (
      <div className="max-w-3xl mx-auto text-center py-16">
        <p style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", fontSize: "0.8rem" }}>
          Aún no hay partidos terminados con resultados disponibles.
        </p>
      </div>
    );
  }

  const maxGf = teamGoals[0]?.gf || 1;

  return (
    <div className="space-y-5 max-w-3xl mx-auto">

      {/* Header */}
      <div>
        <h2 style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(1rem, 3vw, 1.4rem)",
          letterSpacing: "0.06em",
          color: "var(--color-ink)",
        }}>
          Estadísticas WC 2026
        </h2>
        <p className="text-xs mt-1" style={{
          color: "var(--color-ink-muted)",
          fontFamily: "var(--font-mono)",
          letterSpacing: "0.04em",
        }}>
          {kpis.played} partidos jugados · datos en tiempo real
        </p>
      </div>

      {/* KPIs */}
      <div className="flex gap-3 flex-wrap">
        <Kpi value={String(kpis.goals)} label="goles en el torneo" />
        <Kpi value={kpis.avg.toFixed(2)} label="goles por partido" color="var(--color-wc-red)" />
        <Kpi value={String(kpis.played)} label="partidos jugados" color="rgba(255,255,255,0.6)" />
        <Kpi value={String(kpis.zeroes)} label="sin goles (0-0)" color="var(--color-ink-muted)" />
      </div>

      {/* Equipos más goleadores */}
      {teamGoals.length > 0 && (
        <div className="rounded-xl p-5 space-y-3" style={cardBg}>
          <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
            ⚽ Equipos más goleadores
          </h3>
          <div className="space-y-2">
            {teamGoals.map((t, i) => {
              const flag = teams[t.team]?.flag ?? "";
              const barPct = Math.round((t.gf / maxGf) * 100);
              const isTop3 = i < 3;
              return (
                <div key={t.team} className="flex items-center gap-3">
                  <span className="shrink-0 font-mono text-[0.62rem]" style={{
                    color: isTop3 ? "var(--color-wc-gold)" : "var(--color-ink-muted)",
                    width: 14, textAlign: "right",
                  }}>
                    {i + 1}
                  </span>
                  <span className="shrink-0">{flag}</span>
                  <span className="shrink-0 font-mono text-[0.63rem]" style={{
                    color: "var(--color-ink)",
                    width: 110,
                    overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                  }}>
                    {t.team}
                  </span>
                  <div className="flex-1 rounded-full overflow-hidden" style={{
                    height: 5,
                    background: "rgba(255,255,255,0.06)",
                  }}>
                    <div className="h-full rounded-full transition-all duration-700" style={{
                      width: `${barPct}%`,
                      background: isTop3 ? "var(--color-wc-gold)" : "rgba(201,152,31,0.4)",
                    }} />
                  </div>
                  <span className="shrink-0 font-mono font-bold text-xs" style={{
                    color: "var(--color-wc-gold)", width: 18, textAlign: "right",
                  }}>
                    {t.gf}
                  </span>
                  <span className="shrink-0 text-[0.56rem]" style={{
                    color: "var(--color-ink-muted)", width: 38, textAlign: "right",
                  }}>
                    -{t.ga} GA
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Partidos más goleadores */}
      {topMatches.length > 0 && (
        <div className="rounded-xl p-5 space-y-2" style={cardBg}>
          <h3 className="text-sm font-bold mb-3" style={{ color: "var(--color-ink)" }}>
            🔥 Partidos más goleadores
          </h3>
          {topMatches.map(({ m, total }, i) => {
            const f1 = teams[m.team1]?.flag ?? "";
            const f2 = teams[m.team2]?.flag ?? "";
            return (
              <div key={i} className="flex items-center gap-3 py-1.5" style={{
                borderBottom: i < topMatches.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}>
                <span className="shrink-0 font-mono font-bold text-xs" style={{
                  color: "var(--color-wc-gold)", width: 22, textAlign: "center",
                  background: "rgba(201,152,31,0.12)", borderRadius: 4, padding: "1px 2px",
                }}>
                  {total}
                </span>
                <span className="flex-1 font-mono text-[0.65rem]" style={{ color: "var(--color-ink)" }}>
                  {f1} {m.team1}{" "}
                  <strong style={{ color: "var(--color-wc-gold)" }}>
                    {m.score1}–{m.score2}
                  </strong>{" "}
                  {m.team2} {f2}
                </span>
                <span className="shrink-0 text-[0.56rem]" style={{ color: "var(--color-ink-muted)" }}>
                  {m.group ?? m.round ?? ""}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Marcadores más frecuentes */}
      {scoreDist.length > 0 && (
        <div className="rounded-xl p-5 space-y-3" style={cardBg}>
          <h3 className="text-sm font-bold" style={{ color: "var(--color-ink)" }}>
            📊 Marcadores más frecuentes
          </h3>
          <div className="flex flex-wrap gap-2">
            {scoreDist.map(([score, count], i) => (
              <div key={score} className="rounded-lg px-3 py-2 text-center" style={{
                background: i === 0 ? "rgba(201,152,31,0.12)" : "rgba(255,255,255,0.04)",
                border: `1px solid ${i === 0 ? "rgba(201,152,31,0.25)" : "rgba(255,255,255,0.07)"}`,
                minWidth: 68,
              }}>
                <div className="font-mono font-bold" style={{
                  fontSize: "1rem",
                  color: i === 0 ? "var(--color-wc-gold)" : "var(--color-ink)",
                }}>
                  {score}
                </div>
                <div className="text-[0.58rem] mt-0.5" style={{ color: "var(--color-ink-muted)" }}>
                  {count} {count === 1 ? "vez" : "veces"}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sorpresas */}
      {upsets.length > 0 && (
        <div className="rounded-xl p-5 space-y-3" style={{
          ...cardBg, borderColor: "rgba(207,10,44,0.2)",
        }}>
          <h3 className="text-sm font-bold" style={{ color: "var(--color-wc-red)" }}>
            ⚡ Mayores sorpresas
          </h3>
          <p className="text-[0.63rem]" style={{ color: "var(--color-ink-muted)" }}>
            Resultados que el modelo no vio venir — prob. asignada al ganador real
          </p>
          <div className="space-y-2">
            {upsets.map((u, i) => (
              <div key={i} className="flex items-center gap-3 py-1.5" style={{
                borderBottom: i < upsets.length - 1 ? "1px solid rgba(255,255,255,0.04)" : "none",
              }}>
                <span className="flex-1 font-mono text-[0.63rem]" style={{ color: "var(--color-ink)" }}>
                  {u.t1_flag} {u.team1}{" "}
                  <strong style={{ color: "var(--color-wc-gold)" }}>
                    {u.s1}–{u.s2}
                  </strong>{" "}
                  {u.team2} {u.t2_flag}
                </span>
                <span className="shrink-0 text-[0.58rem]" style={{ color: "var(--color-ink-muted)" }}>
                  {u.group}
                </span>
                <span className="shrink-0 font-mono text-[0.6rem] font-bold" style={{
                  color: "var(--color-wc-red)",
                  background: "rgba(207,10,44,0.1)",
                  border: "1px solid rgba(207,10,44,0.2)",
                  borderRadius: 4, padding: "2px 5px",
                }}>
                  {Math.round(u.actualProb * 100)}%
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

    </div>
  );
}
