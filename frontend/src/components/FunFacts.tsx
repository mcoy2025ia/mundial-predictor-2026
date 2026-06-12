"use client";

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type { SiteStats, Goalscorer, GoalscorerVictim, QatarBacktest } from "@/types";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid, ReferenceLine, Cell,
} from "recharts";
import { useLang } from "@/lib/i18n";

interface Props {
  stats: SiteStats;
  goalscorers: Goalscorer[];
  qatar?: QatarBacktest | null;
}

export default function FunFacts({ stats, goalscorers, qatar }: Props) {
  const T = useLang();
  const {
    total_matches, total_goals, avg_goals_all, n_editions,
    highest_scoring_match, biggest_victory,
    goals_by_year, best_avg_edition, worst_avg_edition,
    top_scoring_teams, top_upsets,
  } = stats;

  const maxAvg = Math.max(...goals_by_year.map((y) => y.avg));

  return (
    <div className="space-y-10">
      {/* ── KPIs ── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { val: total_matches.toLocaleString(), lbl: T.kpiMatches,  icon: "🏟️" },
          { val: total_goals.toLocaleString(),   lbl: T.kpiGoals,    icon: "⚽" },
          { val: avg_goals_all.toFixed(2),       lbl: T.kpiAvg,      icon: "📊" },
          { val: n_editions,                     lbl: T.kpiEditions, icon: "🏆" },
        ].map(({ val, lbl, icon }) => (
          <div key={lbl} className="stat-card text-center">
            <div className="text-3xl mb-1">{icon}</div>
            <div className="text-3xl font-black text-[var(--wc-red)]">{val}</div>
            <div className="text-xs text-[var(--text-muted)] mt-1">{lbl}</div>
          </div>
        ))}
      </div>

      {/* ── Records ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="stat-card">
          <div className="text-xs text-[var(--wc-gold)] font-bold uppercase tracking-widest mb-3">
            {T.recHighScore}
          </div>
          <div className="text-4xl text-center my-3">
            {highest_scoring_match.flag_home}{highest_scoring_match.flag_away}
          </div>
          <div className="text-center">
            <span className="font-bold">{highest_scoring_match.home_team}</span>
            <span className="text-4xl font-black mx-3 text-[var(--wc-red)]">
              {highest_scoring_match.home_score}–{highest_scoring_match.away_score}
            </span>
            <span className="font-bold">{highest_scoring_match.away_team}</span>
          </div>
          <div className="text-center text-[var(--text-muted)] text-sm mt-1">
            {highest_scoring_match.year} · {highest_scoring_match.total} {T.recGoalLabel}
          </div>
        </div>

        <div className="stat-card">
          <div className="text-xs text-[var(--wc-gold)] font-bold uppercase tracking-widest mb-3">
            {T.recBigWin}
          </div>
          <div className="text-4xl text-center my-3">
            {biggest_victory.flag_home}{biggest_victory.flag_away}
          </div>
          <div className="text-center">
            <span className="font-bold">{biggest_victory.home_team}</span>
            <span className="text-4xl font-black mx-3 text-[var(--wc-red)]">
              {biggest_victory.home_score}–{biggest_victory.away_score}
            </span>
            <span className="font-bold">{biggest_victory.away_team}</span>
          </div>
          <div className="text-center text-[var(--text-muted)] text-sm mt-1">
            {biggest_victory.year} · +{biggest_victory.margin} {T.recMarginLabel}
          </div>
        </div>
      </div>

      {/* ── Goals by year chart ── */}
      <div className="stat-card">
        <h3 className="font-bold mb-4">{T.chartTitle}</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={goals_by_year} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="year" tick={{ fontSize: 10 }} interval={3} />
            <YAxis tick={{ fontSize: 10 }} domain={[0, Math.ceil(maxAvg) + 0.5]} />
            <Tooltip
              formatter={(v: number) => [`${v.toFixed(2)} g/partido`]}
              contentStyle={{ background: "var(--surface-2)", border: "1px solid var(--border-subtle)", borderRadius: 10 }}
            />
            <ReferenceLine y={avg_goals_all} stroke="rgba(245,211,0,0.5)" strokeDasharray="6 3"
              label={{ value: `Avg ${avg_goals_all.toFixed(2)}`, fill: "var(--wc-gold)", fontSize: 10 }} />
            <Bar dataKey="avg" radius={[4, 4, 0, 0]}>
              {goals_by_year.map((entry) => (
                <Cell
                  key={entry.year}
                  fill={entry.year === best_avg_edition.year ? "var(--wc-gold)" : "var(--wc-red)"}
                  fillOpacity={entry.year === best_avg_edition.year ? 1 : 0.75}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
        <p className="text-xs text-[var(--text-muted)] mt-2">
          ↑ {best_avg_edition.year} ({best_avg_edition.avg.toFixed(2)}) · ↓ {worst_avg_edition.year} ({worst_avg_edition.avg.toFixed(2)})
        </p>
      </div>

      {/* ── Individual top scorers ── */}
      {goalscorers.length > 0 && (
        <GoalscorersTable goalscorers={goalscorers} />
      )}

      {/* ── Top scoring teams ── */}
      <div className="stat-card overflow-x-auto">
        <h3 className="font-bold mb-4">{T.topScoringTitle}</h3>
        <table>
          <thead>
            <tr>
              <th>{T.colTeam}</th>
              <th className="text-right">{T.colMatches}</th>
              <th className="text-right">{T.colGoalsFor}</th>
              <th className="text-right">{T.colGoalsAgainst}</th>
              <th className="text-right">{T.colDiff}</th>
              <th className="text-right">{T.colGoalsPerGame}</th>
            </tr>
          </thead>
          <tbody>
            {top_scoring_teams.slice(0, 12).map((t) => (
              <tr key={t.team}>
                <td><span className="flex items-center gap-2">{t.flag} {t.team}</span></td>
                <td className="text-right text-[var(--text-muted)]">{t.matches}</td>
                <td className="text-right font-bold text-[var(--wc-red)]">{t.goals_for}</td>
                <td className="text-right text-[var(--text-muted)]">{t.goals_against}</td>
                <td className="text-right">
                  <span className={t.goal_diff >= 0 ? "text-green-400" : "text-red-400"}>
                    {t.goal_diff >= 0 ? "+" : ""}{t.goal_diff}
                  </span>
                </td>
                <td className="text-right tabular-nums">{t.avg.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Top upsets ── */}
      <div className="stat-card overflow-x-auto">
        <h3 className="font-bold mb-1">{T.topUpsets}</h3>
        <p className="text-xs text-[var(--text-muted)] mb-4">{T.upsetSubtitle}</p>
        <table>
          <thead>
            <tr>
              <th>{T.colYear}</th>
              <th>{T.colMatch}</th>
              <th>{T.colScore}</th>
              <th>{T.colFavored}</th>
              <th>{T.colWinner}</th>
              <th className="text-right">{T.colEloDiff}</th>
            </tr>
          </thead>
          <tbody>
            {top_upsets.map((u, i) => (
              <tr key={i}>
                <td className="text-[var(--text-muted)]">{u.year}</td>
                <td><span className="text-xs">{u.flag_favored} {u.favored} vs {u.flag_winner} {u.winner}</span></td>
                <td className="font-bold tabular-nums">{u.home_score}–{u.away_score}</td>
                <td className="text-[var(--text-muted)] text-xs">{u.flag_favored} {u.favored} ({u.elo_favored})</td>
                <td>
                  <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-[var(--wc-red)]/20 text-[var(--wc-red)]">
                    {u.flag_winner} {u.winner}
                  </span>
                </td>
                <td className="text-right font-bold text-[var(--wc-gold)]">+{u.elo_advantage} ELO</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ── Backtest Qatar 2022 ── */}
      {qatar && qatar.matches.length > 0 && <QatarSection qatar={qatar} />}
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   BACKTEST QATAR 2022 — qué predijo el modelo en el test
══════════════════════════════════════════════════════ */
function QatarSection({ qatar }: { qatar: QatarBacktest }) {
  const T = useLang();
  const [showAll, setShowAll] = useState(false);
  const rows = showAll ? qatar.matches : qatar.matches.slice(0, 10);

  return (
    <div>
      <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-1">
        {T.backtestTitle}
      </h3>
      <p className="text-xs text-[var(--text-muted)] mb-4 max-w-2xl">{T.backtestDesc}</p>

      <div className="stat-card !p-3 mb-4 flex items-center gap-3 flex-wrap">
        <span className="text-3xl font-black tabular-nums" style={{ color: "var(--wc-gold)" }}>
          {(qatar.accuracy * 100).toFixed(0)}%
        </span>
        <span className="text-sm font-bold">{qatar.hits}/{qatar.n} {T.backtestHits}</span>
        <span className="text-xs text-[var(--text-muted)]">· {T.backtestBaseline}</span>
      </div>

      <div className="space-y-1.5">
        {rows.map((m) => {
          const predLabel =
            m.predicted === "home_win" ? m.home_team :
            m.predicted === "away_win" ? m.away_team : T.draw;
          const predProb =
            m.predicted === "home_win" ? m.home_win :
            m.predicted === "away_win" ? m.away_win : m.draw;
          return (
            <div key={`${m.date}|${m.home_team}|${m.away_team}`}
              className="stat-card !p-2.5 flex items-center gap-2 flex-wrap text-sm">
              <span className="text-xs text-[var(--text-muted)] tabular-nums w-16 shrink-0">
                {m.date.slice(5)}
              </span>
              <span className="flex-1 min-w-[180px]">
                {m.home_flag} {m.home_team} <strong className="tabular-nums">{m.home_score}–{m.away_score}</strong> {m.away_team} {m.away_flag}
              </span>
              <span className="text-xs text-[var(--text-muted)]">
                {predLabel} · {(predProb * 100).toFixed(0)}%
              </span>
              <span className={`verdict-badge ${m.hit ? "verdict-hit" : "verdict-miss"}`}>
                {m.hit ? "✓" : "✗"}
              </span>
            </div>
          );
        })}
      </div>

      <button onClick={() => setShowAll(!showAll)}
        className="mt-3 text-xs font-bold uppercase tracking-widest text-[var(--wc-gold)] hover:opacity-80 transition-opacity">
        {showAll ? T.backtestLess : `${T.backtestMore} (${qatar.n})`}
      </button>
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   TABLA DE GOLEADORES
══════════════════════════════════════════════════════ */
function GoalscorersTable({ goalscorers }: { goalscorers: Goalscorer[] }) {
  const T = useLang();
  const [hovered,  setHovered]  = useState<Goalscorer | null>(null);
  const [selected, setSelected] = useState<Goalscorer | null>(null);

  const active   = selected ?? hovered;
  const isPinned = selected !== null;
  const maxGoals = goalscorers[0]?.goals ?? 1;

  function handleRowClick(g: Goalscorer) {
    setSelected((prev) => (prev?.rank === g.rank ? null : g));
  }

  return (
    <div className="stat-card">
      <h3 className="font-bold mb-1">{T.topScorersTableTitle}</h3>
      <p className="text-xs text-[var(--text-muted)] mb-4">
        {T.topScorersSubtitle}
        <span
          className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-mono"
          style={{
            background: "rgba(212,168,67,0.10)",
            color: "var(--color-wc-gold, #D4A843)",
            border: "1px solid rgba(212,168,67,0.20)",
          }}
        >
          {T.hoverHint}
        </span>
      </p>

      <div className="flex flex-col lg:flex-row gap-4">
        {/* Tabla */}
        <div className="overflow-x-auto flex-1">
          <table onMouseLeave={() => setHovered(null)} style={{ tableLayout: "fixed" }}>
            <colgroup>
              <col style={{ width: 36 }} />
              <col />
              <col style={{ width: 120 }} />
              <col style={{ width: 68 }} />
            </colgroup>
            <thead>
              <tr>
                <th>#</th>
                <th>{T.topScorers}</th>
                <th>{T.colTeam}</th>
                <th className="text-right">⚽</th>
              </tr>
            </thead>
            <tbody>
              {goalscorers.map((g) => {
                const isHovered  = hovered?.rank  === g.rank;
                const isSelected = selected?.rank === g.rank;
                const isActive   = isHovered || isSelected;
                const medal = g.rank === 1 ? "🥇" : g.rank === 2 ? "🥈" : g.rank === 3 ? "🥉" : null;

                return (
                  <tr
                    key={g.rank}
                    onMouseEnter={() => setHovered(g)}
                    onClick={() => handleRowClick(g)}
                    className="transition-colors duration-100"
                    style={{
                      cursor: "pointer",
                      background: isSelected
                        ? "rgba(212,168,67,0.14)"
                        : isHovered
                        ? "rgba(212,168,67,0.07)"
                        : g.rank <= 3
                        ? "rgba(234,179,8,0.03)"
                        : "transparent",
                      boxShadow: isSelected
                        ? "inset 2px 0 0 rgba(212,168,67,0.8)"
                        : isHovered
                        ? "inset 2px 0 0 rgba(212,168,67,0.35)"
                        : "none",
                    }}
                  >
                    <td className="font-mono text-xs" style={{ color: "var(--text-muted, #9898BB)" }}>
                      {medal ?? g.rank}
                    </td>
                    <td>
                      <div className="flex items-center gap-1.5">
                        {isSelected && <span className="text-[10px]" title={T.pinnedLabel}>📌</span>}
                        <span
                          className="font-semibold text-sm"
                          style={{ color: isActive ? "var(--color-wc-gold, #D4A843)" : "var(--text, #F0F0FF)", transition: "color 0.12s" }}
                        >
                          {g.scorer}
                        </span>
                      </div>
                    </td>
                    <td className="text-sm" style={{ color: "var(--text-muted, #9898BB)" }}>
                      {g.flag} {g.country}
                    </td>
                    <td className="text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <div
                          className="hidden sm:block h-1.5 rounded-full"
                          style={{
                            width: `${Math.round((g.goals / maxGoals) * 44)}px`,
                            background: isActive ? "var(--color-wc-gold, #D4A843)" : "rgba(207,10,44,0.55)",
                            transition: "background 0.15s",
                          }}
                        />
                        <span
                          className="font-black text-lg tabular-nums"
                          style={{
                            fontFamily: "var(--font-display, 'Bebas Neue', system-ui)",
                            color: isActive ? "var(--color-wc-gold, #D4A843)" : "var(--wc-red, #CF0A2C)",
                            transition: "color 0.12s",
                          }}
                        >
                          {g.goals}
                        </span>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Panel de víctimas */}
        <div className="lg:w-72 shrink-0">
          <AnimatePresence mode="wait">
            {active ? (
              <motion.div
                key={active.rank}
                initial={{ opacity: 0, x: 14 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 10 }}
                transition={{ duration: 0.18, ease: [0.22, 1, 0.36, 1] }}
                className="rounded-xl p-4"
                style={{
                  background: "var(--color-arena-elevated, #161628)",
                  border: isPinned ? "1px solid rgba(212,168,67,0.40)" : "1px solid rgba(212,168,67,0.18)",
                  boxShadow: isPinned
                    ? "0 0 24px rgba(212,168,67,0.12), 0 8px 32px rgba(0,0,0,0.4)"
                    : "0 8px 32px rgba(0,0,0,0.4)",
                }}
              >
                <div className="flex items-center gap-2 mb-3">
                  <span className="text-xl">{active.flag}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-1.5">
                      <p className="font-bold text-sm leading-tight truncate" style={{ color: "var(--color-ink-primary, #F0F0FF)" }}>
                        {active.scorer}
                      </p>
                      {isPinned && (
                        <span
                          className="text-[9px] px-1.5 py-0.5 rounded-full font-mono shrink-0"
                          style={{ background: "rgba(212,168,67,0.15)", color: "var(--color-wc-gold, #D4A843)", border: "1px solid rgba(212,168,67,0.30)" }}
                        >
                          {T.pinnedLabel}
                        </span>
                      )}
                    </div>
                    <p className="text-[10px] font-mono" style={{ color: "var(--color-ink-muted, #4A4A6A)" }}>
                      {active.goals} {T.goalsInFinalStage}
                    </p>
                  </div>
                  <span
                    className="text-2xl leading-none tabular-nums shrink-0"
                    style={{ fontFamily: "var(--font-display, 'Bebas Neue', system-ui)", color: "var(--color-wc-gold, #D4A843)" }}
                  >
                    {active.goals}
                  </span>
                </div>

                <div className="h-px mb-3" style={{ background: "linear-gradient(90deg, rgba(212,168,67,0.35), transparent)" }} />

                <p className="text-[10px] uppercase tracking-widest mb-2 font-mono" style={{ color: "var(--color-ink-muted, #4A4A6A)" }}>
                  {T.victimsTitle}
                </p>

                {(active.victims ?? []).length === 0 ? (
                  <p className="text-xs italic" style={{ color: "var(--color-ink-muted, #4A4A6A)" }}>
                    {T.noDataAvailable}
                  </p>
                ) : (
                  <div className="space-y-1.5 max-h-72 overflow-y-auto pr-1">
                    {active.victims.map((v, i) => (
                      <VictimRow key={v.team} victim={v} maxVictimGoals={active.victims[0].goals} index={i} />
                    ))}
                  </div>
                )}

                {isPinned && (
                  <button
                    onClick={() => setSelected(null)}
                    className="mt-3 w-full text-[10px] font-mono py-1 rounded-lg transition-colors"
                    style={{
                      color: "var(--color-ink-muted, #4A4A6A)",
                      background: "rgba(255,255,255,0.03)",
                      border: "1px solid rgba(255,255,255,0.06)",
                    }}
                  >
                    {T.closePanel}
                  </button>
                )}
              </motion.div>
            ) : (
              <motion.div
                key="idle"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className="hidden lg:flex flex-col items-center justify-center gap-2 min-h-36 rounded-xl"
                style={{ background: "var(--color-arena-elevated, #161628)", border: "1px dashed rgba(255,255,255,0.07)" }}
              >
                <span className="text-2xl opacity-30">⚽</span>
                <p
                  className="text-xs text-center px-4 leading-relaxed"
                  style={{ color: "var(--color-ink-muted, #4A4A6A)", fontFamily: "var(--font-mono, monospace)" }}
                >
                  {T.idleScorersHint}
                </p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function VictimRow({ victim, maxVictimGoals, index }: { victim: GoalscorerVictim; maxVictimGoals: number; index: number }) {
  const barPct = Math.round((victim.goals / maxVictimGoals) * 100);
  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.14, delay: index * 0.03 }}
      className="flex items-center gap-2 group"
    >
      <span className="text-[10px] font-mono w-4 shrink-0 text-right" style={{ color: "var(--color-ink-muted, #4A4A6A)" }}>
        {index + 1}
      </span>
      <span className="text-base leading-none shrink-0">{victim.flag}</span>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between mb-0.5">
          <span className="text-xs truncate" style={{ color: "var(--color-ink-secondary, #9898BB)" }}>
            {victim.team}
          </span>
          <span
            className="text-xs font-bold tabular-nums ml-1 shrink-0"
            style={{
              fontFamily: "var(--font-mono, monospace)",
              color: victim.goals >= 3 ? "var(--color-wc-gold, #D4A843)" : "var(--color-ink-primary, #F0F0FF)",
            }}
          >
            {victim.goals}⚽
          </span>
        </div>
        <div className="h-1 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.06)" }}>
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${barPct}%` }}
            transition={{ duration: 0.4, delay: index * 0.03, ease: [0.22, 1, 0.36, 1] }}
            className="h-full rounded-full"
            style={{ background: victim.goals >= 3 ? "var(--color-wc-gold, #D4A843)" : "rgba(207,10,44,0.7)" }}
          />
        </div>
      </div>
    </motion.div>
  );
}
