"use client";

import { useMemo, useState } from "react";
import type { TeamInfo } from "@/types";
import AgentDebatePanel from "./AgentDebatePanel";

interface ScoreLine { home: number; away: number; prob: number; }
interface Pred { p_home: number; p_draw: number; p_away: number; top_scorelines?: ScoreLine[]; }
interface Result { home_score: number; away_score: number; winner: "home" | "away" | "draw"; played: boolean; }

export interface KnockoutMatch {
  num: number;
  round: string;
  round_es: string;
  date: string;
  time: string;
  ground: string;
  home: string | null;
  away: string | null;
  home_label: string;
  away_label: string;
  resolved: boolean;
  pred?: Pred;
  result?: Result;
}

export interface BracketData {
  round_order: string[];
  round_labels: Record<string, string>;
  rounds: Record<string, KnockoutMatch[]>;
  counts: Record<string, number>;
}

interface Props {
  data: BracketData;
  roundKey: string;
  teams: Record<string, TeamInfo>;
}

const LEFT_PATH: Record<string, number[]> = {
  "Round of 32": [74, 77, 73, 75, 83, 84, 81, 82],
  "Round of 16": [89, 90, 93, 94],
  "Quarter-final": [97, 98],
  "Semi-final": [101],
};

const RIGHT_PATH: Record<string, number[]> = {
  "Semi-final": [102],
  "Quarter-final": [99, 100],
  "Round of 16": [91, 92, 95, 96],
  "Round of 32": [76, 78, 79, 80, 86, 88, 85, 87],
};

function byNums(matches: KnockoutMatch[], nums: number[]) {
  const map = new Map(matches.map((m) => [m.num, m]));
  return nums.map((n) => map.get(n)).filter((m): m is KnockoutMatch => Boolean(m));
}

function fmtDate(d: string) {
  const months = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
  const m = d.match(/(\d{4})-(\d{2})-(\d{2})/);
  if (!m) return d;
  return `${parseInt(m[3], 10)} ${months[parseInt(m[2], 10) - 1]}`;
}

function shortVenue(ground: string) {
  return ground.replace(/\s*\(.+?\)\s*/g, "").replace("New York/New Jersey", "New York");
}

function flagOf(teams: Record<string, TeamInfo>, name: string | null) {
  if (!name) return "";
  return teams[name]?.flag ?? "";
}

function pct(v?: number) {
  return v == null ? "-" : `${Math.round(v * 100)}%`;
}

function displayName(name: string) {
  return name
    .replace("Bosnia and Herzegovina", "Bosnia/Herz.")
    .replace("United States", "United States")
    .replace("Ivory Coast", "Ivory Coast")
    .replace("Cape Verde", "Cape Verde")
    .replace("DR Congo", "D.R. Congo");
}

export default function KnockoutBracket({ data, roundKey, teams }: Props) {
  const [selectedMatch, setSelectedMatch] = useState<KnockoutMatch | null>(null);
  const displayRounds = useMemo(() => {
    const roundsCopy: Record<string, KnockoutMatch[]> = {};
    for (const [round, matches] of Object.entries(data?.rounds ?? {})) {
      roundsCopy[round] = [...matches];
    }
    if ((roundsCopy["Semi-final"]?.length ?? 0) >= 2 && !(roundsCopy["Final"]?.length ?? 0)) {
      roundsCopy["Final"] = [{
        num: 104,
        round: "Final",
        round_es: data?.round_labels?.["Final"] ?? "Final",
        date: "2026-07-19",
        time: "15:00 UTC-4",
        ground: "New York/New Jersey (East Rutherford)",
        home: null,
        away: null,
        home_label: "Ganador #101",
        away_label: "Ganador #102",
        resolved: false,
      }];
    }
    return roundsCopy;
  }, [data]);

  const focusedLabel = data?.round_labels?.[roundKey] ?? roundKey;
  const rounds = (data?.round_order ?? []).filter((r) => (displayRounds[r] ?? []).length > 0);
  const total = rounds.reduce((sum, r) => sum + (displayRounds[r]?.length ?? 0), 0);
  const played = rounds.reduce((sum, r) => sum + (displayRounds[r] ?? []).filter((m) => m.result?.played).length, 0);
  const resolved = rounds.reduce((sum, r) => sum + (displayRounds[r] ?? []).filter((m) => m.resolved).length, 0);

  const left = {
    r32: byNums(displayRounds["Round of 32"] ?? [], LEFT_PATH["Round of 32"]),
    r16: byNums(displayRounds["Round of 16"] ?? [], LEFT_PATH["Round of 16"]),
    qf: byNums(displayRounds["Quarter-final"] ?? [], LEFT_PATH["Quarter-final"]),
    sf: byNums(displayRounds["Semi-final"] ?? [], LEFT_PATH["Semi-final"]),
  };
  const right = {
    r32: byNums(displayRounds["Round of 32"] ?? [], RIGHT_PATH["Round of 32"]),
    r16: byNums(displayRounds["Round of 16"] ?? [], RIGHT_PATH["Round of 16"]),
    qf: byNums(displayRounds["Quarter-final"] ?? [], RIGHT_PATH["Quarter-final"]),
    sf: byNums(displayRounds["Semi-final"] ?? [], RIGHT_PATH["Semi-final"]),
  };
  const finalMatch = displayRounds["Final"]?.[0];

  if (!rounds.length) {
    return (
      <div className="stat-card text-center py-10 text-[var(--text-muted)]">
        Aun no hay cruces definidos para {focusedLabel}.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <style jsx global>{`
        .bracket-stage {
          overflow-x: auto;
          padding: 0.25rem 0 1rem;
        }
        .bracket-map {
          width: min(100%, 68rem);
          min-width: 68rem;
          min-height: 51rem;
          margin: 0 auto;
          display: grid;
          grid-template-columns: 10.6rem 5.85rem 4.9rem 4.35rem 9.7rem 4.35rem 4.9rem 5.85rem 10.6rem;
          grid-template-rows: repeat(16, 2.75rem);
          column-gap: 0.45rem;
          position: relative;
          border-radius: 8px;
          background:
            radial-gradient(circle at 50% 48%, rgba(212,168,67,0.10), transparent 18rem),
            linear-gradient(180deg, rgba(18,20,38,0.98), rgba(9,10,20,0.98));
          color: var(--text);
          padding: 1.15rem;
          box-shadow: 0 20px 70px rgba(0,0,0,0.42);
          border: 1px solid rgba(212,168,67,0.18);
        }
        .bracket-map::before {
          content: "";
          position: absolute;
          inset: 1.15rem;
          background-image:
            linear-gradient(90deg, transparent 0 49.7%, rgba(212,168,67,0.08) 49.7% 50.3%, transparent 50.3% 100%),
            radial-gradient(circle at 50% 50%, rgba(207,10,44,0.08), transparent 28rem);
          pointer-events: none;
        }
        .center-title {
          grid-column: 5;
          grid-row: 5 / span 4;
          align-self: center;
          justify-self: center;
          text-align: center;
          z-index: 2;
        }
        .cup-pill {
          display: inline-flex;
          align-items: center;
          justify-content: center;
          padding: 0.45rem 1rem;
          border-radius: 999px;
          background: #083f2d;
          color: #f7fff7;
          border: 0.22rem solid var(--wc-gold);
          font-family: var(--font-mono);
          font-size: 0.7rem;
          font-weight: 900;
          letter-spacing: 0.08em;
          text-transform: uppercase;
          margin-bottom: 0.55rem;
        }
        .center-title h3 {
          font-family: var(--font-display);
          font-size: clamp(1.55rem, 3vw, 2.35rem);
          line-height: 0.95;
          font-weight: 950;
          color: var(--text);
          text-transform: uppercase;
          letter-spacing: 0;
          margin: 0;
        }
        .center-note {
          margin-top: 0.55rem;
          font-family: var(--font-mono);
          font-size: 0.58rem;
          color: var(--text-muted);
          text-transform: uppercase;
          letter-spacing: 0.08em;
        }
        .connector {
          position: absolute;
          border-color: rgba(70,70,70,0.20);
          pointer-events: none;
        }
        .bracket-card {
          align-self: center;
          z-index: 2;
          width: 100%;
          border: 1px solid rgba(212,168,67,0.24);
          background: rgba(18,20,38,0.96);
          color: var(--text);
          box-shadow: 0 10px 24px rgba(0,0,0,0.22);
          overflow: hidden;
          text-align: left;
          cursor: pointer;
          transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
        }
        .bracket-card:hover,
        .bracket-card:focus-visible {
          transform: translateY(-1px);
          border-color: rgba(212,168,67,0.72);
          box-shadow: 0 12px 30px rgba(0,0,0,0.34), 0 0 0 1px rgba(212,168,67,0.18);
          outline: none;
        }
        .bracket-card.r32 {
          min-height: 4.3rem;
        }
        .bracket-card.small {
          min-height: 3.25rem;
        }
        .bracket-card .meta {
          display: flex;
          justify-content: space-between;
          gap: 0.4rem;
          padding: 0.2rem 0.35rem;
          background: rgba(212,168,67,0.13);
          border-bottom: 1px solid rgba(212,168,67,0.18);
          font-size: 0.62rem;
          font-weight: 900;
          line-height: 1.1;
          color: var(--wc-gold);
        }
        .bracket-card.small .meta {
          font-size: 0.48rem;
        }
        .bracket-card .meta-date {
          font-weight: 600;
          color: var(--text-muted);
          white-space: nowrap;
        }
        .bracket-card .teams {
          padding: 0.3rem 0.45rem;
          display: grid;
          gap: 0.2rem;
        }
        .bracket-card.small .teams {
          padding: 0.25rem 0.35rem;
          gap: 0.12rem;
        }
        .bracket-card .team {
          display: grid;
          grid-template-columns: 1.2rem 1fr auto;
          gap: 0.28rem;
          align-items: center;
          min-width: 0;
          font-size: 0.84rem;
          line-height: 1.08;
          color: var(--text);
          font-weight: 700;
        }
        .bracket-card.small .team {
          grid-template-columns: 1fr auto;
          font-size: 0.68rem;
        }
        .bracket-card .flag {
          text-align: center;
          font-size: 0.85rem;
        }
        .bracket-card .name {
          overflow: hidden;
          text-overflow: ellipsis;
          white-space: nowrap;
        }
        .bracket-card.small .name {
          font-style: italic;
        }
        .bracket-card .score {
          font-family: var(--font-mono);
          font-weight: 950;
          color: #32d583;
        }
        .bracket-card .muted {
          color: var(--text-muted);
          font-style: italic;
        }
        .bracket-card .winner .name,
        .bracket-card .winner .score {
          color: #32d583;
          font-weight: 950;
          font-style: normal;
        }
        .bracket-card .status {
          margin-top: 0.18rem;
          display: inline-flex;
          width: fit-content;
          padding: 0.08rem 0.28rem;
          border-radius: 999px;
          background: rgba(50,213,131,0.12);
          color: #32d583;
          font-size: 0.45rem;
          font-weight: 900;
          text-transform: uppercase;
        }
        @media (max-width: 720px) {
          .bracket-map {
            min-width: 64rem;
            grid-template-columns: 10rem 5.55rem 4.65rem 4.1rem 9.2rem 4.1rem 4.65rem 5.55rem 10rem;
          }
        }
      `}</style>

      <div className="text-center">
        <h3 className="text-2xl font-black mb-1" style={{ color: "var(--wc-gold)" }}>
          Llaves de eliminatorias
        </h3>
        <p className="text-sm text-[var(--text-muted)]">
          {played} jugados · {resolved}/{total} cruces definidos · desde {focusedLabel}
        </p>
      </div>

      <div className="bracket-stage">
        <div className="bracket-map">
          <div className="center-title">
            <div className="cup-pill">World Cup</div>
            <h3>Round of 32<br />Bracket</h3>
            <div className="center-note">R32 → Octavos → Cuartos → Semis → Final</div>
          </div>

          {finalMatch && (
            <BracketNode
              match={finalMatch}
              teams={teams}
              variant="small"
              col={5}
              row={10}
              label="Final"
              onSelect={setSelectedMatch}
            />
          )}

          <HalfBracket side="left" data={left} teams={teams} onSelect={setSelectedMatch} />
          <HalfBracket side="right" data={right} teams={teams} onSelect={setSelectedMatch} />
        </div>
      </div>

      <PredictionPanel match={selectedMatch} teams={teams} onClose={() => setSelectedMatch(null)} />
    </div>
  );
}

function HalfBracket({
  side,
  data,
  teams,
  onSelect,
}: {
  side: "left" | "right";
  data: { r32: KnockoutMatch[]; r16: KnockoutMatch[]; qf: KnockoutMatch[]; sf: KnockoutMatch[] };
  teams: Record<string, TeamInfo>;
  onSelect: (match: KnockoutMatch) => void;
}) {
  const cols = side === "left"
    ? { r32: 1, r16: 2, qf: 3, sf: 4 }
    : { sf: 6, qf: 7, r16: 8, r32: 9 };
  const align = side;

  return (
    <>
      {data.r32.map((m, i) => (
        <BracketNode key={m.num} match={m} teams={teams} variant="r32" col={cols.r32} row={1 + i * 2} align={align} onSelect={onSelect} />
      ))}
      {data.r16.map((m, i) => (
        <BracketNode key={m.num} match={m} teams={teams} variant="small" col={cols.r16} row={2 + i * 4} align={align} onSelect={onSelect} />
      ))}
      {data.qf.map((m, i) => (
        <BracketNode key={m.num} match={m} teams={teams} variant="small" col={cols.qf} row={4 + i * 8} align={align} label="Quarter-final" onSelect={onSelect} />
      ))}
      {data.sf.map((m) => (
        <BracketNode key={m.num} match={m} teams={teams} variant="small" col={cols.sf} row={7} align={align} label="Semi-final" onSelect={onSelect} />
      ))}
    </>
  );
}

function BracketNode({
  match,
  teams,
  variant,
  col,
  row,
  align = "left",
  label,
  onSelect,
}: {
  match: KnockoutMatch;
  teams: Record<string, TeamInfo>;
  variant: "r32" | "small";
  col: number;
  row: number;
  align?: "left" | "right";
  label?: string;
  onSelect: (match: KnockoutMatch) => void;
}) {
  const res = match.result;
  const homeName = match.home ?? match.home_label;
  const awayName = match.away ?? match.away_label;
  const isSmall = variant === "small";
  const homeWon = res?.winner === "home";
  const awayWon = res?.winner === "away";

  return (
    <button
      type="button"
      onClick={() => onSelect(match)}
      className={`bracket-card ${isSmall ? "small" : "r32"} ${res?.played ? "played" : ""} ${align}`}
      style={{ gridColumn: col, gridRow: `${row} / span ${isSmall ? 2 : 2}` }}
      aria-label={`Ver predicción de ${homeName} vs ${awayName}`}
    >
      <div className="meta">
        <span>{label ?? shortVenue(match.ground)}</span>
        <span className="meta-date">{fmtDate(match.date)}</span>
      </div>
      <div className="teams">
        <TeamLine
          flag={flagOf(teams, match.home)}
          name={displayName(homeName)}
          score={res?.played ? res.home_score : undefined}
          winner={homeWon}
          muted={!match.home || awayWon}
          compact={isSmall}
        />
        <TeamLine
          flag={flagOf(teams, match.away)}
          name={displayName(awayName)}
          score={res?.played ? res.away_score : undefined}
          winner={awayWon}
          muted={!match.away || homeWon}
          compact={isSmall}
        />
        {res?.played && !isSmall && <span className="status">Final</span>}
      </div>
    </button>
  );
}

function TeamLine({
  flag,
  name,
  score,
  winner,
  muted,
  compact,
}: {
  flag: string;
  name: string;
  score?: number;
  winner: boolean;
  muted: boolean;
  compact: boolean;
}) {
  return (
    <div className={`team ${winner ? "winner" : ""} ${muted ? "muted" : ""}`}>
      {!compact && <span className="flag">{flag}</span>}
      <span className="name">{compact ? name.replace("Ganador ", "W") : `${flag && compact ? `${flag} ` : ""}${name}`}</span>
      {score != null && <span className="score">{score}</span>}
    </div>
  );
}

function PredictionPanel({
  match,
  teams,
  onClose,
}: {
  match: KnockoutMatch | null;
  teams: Record<string, TeamInfo>;
  onClose: () => void;
}) {
  if (!match) {
    return (
      <div className="stat-card !p-4 text-center text-sm text-[var(--text-muted)]">
        Toca cualquier cajita de la llave para ver su predicción del modelo.
      </div>
    );
  }

  const p = match.pred;
  const res = match.result;
  const homeName = match.home ?? match.home_label;
  const awayName = match.away ?? match.away_label;
  const probs = p
    ? [
        { key: "home", label: `${flagOf(teams, match.home)} ${homeName}`, value: p.p_home, color: "#1c3f94" },
        { key: "draw", label: "Empate", value: p.p_draw, color: "#777799" },
        { key: "away", label: `${flagOf(teams, match.away)} ${awayName}`, value: p.p_away, color: "#cf0a2c" },
      ].sort((a, b) => b.value - a.value)
    : [];
  const favorite = probs[0];

  return (
    <div className="stat-card !p-4 text-left">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <p className="text-[10px] uppercase tracking-[0.18em] mb-1" style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}>
            #{match.num} · {match.round_es || match.round} · {shortVenue(match.ground)} · {fmtDate(match.date)}
          </p>
          <h4 className="text-lg font-black">
            {flagOf(teams, match.home)} {homeName} <span className="text-[var(--text-muted)]">vs</span> {awayName} {flagOf(teams, match.away)}
          </h4>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="px-2 py-1 rounded-lg text-xs font-bold bg-white/5 text-[var(--text-muted)] hover:text-[var(--text)]"
        >
          Cerrar
        </button>
      </div>

      {res?.played && (
        <div className="mb-3 inline-flex rounded-full px-2 py-1 text-xs font-black bg-emerald-500/10 text-emerald-300">
          Final: {homeName} {res.home_score}-{res.away_score} {awayName}
        </div>
      )}

      {p ? (
        <div className="grid gap-3 md:grid-cols-[1.2fr_0.8fr]">
          <div>
            <div className="flex h-3 rounded-full overflow-hidden bg-white/5 mb-2">
              <div style={{ width: `${p.p_home * 100}%`, background: "#1c3f94" }} />
              <div style={{ width: `${p.p_draw * 100}%`, background: "#777799" }} />
              <div style={{ width: `${p.p_away * 100}%`, background: "#cf0a2c" }} />
            </div>
            <div className="space-y-2">
              {probs.map((item) => (
                <div key={item.key} className="grid grid-cols-[1fr_auto] gap-3 items-center text-sm">
                  <span className="truncate" style={{ color: item.color }}>{item.label}</span>
                  <span className="font-black tabular-nums">{pct(item.value)}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-lg border border-[var(--border-subtle)] bg-white/[0.03] p-3">
            <p className="text-[10px] uppercase tracking-[0.16em] mb-1" style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
              Lectura rápida
            </p>
            <p className="text-sm">
              Favorito: <span className="font-black" style={{ color: favorite?.color }}>{favorite?.label}</span> ({pct(favorite?.value)}).
            </p>
            {p.top_scorelines?.length ? (
              <div className="mt-2">
                <p className="text-xs mb-1 text-[var(--text-muted)]">Marcadores más probables</p>
                <div className="flex flex-wrap gap-1.5">
                  {p.top_scorelines.slice(0, 3).map((s) => (
                    <span key={`${s.home}-${s.away}-${s.prob}`} className="text-xs px-2 py-1 rounded-full bg-[var(--surface-2)] tabular-nums">
                      {s.home}-{s.away} · {pct(s.prob)}
                    </span>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      ) : (
        <p className="text-sm text-[var(--text-muted)]">
          Este cruce todavía depende de rondas anteriores. La predicción aparecerá cuando ambos equipos estén definidos.
        </p>
      )}

      {match.home && match.away && (
        <div className="mt-4 rounded-lg border border-[rgba(212,168,67,0.22)] bg-[rgba(212,168,67,0.04)] p-3">
          <p className="text-[10px] uppercase tracking-[0.16em] mb-2" style={{ fontFamily: "var(--font-mono)", color: "var(--wc-gold)" }}>
            Agentes expertos
          </p>
          <AgentDebatePanel homeTeam={match.home} awayTeam={match.away} variant="full" />
        </div>
      )}
    </div>
  );
}
