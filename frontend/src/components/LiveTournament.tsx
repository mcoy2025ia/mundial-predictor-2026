"use client";

import { useMemo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { TeamInfo, Prediction, LiveMatch } from "@/types";
import type { LiveStats, MatchVerdict } from "@/lib/live";
import { computeGroupStandings } from "@/lib/live";
import { staggerContainer, fadeUp } from "@/lib/animations";
import { useLang } from "@/lib/i18n";

interface Props {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  groups: Record<string, string[]>;
  liveMatches: LiveMatch[];
  stats: LiveStats;
  verdicts: MatchVerdict[];
  groupNarratives?: Record<string, string>;
}

type LiveSection = "resultados" | "posiciones" | "proximos";

const MVR_PREVIEW = 6;

function fmtPct(n: number) { return `${(n * 100).toFixed(0)}%`; }

export default function LiveTournament({
  teams, predictions, groups, liveMatches, stats, verdicts, groupNarratives,
}: Props) {
  const T = useLang();
  const [section, setSection] = useState<LiveSection>("resultados");
  const [sectionDir, setSectionDir] = useState(0);
  const [showAll, setShowAll] = useState(false);
  const flag = (name: string) => teams[name]?.flag ?? "";

  const SECTIONS: { id: LiveSection; label: string }[] = [
    { id: "resultados", label: T.lt_secResults },
    { id: "posiciones", label: T.lt_secStandings },
    { id: "proximos",   label: T.lt_secUpcoming },
  ];

  function switchSection(s: LiveSection) {
    const currentIdx = SECTIONS.findIndex((x) => x.id === section);
    const newIdx = SECTIONS.findIndex((x) => x.id === s);
    setSectionDir(newIdx > currentIdx ? 1 : -1);
    setSection(s);
  }

  const ROUND_LABEL: Record<string, string> = {
    LAST_32: T.roundOf32, LAST_16: T.roundOf16,
    QUARTER_FINALS: T.quarterFinal, SEMI_FINALS: T.semiFinal,
    THIRD_PLACE: "3°", FINAL: T.final,
  };
  const stageLabel = (m: LiveMatch) =>
    m.group?.startsWith("Group")
      ? `${T.group} ${m.group.slice(6)}`
      : (m.round ? (ROUND_LABEL[m.round] ?? m.round) : "");

  const inPlay = useMemo(
    () => liveMatches.filter((m) => m.status === "IN_PLAY" || m.status === "PAUSED"),
    [liveMatches]
  );

  const recent = useMemo(
    () => [...verdicts].sort((a, b) => (b.m.date ?? "").localeCompare(a.m.date ?? "")),
    [verdicts]
  );
  const visible = showAll ? recent : recent.slice(0, MVR_PREVIEW);
  const hits = verdicts.filter((v) => v.hit).length;
  const pct = verdicts.length ? Math.round((hits / verdicts.length) * 100) : 0;

  const standings = useMemo(() => {
    const all = computeGroupStandings(liveMatches, groups);
    return Object.entries(all)
      .filter(([, rows]) => rows.some((r) => r.played > 0))
      .sort(([a], [b]) => a.localeCompare(b));
  }, [liveMatches, groups]);

  const today = new Date().toLocaleDateString("en-CA");
  const bogotaToday = todayBogota();
  const dailyGroupNarratives = useMemo(
    () => selectDailyGroupNarratives(groupNarratives, bogotaToday),
    [groupNarratives, bogotaToday]
  );
  const upcoming = useMemo(() => {
    const pending = liveMatches.filter(
      (m) =>
        m.score1 === null && m.status !== "IN_PLAY" && m.status !== "PAUSED" &&
        m.date && m.date >= today && teams[m.team1] && teams[m.team2]
    );
    const dates = [...new Set(pending.map((m) => m.date!))].sort().slice(0, 2);
    return dates.map((d) => ({ date: d, fixtures: pending.filter((m) => m.date === d) }));
  }, [liveMatches, teams, today]);

  function forecast(m: LiveMatch): { label: string; prob: number } | null {
    const direct = predictions[`${m.team1}|${m.team2}`];
    const reverse = predictions[`${m.team2}|${m.team1}`];
    const probs = direct
      ? { t1: direct.home_win, draw: direct.draw, t2: direct.away_win }
      : reverse
        ? { t1: reverse.away_win, draw: reverse.draw, t2: reverse.home_win }
        : null;
    if (!probs) return null;
    const [k, p] = Object.entries(probs).sort((a, b) => b[1] - a[1])[0];
    return { label: k === "t1" ? m.team1 : k === "t2" ? m.team2 : T.draw, prob: p };
  }

  const fmtDate = (d: string) =>
    new Date(d + "T12:00:00").toLocaleDateString(T.locale, {
      weekday: "short", day: "numeric", month: "short",
    });
  const fmtTime = (utc?: string) =>
    utc ? new Date(utc).toLocaleTimeString(T.locale, { hour: "2-digit", minute: "2-digit" }) : "";

  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="visible" className="space-y-5">

      {/* ── KPIs siempre visibles ── */}
      <motion.div variants={fadeUp} className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 sm:gap-3">
        <Kpi label={T.lt_played}   value={String(stats.played)} />
        <Kpi label={T.lt_goals}    value={String(stats.goals)} />
        <Kpi label={T.lt_avgGoals} value={stats.played ? stats.avg.toFixed(2) : "—"} />
        <Kpi
          label={T.modelRecord}
          value={verdicts.length ? `${pct}%` : "—"}
          sub={verdicts.length ? `${hits}/${verdicts.length}` : undefined}
          gold
        />
      </motion.div>

      {/* ── En juego ahora (siempre visible si hay partidos) ── */}
      {inPlay.length > 0 && (
        <motion.section variants={fadeUp} className="space-y-3">
          <SectionTitle dot title={T.lt_inPlay} />
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {inPlay.map((m) => (
              <div
                key={`${m.team1}|${m.team2}`}
                className="stat-card !p-4 text-center"
                style={{ borderColor: "rgba(207,10,44,0.45)" }}
              >
                <div className="flex items-center justify-center gap-2 mb-2.5">
                  <span className="live-dot" />
                  <span
                    className="text-[10px] uppercase tracking-[0.18em]"
                    style={{ fontFamily: "var(--font-mono)", color: "var(--wc-red)" }}
                  >
                    {stageLabel(m)}
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="flex-1 min-w-0 text-right text-sm font-bold truncate">
                    {flag(m.team1)} {m.team1}
                  </span>
                  <span className="text-xs shrink-0 px-1" style={{ color: "var(--text-muted)" }}>vs</span>
                  <span className="flex-1 min-w-0 text-left text-sm font-bold truncate">
                    {m.team2} {flag(m.team2)}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </motion.section>
      )}

      {/* ── Sub-navegación ── */}
      {dailyGroupNarratives.length > 0 && (
        <motion.section variants={fadeUp} className="space-y-3">
          <SectionTitle title="Previas de grupos" note="GroupNarrative-Preview" />
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {dailyGroupNarratives.map(({ group, text }) => (
              <div key={group} className="stat-card !p-4 text-left">
                <p
                  className="text-[10px] uppercase tracking-[0.18em] mb-2"
                  style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}
                >
                  Grupo {group}
                </p>
                <div
                  className="text-sm"
                  style={{ color: "var(--text)", lineHeight: 1.65, whiteSpace: "pre-line" }}
                >
                  {compactNarrative(text)}
                </div>
              </div>
            ))}
          </div>
        </motion.section>
      )}

      <motion.div variants={fadeUp}>
        <div style={{
          display: "flex", gap: 4,
          background: "var(--surface-2)",
          borderRadius: 12, padding: 4,
          width: "fit-content",
        }}>
          {SECTIONS.map(({ id, label }) => (
            <button
              key={id}
              onClick={() => switchSection(id)}
              style={{
                padding: "0.45rem 1.1rem", borderRadius: 9, cursor: "pointer",
                fontFamily: "var(--font-mono)", fontSize: "0.6rem",
                letterSpacing: "0.1em", textTransform: "uppercase",
                fontWeight: 700, transition: "all 0.18s",
                background: section === id ? "var(--wc-red)" : "transparent",
                color: section === id ? "#fff" : "var(--text-muted)",
                border: "none",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </motion.div>

      {/* ── Contenido de la sección activa con transición ── */}
      <AnimatePresence mode="wait" custom={sectionDir}>
        <motion.div
          key={section}
          custom={sectionDir}
          initial={{ opacity: 0, x: sectionDir * 32 }}
          animate={{ opacity: 1, x: 0 }}
          exit={{ opacity: 0, x: -sectionDir * 32 }}
          transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        >
          {/* RESULTADOS: Modelo vs Realidad */}
          {section === "resultados" && (
            <div className="space-y-3">
              <SectionTitle title={T.lt_mvrTitle} note={T.lt_mvrNote} />

              {recent.length === 0 ? (
                <div className="stat-card !p-5 flex items-center gap-3">
                  <span className="live-dot shrink-0" />
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>{T.lt_empty}</p>
                </div>
              ) : (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                    {visible.map((v) => {
                      const { m } = v;
                      const pickLabel =
                        v.predicted === "t1" ? m.team1 : v.predicted === "t2" ? m.team2 : T.draw;
                      return (
                        <div key={`${m.team1}|${m.team2}|${m.date}`} className="stat-card !p-4 text-left">
                          <div className="flex items-center justify-between gap-2 mb-3">
                            <span
                              className="text-[10px] uppercase tracking-wider truncate"
                              style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}
                            >
                              {m.date ? fmtDate(m.date) : ""} · {stageLabel(m)}
                            </span>
                            <span className={`verdict-badge ${v.hit ? "verdict-hit" : "verdict-miss"}`}>
                              {v.hit ? `✓ ${T.verdictHit}` : `✗ ${T.verdictMiss}`}
                            </span>
                          </div>

                          <div className="flex items-center gap-2 mb-3">
                            <span className="flex-1 min-w-0 text-right text-sm font-bold truncate">
                              {flag(m.team1)} {m.team1}
                            </span>
                            <span className="score-final shrink-0 px-1">{m.score1}–{m.score2}</span>
                            <span className="flex-1 min-w-0 text-sm font-bold truncate">
                              {m.team2} {flag(m.team2)}
                            </span>
                          </div>

                          <div className="flex h-2 rounded-full overflow-hidden mb-1.5">
                            <div style={{ width: `${v.probs.t1 * 100}%`, background: "#c8102e" }} />
                            <div style={{ width: `${v.probs.draw * 100}%`, background: "rgba(255,255,255,0.15)" }} />
                            <div style={{ width: `${v.probs.t2 * 100}%`, background: "#003087" }} />
                          </div>
                          <p className="text-xs tabular-nums" style={{ color: "var(--text-muted)" }}>
                            {T.lt_forecast}: <span className="font-bold" style={{ color: "var(--text)" }}>{pickLabel}</span> · {fmtPct(v.prob)}
                          </p>
                        </div>
                      );
                    })}
                  </div>

                  {recent.length > MVR_PREVIEW && (
                    <div className="text-center">
                      <button
                        onClick={() => setShowAll(!showAll)}
                        className="text-xs px-4 py-2 rounded-lg font-semibold transition-all bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
                      >
                        {showAll ? T.backtestLess : `${T.backtestMore} (${recent.length})`}
                      </button>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* POSICIONES: Grupos oficiales */}
          {section === "posiciones" && (
            <div className="space-y-3">
              <SectionTitle title={T.lt_standings} note={T.lt_standingsNote} />

              {standings.length === 0 ? (
                <div className="stat-card !p-5 flex items-center gap-3">
                  <span className="live-dot shrink-0" />
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>{T.lt_empty}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {standings.map(([g, rows]) => (
                    <div key={g} className="stat-card !p-4 text-left">
                      <div className="grid grid-cols-[1fr_1.8rem_2.4rem_1.9rem] gap-x-1.5 items-baseline mb-2 pb-2 border-b border-[var(--border-subtle)]">
                        <span className="text-xs font-black" style={{ color: "var(--wc-red)" }}>
                          {T.group} {g}
                        </span>
                        {[T.lt_playedHead, T.lt_gdHead, T.lt_ptsHead].map((h) => (
                          <span
                            key={h}
                            className="text-[9px] uppercase tracking-wider text-right"
                            style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}
                          >
                            {h}
                          </span>
                        ))}
                      </div>
                      <div className="space-y-1.5">
                        {rows.map((r, i) => (
                          <div
                            key={r.team}
                            className="grid grid-cols-[1fr_1.8rem_2.4rem_1.9rem] gap-x-1.5 items-center text-xs"
                          >
                            <span className="flex items-center gap-1.5 min-w-0">
                              <span
                                className="w-2 h-2 rounded-full shrink-0"
                                style={{
                                  background:
                                    i < 2 ? "#22c55e" : i === 2 ? "#f59e0b88" : "rgba(255,255,255,0.10)",
                                }}
                              />
                              <span className="truncate">{flag(r.team)} {r.team}</span>
                            </span>
                            <span className="tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                              {r.played}
                            </span>
                            <span className="tabular-nums text-right" style={{ color: "var(--text-muted)" }}>
                              {r.gd > 0 ? `+${r.gd}` : r.gd}
                            </span>
                            <span className="tabular-nums font-bold text-right" style={{ color: "var(--wc-gold)" }}>
                              {r.points}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* PRÓXIMOS: Siguientes partidos */}
          {section === "proximos" && (
            <div className="space-y-3">
              <SectionTitle title={T.lt_upcoming} />

              {upcoming.length === 0 ? (
                <div className="stat-card !p-5 flex items-center gap-3">
                  <span className="live-dot shrink-0" />
                  <p className="text-sm" style={{ color: "var(--text-muted)" }}>{T.lt_empty}</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 items-start">
                  {upcoming.map(({ date, fixtures }) => (
                    <div key={date} className="stat-card !p-4 text-left">
                      <p
                        className="text-[10px] uppercase tracking-[0.18em] mb-1"
                        style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}
                      >
                        {fmtDate(date)}
                      </p>
                      <div className="divide-y divide-[var(--border-subtle)]">
                        {fixtures.map((m) => {
                          const f = forecast(m);
                          return (
                            <div key={`${m.team1}|${m.team2}`} className="py-2.5">
                              <div className="flex items-center gap-2">
                                <span
                                  className="text-[10px] tabular-nums w-11 shrink-0"
                                  style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}
                                >
                                  {fmtTime(m.utc)}
                                </span>
                                <span className="flex-1 min-w-0 text-right text-sm truncate">
                                  {flag(m.team1)} {m.team1}
                                </span>
                                <span className="text-[10px] shrink-0 px-0.5" style={{ color: "var(--text-muted)" }}>
                                  vs
                                </span>
                                <span className="flex-1 min-w-0 text-sm truncate">
                                  {m.team2} {flag(m.team2)}
                                </span>
                              </div>
                              {f && (
                                <div className="flex justify-end mt-1.5 pl-11">
                                  <span
                                    className="text-[10px] px-2 py-0.5 rounded-full tabular-nums"
                                    style={{
                                      fontFamily: "var(--font-mono)",
                                      background: "rgba(212,168,67,0.10)",
                                      border: "1px solid rgba(212,168,67,0.30)",
                                      color: "var(--wc-gold)",
                                    }}
                                  >
                                    {T.lt_forecast}: {f.label} {fmtPct(f.prob)}
                                  </span>
                                </div>
                              )}
                            </div>
                          );
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </motion.div>
      </AnimatePresence>

      <motion.p
        variants={fadeUp}
        className="text-center text-xs"
        style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}
      >
        {T.lt_source}
      </motion.p>
    </motion.div>
  );
}

/* ── Piezas ─────────────────────────────────────────── */
function todayBogota() {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/Bogota",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const get = (type: string) => parts.find((part) => part.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

function selectDailyGroupNarratives(groupNarratives: Record<string, string> | undefined, today: string) {
  if (!groupNarratives) return [];
  const entries = Object.entries(groupNarratives)
    .map(([key, text]) => {
      const [group, date, lang] = key.split("|");
      return { group, date, lang, text };
    })
    .filter((entry) => entry.lang === "bogotano" && entry.text?.trim());

  return entries
    .filter((entry) => entry.date >= today)
    .sort((a, b) => a.date.localeCompare(b.date) || a.group.localeCompare(b.group))
    .slice(0, 4)
    .map(({ group, text }) => ({ group, text }));
}

function compactNarrative(text: string) {
  const cleaned = text
    .replace(/^#{1,3}\s*/gm, "")
    .replace(/\*\*/g, "")
    .trim();
  const paragraphs = cleaned.split(/\n{2,}/).filter(Boolean);
  return paragraphs.slice(0, 3).join("\n\n");
}

function Kpi({ label, value, sub, gold }: {
  label: string; value: string; sub?: string; gold?: boolean;
}) {
  return (
    <div
      className="stat-card !p-4 text-left"
      style={gold ? { borderColor: "rgba(212,168,67,0.35)" } : undefined}
    >
      <p
        className="text-[10px] uppercase tracking-widest mb-1.5"
        style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}
      >
        {label}
      </p>
      <p
        className="leading-none tabular-nums flex items-baseline gap-2 flex-wrap"
        style={{
          fontFamily: "var(--font-display)",
          fontSize: "clamp(1.7rem, 4vw, 2.4rem)",
          color: gold ? "var(--wc-gold)" : "var(--text)",
        }}
      >
        {value}
        {sub && (
          <span className="text-sm" style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
            {sub}
          </span>
        )}
      </p>
    </div>
  );
}

function SectionTitle({ title, note, dot }: { title: string; note?: string; dot?: boolean }) {
  return (
    <div className="flex items-center gap-2.5 flex-wrap">
      {dot
        ? <span className="live-dot shrink-0" />
        : <span className="shrink-0" style={{ width: 18, height: 3, background: "var(--wc-red)" }} />}
      <h3
        className="text-[11px] font-bold uppercase tracking-[0.18em]"
        style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}
      >
        {title}
      </h3>
      {note && (
        <span className="text-xs hidden sm:inline" style={{ color: "var(--text-muted)" }}>
          · {note}
        </span>
      )}
    </div>
  );
}
