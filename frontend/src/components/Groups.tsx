"use client";

import { useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { GroupMatch, GroupStandingEntry } from "@/types";
import { useLang } from "@/lib/i18n";
import { modelRecord, modelVerdict, orientScore, type ScoreMap } from "@/lib/live";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  groupStandings: Record<string, GroupStandingEntry[]>;
  liveScores?: ScoreMap;
}

function fmt(n: number) { return `${(n * 100).toFixed(0)}%`; }

/* ── Narrador: tipo escenario basado en probabilidades ── */
function getScenario(standings: GroupStandingEntry[]): "death" | "dominant" | "twofav" | "balance" {
  const s = [...standings].sort((a, b) => b.first - a.first);
  if (!s[2]) return "balance";
  if (s[0].first > 0.52) return "dominant";
  if (s[2].first > 0.15 && s[0].first < 0.40) return "death";
  if (s[0].first > 0.35 && (s[1]?.first ?? 0) > 0.26 && (s[2].first ?? 0) < 0.17) return "twofav";
  return "balance";
}

function fill(template: string, teams: string[]) {
  return template.replace(/\{(\d)\}/g, (_, i) => teams[parseInt(i)] ?? "");
}

function GroupNarrator({ standings, groupName }: { standings: GroupStandingEntry[]; groupName: string }) {
  const T = useLang();
  const sorted = [...standings].sort((a, b) => b.first - a.first);
  const teamNames = sorted.map((s) => `${s.flag} ${s.team}`);
  const scenario = getScenario(standings);

  const templateMap = {
    death:    T.groupNarDeath,
    dominant: T.groupNarDominant,
    twofav:   T.groupNarTwoFav,
    balance:  T.groupNarBalance,
  };
  const text = fill(templateMap[scenario], teamNames);

  const scenarioTag: Record<typeof scenario, { label: string; color: string }> = {
    death:    { label: T.groupNarScenarioDeath,    color: "var(--wc-red)" },
    dominant: { label: T.groupNarScenarioDominant, color: "var(--wc-gold)" },
    twofav:   { label: T.groupNarScenarioTwoFav,   color: "#60a5fa" },
    balance:  { label: T.groupNarScenarioBalance,  color: "#a3e635" },
  };
  const tag = scenarioTag[scenario];

  return (
    <div style={{
      background: "linear-gradient(135deg, rgba(207,10,44,0.07) 0%, rgba(201,152,31,0.05) 100%)",
      border: "1px solid rgba(207,10,44,0.18)",
      borderRadius: 14,
      padding: "1rem 1.25rem",
      display: "flex", alignItems: "flex-start", gap: "0.9rem",
    }}>
      <span style={{ fontSize: "1.4rem", flexShrink: 0, marginTop: 2 }}>🎙️</span>
      <div style={{ minWidth: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.6rem", marginBottom: "0.45rem", flexWrap: "wrap" }}>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.5rem", letterSpacing: "0.2em",
            textTransform: "uppercase", color: "var(--text-muted)",
          }}>
            {T.groupNarTitle} · {T.group} {groupName}
          </span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.48rem", letterSpacing: "0.12em",
            textTransform: "uppercase", padding: "0.15rem 0.5rem", borderRadius: 4,
            background: `${tag.color}18`, border: `1px solid ${tag.color}40`,
            color: tag.color,
          }}>
            {tag.label}
          </span>
        </div>
        <p style={{
          fontFamily: "var(--font-body)", fontSize: "clamp(0.82rem, 1.4vw, 0.92rem)",
          lineHeight: 1.7, color: "var(--text)", margin: 0, fontStyle: "italic",
        }}>
          {text}
        </p>
      </div>
    </div>
  );
}

/* ── Tarjeta de partido ── */
function MatchCard({ match, liveScores }: { match: GroupMatch; liveScores?: ScoreMap }) {
  const T = useLang();
  const { team1, team2, team1_flag, team2_flag, t1_win, draw, t2_win, date, ground } = match;
  const d = new Date(date + "T12:00:00");
  const dateStr = d.toLocaleDateString("es-CO", { month: "short", day: "numeric" });
  const venue = ground.split("(")[0].trim();
  const maxP = Math.max(t1_win, t2_win);

  const score = orientScore(match, liveScores);
  const verdict = score ? modelVerdict(match, score) : null;
  const predictedLabel = verdict
    ? verdict.predicted === "t1" ? team1 : verdict.predicted === "t2" ? team2 : T.draw
    : "";

  return (
    <div className="stat-card p-4 text-left" style={score ? { borderColor: "rgba(212,168,67,0.35)" } : undefined}>
      <div className="flex justify-between items-center text-xs text-[var(--text-muted)] mb-3">
        <span className="uppercase tracking-wider">{dateStr}</span>
        {score
          ? <span className="final-tag">✓ {T.finalTag}</span>
          : <span className="text-right truncate max-w-[55%]">{venue}</span>}
      </div>

      <div className="flex items-center gap-2 mb-2.5">
        <span className={`flex-1 text-right text-sm font-bold ${t1_win === maxP ? "text-[var(--text)]" : "text-[var(--text-muted)]"}`}>
          {team1_flag} {team1}
        </span>
        {score
          ? <span className="score-final shrink-0 px-1">{score.s1}–{score.s2}</span>
          : <span className="text-xs text-[var(--text-muted)] shrink-0 px-1">vs</span>}
        <span className={`flex-1 text-sm font-bold ${t2_win === maxP ? "text-[var(--text)]" : "text-[var(--text-muted)]"}`}>
          {team2_flag} {team2}
        </span>
      </div>

      <div className="flex h-2.5 rounded-full overflow-hidden" style={score ? { opacity: 0.45 } : undefined}>
        <div style={{ width: `${t1_win * 100}%`, background: "#c8102e" }} />
        <div style={{ width: `${draw * 100}%`, background: "rgba(255,255,255,0.15)" }} />
        <div style={{ width: `${t2_win * 100}%`, background: "#003087" }} />
      </div>

      <div className="flex justify-between mt-1.5 text-xs font-bold tabular-nums" style={score ? { opacity: 0.6 } : undefined}>
        <span style={{ color: "#e85c74" }}>{fmt(t1_win)}</span>
        <span className="text-[var(--text-muted)]">{fmt(draw)} {T.drawAbbr}</span>
        <span style={{ color: "#6699ff" }}>{fmt(t2_win)}</span>
      </div>

      {verdict && (
        <div className="flex items-center gap-2 mt-2.5 pt-2 border-t border-[var(--border-subtle)]">
          <span className={`verdict-badge ${verdict.hit ? "verdict-hit" : "verdict-miss"}`}>
            {verdict.hit ? `✓ ${T.verdictHit}` : `✗ ${T.verdictMiss}`}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            {predictedLabel} · {fmt(verdict.prob)}
          </span>
        </div>
      )}
    </div>
  );
}

/* ── Tabla de posiciones ── */
function StandingsCard({ standings }: { standings: GroupStandingEntry[] }) {
  const T = useLang();
  const sorted = [...standings].sort((a, b) => b.first - a.first);
  return (
    <div className="stat-card text-left">
      <h4 className="font-bold text-sm mb-3 flex items-center gap-2">
        <span>{T.groupPredTitle}</span>
        <span className="text-[var(--text-muted)] font-normal text-xs">(5 000 sims)</span>
      </h4>
      <table>
        <thead>
          <tr>
            <th>{T.colTeam}</th>
            <th className="text-right">{T.firstPlace}</th>
            <th className="text-right">{T.secondPlace}</th>
            <th className="text-right">{T.thirdPlace}</th>
            <th className="text-right text-[#e55]">{T.eliminated}</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((row, i) => (
            <tr key={row.team} className={i < 2 ? "bg-green-500/5" : ""}>
              <td>
                <span className="flex items-center gap-2 text-sm">
                  <span
                    className="w-2 h-2 rounded-full shrink-0"
                    style={{
                      background: i === 0 ? "var(--wc-gold)" : i === 1 ? "#aaa" : i === 2 ? "#f59e0b55" : "#ef444440",
                    }}
                  />
                  {row.flag} {row.team}
                </span>
              </td>
              <td className="text-right font-bold" style={{ color: "var(--wc-red)" }}>{fmt(row.first)}</td>
              <td className="text-right text-[var(--text-muted)]">{fmt(row.second)}</td>
              <td className="text-right text-[var(--text-muted)]">{fmt(row.third)}</td>
              <td className="text-right" style={{ color: "#ef4444aa" }}>{fmt(row.fourth)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-[var(--text-muted)] mt-3 border-t border-[var(--border-subtle)] pt-2">
        {T.classifyNote}
      </p>
    </div>
  );
}

/* ── Componente principal ── */
export default function Groups({ groupMatches, groupStandings, liveScores }: Props) {
  const T = useLang();
  const groups = Object.keys(groupMatches).sort();
  const [selected, setSelected] = useState(groups.includes("K") ? "K" : groups[0] ?? "A");
  const [direction, setDirection] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);

  const matches = (groupMatches[selected] ?? [])
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
  const standings = groupStandings[selected] ?? [];

  const { played, hits } = modelRecord(groupMatches, liveScores ?? new Map());

  function handleSelectGroup(g: string) {
    const currentIdx = groups.indexOf(selected);
    const newIdx = groups.indexOf(g);
    setDirection(newIdx > currentIdx ? 1 : -1);
    setSelected(g);
  }

  function scrollCarousel(dir: -1 | 1) {
    scrollRef.current?.scrollBy({ left: dir * 160, behavior: "smooth" });
  }

  return (
    <div className="space-y-5">
      {/* Récord del modelo */}
      {played > 0 && (
        <div className="flex items-center gap-2 text-sm rounded-md px-3 py-2 stat-card !p-3">
          <span className="live-dot" />
          <span className="font-bold">{T.modelRecord}:</span>
          <span className="tabular-nums font-bold" style={{ color: "var(--wc-gold)" }}>
            {hits}/{played} ({played ? Math.round((hits / played) * 100) : 0}%)
          </span>
          <span className="text-xs text-[var(--text-muted)]">· {T.modelRecordNote}</span>
        </div>
      )}

      {/* ── Carrusel de grupos ── */}
      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
        {/* Flecha izquierda */}
        <button
          onClick={() => scrollCarousel(-1)}
          aria-label="Grupos anteriores"
          style={{
            flexShrink: 0, width: 34, height: 34,
            display: "flex", alignItems: "center", justifyContent: "center",
            borderRadius: "50%", border: "1px solid rgba(255,255,255,0.1)",
            background: "var(--surface-2)", color: "var(--text-muted)",
            cursor: "pointer", fontSize: "1.1rem", transition: "all 0.15s",
          }}
        >
          ‹
        </button>

        {/* Chips scrollables */}
        <div
          ref={scrollRef}
          style={{
            display: "flex", gap: "0.5rem",
            overflowX: "auto", scrollSnapType: "x mandatory",
            flex: 1, padding: "0.25rem 0",
          }}
          className="scrollbar-hide"
        >
          {groups.map((g) => {
            const flags = (groupStandings[g] ?? [])
              .sort((a, b) => b.first - a.first)
              .map((s) => s.flag)
              .slice(0, 4);
            const isActive = selected === g;
            return (
              <button
                key={g}
                onClick={() => handleSelectGroup(g)}
                style={{
                  flexShrink: 0, scrollSnapAlign: "start",
                  minWidth: 76, padding: "0.65rem 0.75rem",
                  borderRadius: 12, cursor: "pointer",
                  display: "flex", flexDirection: "column", alignItems: "center", gap: 4,
                  background: isActive
                    ? "var(--wc-red)"
                    : "var(--surface-2)",
                  border: isActive ? "1px solid transparent" : "1px solid rgba(255,255,255,0.07)",
                  boxShadow: isActive ? "0 4px 16px rgba(207,10,44,0.35)" : "none",
                  transition: "all 0.2s cubic-bezier(0.22,1,0.36,1)",
                  transform: isActive ? "scale(1.05)" : "scale(1)",
                }}
              >
                <span style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "1.25rem", lineHeight: 1, fontWeight: 900,
                  color: isActive ? "#fff" : "var(--text)",
                }}>
                  {g}
                </span>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: "0.42rem",
                  letterSpacing: "0.14em", textTransform: "uppercase",
                  color: isActive ? "rgba(255,255,255,0.7)" : "var(--text-muted)",
                }}>
                  {T.group}
                </span>
                {flags.length > 0 && (
                  <span style={{ fontSize: "0.6rem", letterSpacing: "0.04em" }}>
                    {flags.join("")}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {/* Flecha derecha */}
        <button
          onClick={() => scrollCarousel(1)}
          aria-label="Grupos siguientes"
          style={{
            flexShrink: 0, width: 34, height: 34,
            display: "flex", alignItems: "center", justifyContent: "center",
            borderRadius: "50%", border: "1px solid rgba(255,255,255,0.1)",
            background: "var(--surface-2)", color: "var(--text-muted)",
            cursor: "pointer", fontSize: "1.1rem", transition: "all 0.15s",
          }}
        >
          ›
        </button>
      </div>

      {/* ── Contenido del grupo con transición direccional ── */}
      <AnimatePresence mode="wait" custom={direction}>
        <motion.div
          key={selected}
          custom={direction}
          initial={{ opacity: 0, x: direction * 28 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -direction * 28 }}
          transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          className="space-y-4"
        >
          {/* Narrador */}
          {standings.length > 0 && (
            <GroupNarrator standings={standings} groupName={selected} />
          )}

          {/* Grid: posiciones + partidos */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-5 items-start">
            <StandingsCard standings={standings} />
            <div className="space-y-3">
              {matches.map((m) => (
                <MatchCard key={`${m.team1}|${m.team2}`} match={m} liveScores={liveScores} />
              ))}
            </div>
          </div>
        </motion.div>
      </AnimatePresence>

      <p className="text-xs text-center text-[var(--text-muted)]">
        {T.groupsXGBNote}
      </p>
    </div>
  );
}
