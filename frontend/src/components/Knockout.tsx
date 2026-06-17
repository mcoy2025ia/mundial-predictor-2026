"use client";

import { useState, useEffect, useTransition, useMemo } from "react";
import type { TeamInfo, Prediction, SimResult } from "@/types";
import { runMonteCarlo } from "@/lib/simulator";
import { useLang } from "@/lib/i18n";

interface Props {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  groups: Record<string, string[]>;
}

const LATAM = new Set([
  "Colombia", "Argentina", "Brazil", "Uruguay",
  "Ecuador", "Venezuela", "Mexico", "Chile", "Peru", "Paraguay",
]);

const N_SIMS = 10_000;

function pct(v: number, decimals = 1) {
  return `${(v * 100).toFixed(decimals)}%`;
}

export default function Knockout({ teams, predictions, groups }: Props) {
  const T = useLang();

  const ROUNDS = useMemo(() => [
    { key: "r32"      as keyof SimResult, label: T.r32,       subtitle: T.roundOf32,     nTeams: 32, accent: "#4a4a8a" },
    { key: "r16"      as keyof SimResult, label: T.r16,       subtitle: T.roundOf16,     nTeams: 16, accent: "#1c3f94" },
    { key: "qf"       as keyof SimResult, label: T.qf,        subtitle: T.quarterFinal,  nTeams:  8, accent: "#7b1c94" },
    { key: "sf"       as keyof SimResult, label: T.sf,        subtitle: T.semiFinal,     nTeams:  4, accent: "#cf0a2c" },
    { key: "final"    as keyof SimResult, label: T.final,     subtitle: T.final,         nTeams:  2, accent: "#d4a843" },
    { key: "champion" as keyof SimResult, label: T.champion,  subtitle: T.worldChampion, nTeams:  1, accent: "#f5cc6a" },
  // eslint-disable-next-line react-hooks/exhaustive-deps
  ], [T.r32, T.r16, T.qf, T.sf, T.final, T.champion]);

  const [results, setResults]     = useState<SimResult[] | null>(null);
  const [isPending, startTransition] = useTransition();
  const [selected, setSelected]   = useState<keyof SimResult>("r16");
  const [confFilter, setConfFilter] = useState("all");

  useEffect(() => {
    startTransition(() => {
      setResults(runMonteCarlo(predictions, groups, teams, N_SIMS));
    });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const round = ROUNDS.find((r) => r.key === selected) ?? ROUNDS[1];

  const sorted = useMemo(() => {
    if (!results) return [];
    let base = [...results];
    if (confFilter === "americas") {
      base = base.filter((r) => r.confederation === "CONMEBOL" || r.confederation === "CONCACAF");
    } else if (confFilter === "europe") {
      base = base.filter((r) => r.confederation === "UEFA");
    } else if (confFilter === "africa") {
      base = base.filter((r) => r.confederation === "CAF");
    } else if (confFilter === "asia") {
      base = base.filter((r) => r.confederation === "AFC" || r.confederation === "OFC" || r.confederation === "AFC/OFC");
    }
    return base.sort((a, b) => (b[round.key] as number) - (a[round.key] as number));
  }, [results, round, confFilter]);

  const maxVal = (sorted[0]?.[round.key] as number) || 0.01;

  return (
    <div className="space-y-6">
      {/* Round pills */}
      <div className="flex flex-wrap gap-2 justify-center">
        {ROUNDS.map((r) => (
          <button
            key={r.key as string}
            onClick={() => setSelected(r.key)}
            className={`px-4 py-2 rounded-xl text-sm font-bold transition-all ${
              selected === r.key
                ? "text-white shadow-lg shadow-red-900/30"
                : "bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
            style={selected === r.key ? { background: r.accent } : {}}
          >
            {r.label}
          </button>
        ))}
      </div>

      {/* Continent filter */}
      <div className="flex flex-wrap gap-2 justify-center">
        {[
          { key: "all",     label: T.allConf            },
          { key: "americas",label: T.continentAmericas  },
          { key: "europe",  label: T.continentEurope    },
          { key: "africa",  label: T.continentAfrica    },
          { key: "asia",    label: T.continentAsia      },
        ].map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setConfFilter(key)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
              confFilter === key
                ? "bg-[var(--wc-gold)] text-black"
                : "bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Loading */}
      {isPending && (
        <div className="flex flex-col items-center py-16 gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-[var(--wc-red)] border-t-transparent animate-spin" />
          <p className="text-[var(--text-muted)] text-sm">
            {T.calculatingTourneys.replace("{n}", N_SIMS.toLocaleString())}
          </p>
        </div>
      )}

      {/* Results */}
      {results && !isPending && (
        <div className="space-y-4 animate-in fade-in duration-300">
          <div className="text-center">
            <h3 className="text-2xl font-black mb-1" style={{ color: round.accent }}>
              {round.subtitle}
            </h3>
            <p className="text-sm text-[var(--text-muted)]">
              {T.probabilityNote} · {N_SIMS.toLocaleString()} {T.simCount.toLowerCase()} Monte Carlo
            </p>
          </div>

          {/* Podium */}
          {round.nTeams <= 4 && sorted.length <= 6 && (
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-2">
              {sorted.slice(0, round.nTeams === 1 ? 4 : round.nTeams).map((r, i) => {
                const val = r[round.key] as number;
                return (
                  <div key={r.team} className="stat-card text-center">
                    <div className="text-3xl mb-1">{r.flag}</div>
                    <div className="font-bold text-sm">{r.team}</div>
                    <div className="text-3xl font-black mt-2" style={{ color: round.accent }}>
                      {pct(val, 0)}
                    </div>
                    <div className="text-xs text-[var(--text-muted)] mt-0.5">
                      {T.group} {r.group} · ELO {r.elo.toFixed(0)}
                    </div>
                    {i === 0 && (
                      <div
                        className="mt-2 text-xs font-bold px-2 py-0.5 rounded-full inline-block"
                        style={{ background: `${round.accent}25`, color: round.accent }}
                      >
                        {T.favoritoLabel}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Full ranking list */}
          <div className="stat-card space-y-1.5 text-left">
            <div className="flex items-center gap-2 mb-3 pb-2 border-b border-[var(--border-subtle)]">
              <span className="text-sm font-bold">{T.rankingFull}</span>
              <span className="text-xs text-[var(--text-muted)]">({sorted.length} {T.teamsUnit})</span>
            </div>
            {sorted.map((r, i) => {
              const val = r[round.key] as number;
              const isLatam = LATAM.has(r.team);

              return (
                <div
                  key={r.team}
                  className="flex items-center gap-3 py-1.5 px-2 rounded-lg transition-colors hover:bg-white/2"
                >
                  <span className="w-5 text-xs text-[var(--text-muted)] text-right tabular-nums shrink-0">
                    {i + 1}
                  </span>
                  <span className="flex items-center gap-1.5 w-28 sm:w-40 shrink-0">
                    <span className="text-base">{r.flag}</span>
                    <span className={`text-xs sm:text-sm truncate ${isLatam ? "font-semibold" : ""}`}>
                      {r.team}
                    </span>
                  </span>
                  <span className="text-xs text-[var(--text-muted)] w-8 shrink-0">{r.group}</span>
                  <span className="text-xs text-[var(--text-muted)] w-12 tabular-nums shrink-0 hidden sm:block">
                    {r.elo.toFixed(0)}
                  </span>
                  <div className="flex-1 h-3 rounded-full bg-white/5 overflow-hidden">
                    <div
                      className="h-full rounded-full transition-all duration-700"
                      style={{
                        width: `${(val / maxVal) * 100}%`,
                        background: isLatam
                          ? "linear-gradient(90deg,#c8102e,#ff4d6d)"
                          : `linear-gradient(90deg,${round.accent}cc,${round.accent})`,
                      }}
                    />
                  </div>
                  <span className="w-14 text-right text-sm font-bold tabular-nums shrink-0">
                    {pct(val)}
                  </span>
                </div>
              );
            })}
          </div>

          <FunnelSummary results={results} />
        </div>
      )}
    </div>
  );
}

function FunnelSummary({ results }: { results: SimResult[] }) {
  const T = useLang();

  const ROUNDS_STATIC = [
    { key: "r32"      as keyof SimResult, label: T.r32,      accent: "#4a4a8a" },
    { key: "r16"      as keyof SimResult, label: T.r16,      accent: "#1c3f94" },
    { key: "qf"       as keyof SimResult, label: T.qf,       accent: "#7b1c94" },
    { key: "sf"       as keyof SimResult, label: T.sf,       accent: "#cf0a2c" },
    { key: "final"    as keyof SimResult, label: T.final,    accent: "#d4a843" },
    { key: "champion" as keyof SimResult, label: T.champion, accent: "#f5cc6a" },
  ];

  const topPerRound = ROUNDS_STATIC.map((r) => {
    const best = [...results]
      .sort((a, b) => (b[r.key] as number) - (a[r.key] as number))
      .slice(0, 3);
    return { ...r, teams: best };
  });

  return (
    <div className="stat-card text-left">
      <h4 className="font-bold text-sm mb-4 text-[var(--text-muted)] uppercase tracking-widest">
        {T.funnelTitle}
      </h4>
      <div className="space-y-3">
        {topPerRound.map((r) => (
          <div key={r.key as string} className="flex items-center gap-3">
            <span className="text-xs font-bold w-16 shrink-0 text-right" style={{ color: r.accent }}>
              {r.label}
            </span>
            <div className="flex gap-2 flex-wrap">
              {r.teams.map((t) => (
                <span
                  key={t.team}
                  className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full"
                  style={{
                    background: `${r.accent}18`,
                    border: `1px solid ${r.accent}30`,
                    color: "var(--text)",
                  }}
                >
                  {t.flag} {t.team}{" "}
                  <span style={{ color: r.accent, fontWeight: 700 }}>
                    {pct(t[r.key] as number, 0)}
                  </span>
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
      <p className="text-xs text-[var(--text-muted)] mt-4">
        {T.latamNote.replace("{n}", N_SIMS.toLocaleString())}
      </p>
    </div>
  );
}
