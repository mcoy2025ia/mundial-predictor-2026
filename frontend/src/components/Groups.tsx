"use client";

import { useState } from "react";
import type { GroupMatch, GroupStandingEntry } from "@/types";
import { useLang } from "@/lib/i18n";
import { modelRecord, modelVerdict, orientScore, type ScoreMap } from "@/lib/live";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  groupStandings: Record<string, GroupStandingEntry[]>;
  liveScores?: ScoreMap;
}

function fmt(n: number) { return `${(n * 100).toFixed(0)}%`; }

function MatchCard({ match, liveScores }: { match: GroupMatch; liveScores?: ScoreMap }) {
  const T = useLang();
  const { team1, team2, team1_flag, team2_flag, t1_win, draw, t2_win, date, ground } = match;
  const d = new Date(date + "T12:00:00");
  const dateStr = d.toLocaleDateString("es-CO", { month: "short", day: "numeric" });
  const venue = ground.split("(")[0].trim();
  const maxP = Math.max(t1_win, t2_win);

  // marcador real si el partido ya se jugó (openfootball)
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

      {/* veredicto del modelo vs resultado real */}
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

export default function Groups({ groupMatches, groupStandings, liveScores }: Props) {
  const T = useLang();
  const groups = Object.keys(groupMatches).sort();
  const [selected, setSelected] = useState(groups.includes("K") ? "K" : groups[0] ?? "A");

  const matches = (groupMatches[selected] ?? [])
    .slice()
    .sort((a, b) => a.date.localeCompare(b.date));
  const standings = groupStandings[selected] ?? [];

  // récord global del modelo sobre los partidos ya jugados
  const { played, hits } = modelRecord(groupMatches, liveScores ?? new Map());

  return (
    <div className="space-y-6">
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

      <div className="flex flex-wrap gap-2">
        {groups.map((g) => (
          <button
            key={g}
            onClick={() => setSelected(g)}
            className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
              selected === g
                ? "bg-[var(--wc-red)] text-white shadow-lg shadow-red-900/30"
                : "bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {T.group} {g}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
        <StandingsCard standings={standings} />
        <div className="space-y-3">
          {matches.map((m) => (
            <MatchCard key={`${m.team1}|${m.team2}`} match={m} liveScores={liveScores} />
          ))}
        </div>
      </div>

      <p className="text-xs text-center text-[var(--text-muted)]">
        {T.groupsXGBNote}
      </p>
    </div>
  );
}
