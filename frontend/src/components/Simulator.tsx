"use client";

import { useState, useTransition } from "react";
import type { SimResult } from "@/types";
import { runMonteCarlo } from "@/lib/simulator";
import type { TeamInfo, Prediction, FixedResults } from "@/types";
import { useLang } from "@/lib/i18n";

interface Props {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  groups: Record<string, string[]>;
  fixedResults?: FixedResults;
}

const LATAM = new Set(["Colombia", "Argentina", "Brazil", "Uruguay", "Ecuador", "Venezuela", "Mexico", "Chile", "Peru"]);

function pct(v: number) { return `${(v * 100).toFixed(1)}%`; }

function PctBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-16 rounded-full bg-white/5 overflow-hidden shrink-0">
        <div className="prob-bar h-full rounded-full" style={{ width: `${value * 100}%`, background: color }} />
      </div>
      <span className="tabular-nums text-xs">{pct(value)}</span>
    </div>
  );
}

type ViewMode = "knockout" | "groups";

export default function SimulatorTab({ teams, predictions, groups, fixedResults }: Props) {
  const T = useLang();
  const [n, setN]         = useState(1000);
  const [filter, setFilter] = useState("all");
  const [view, setView]   = useState<ViewMode>("knockout");
  const [results, setResults] = useState<SimResult[] | null>(null);
  const [isPending, startTransition] = useTransition();

  const knockoutStages = [
    { key: "r32"      as keyof SimResult, label: T.r32      },
    { key: "r16"      as keyof SimResult, label: T.r16      },
    { key: "qf"       as keyof SimResult, label: T.qf       },
    { key: "sf"       as keyof SimResult, label: T.sf       },
    { key: "final"    as keyof SimResult, label: T.final    },
    { key: "champion" as keyof SimResult, label: T.champion },
  ];

  const groupStages = [
    { key: "first"  as keyof SimResult, label: T.firstPlace  },
    { key: "second" as keyof SimResult, label: T.secondPlace },
    { key: "third"  as keyof SimResult, label: T.thirdPlace  },
    { key: "fourth" as keyof SimResult, label: T.eliminated  },
  ];

  function simulate() {
    startTransition(() => {
      const r = runMonteCarlo(predictions, groups, teams, n, fixedResults);
      setResults(r);
    });
  }

  const nFixed = fixedResults?.size ?? 0;

  const filtered =
    results?.filter((r) => {
      if (filter === "all") return true;
      if (filter === "americas") return r.confederation === "CONMEBOL" || r.confederation === "CONCACAF";
      if (filter === "europe") return r.confederation === "UEFA";
      if (filter === "africa") return r.confederation === "CAF";
      if (filter === "asia") return r.confederation === "AFC" || r.confederation === "AFC/OFC" || r.confederation === "OFC";
      return true;
    }) ?? null;

  return (
    <div className="space-y-6">
      {/* Resultados reales fijados */}
      {nFixed > 0 && (
        <div className="flex items-center gap-2 text-xs rounded-md px-3 py-2"
          style={{ background: "rgba(207,10,44,0.08)", border: "1px solid rgba(207,10,44,0.3)" }}>
          <span className="live-dot" />
          <span className="font-bold text-[var(--text)]">{nFixed} {T.liveFixedCount}</span>
          <span className="text-[var(--text-muted)]">· {T.liveFixedNote}</span>
        </div>
      )}

      {/* Groups overview */}
      <div>
        <h3 className="text-sm font-bold uppercase tracking-widest text-[var(--text-muted)] mb-4">
          {T.simTitle}
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
          {Object.entries(groups).map(([g, gteams]) => (
            <div key={g} className="stat-card p-3">
              <div className="text-xs font-black text-[var(--wc-red)] mb-2">{T.group} {g}</div>
              <div className="space-y-1">
                {gteams.map((t) => (
                  <div key={t} className="flex items-center justify-between text-xs">
                    <span>{teams[t]?.flag} {t}</span>
                    <span className="text-[var(--text-muted)] tabular-nums">{teams[t]?.elo.toFixed(0)}</span>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="border-t border-[var(--border-subtle)]" />

      {/* Controls */}
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="text-xs text-[var(--text-muted)] uppercase tracking-widest block mb-2">
            {T.simCount}
          </label>
          <div className="flex gap-2">
            {[500, 1000, 2000, 5000].map((v) => (
              <button
                key={v}
                onClick={() => setN(v)}
                className={`px-3 py-1.5 rounded-lg text-sm font-semibold transition-all ${
                  n === v
                    ? "bg-[var(--wc-red)] text-white"
                    : "bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
                }`}
              >
                {v.toLocaleString()}
              </button>
            ))}
          </div>
        </div>

        <button
          onClick={simulate}
          disabled={isPending}
          className="px-8 py-3 rounded-xl font-bold text-base bg-[var(--wc-red)]
                     hover:brightness-110 active:scale-[.98] transition-all
                     shadow-lg shadow-red-900/30 disabled:opacity-60 disabled:cursor-wait"
        >
          {isPending ? T.simulating : T.simBtn}
        </button>
      </div>

      {/* Results */}
      {filtered && (
        <div className="space-y-4 animate-in fade-in slide-in-from-bottom-3 duration-400">
          {/* Filter + view toggle */}
          <div className="flex flex-wrap gap-3 items-center justify-between">
            <div className="flex flex-wrap gap-2">
              {[
                { key: "all",      label: T.allTeams           },
                { key: "americas", label: T.continentAmericas  },
                { key: "europe",   label: T.continentEurope    },
                { key: "africa",   label: T.continentAfrica    },
                { key: "asia",     label: T.continentAsia      },
              ].map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setFilter(key)}
                  className={`px-3 py-1 rounded-lg text-xs font-semibold transition-all ${
                    filter === key
                      ? "bg-[var(--wc-gold)] text-black"
                      : "bg-[var(--surface-2)] text-[var(--text-muted)] hover:text-[var(--text)]"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>
            <div className="flex gap-1 bg-[var(--surface-2)] rounded-lg p-1">
              {(["knockout", "groups"] as const).map((v) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`px-3 py-1 rounded-md text-xs font-semibold transition-all ${
                    view === v ? "bg-[var(--wc-red)] text-white" : "text-[var(--text-muted)]"
                  }`}
                >
                  {v === "knockout" ? T.knockoutView : T.groupsView}
                </button>
              ))}
            </div>
          </div>

          {/* Champion bars */}
          {view === "knockout" && (
            <div className="stat-card">
              <h3 className="font-bold text-sm mb-4">
                {T.winChamp} ({n.toLocaleString()} {T.simCount.toLowerCase()})
              </h3>
              <div className="space-y-2">
                {filtered.slice(0, 15).map((r) => {
                  const isLatam = LATAM.has(r.team);
                  return (
                    <div
                      key={r.team}
                      className="flex items-center gap-3 py-1 rounded-lg px-2 transition-colors hover:bg-white/2"
                    >
                      <span className="w-36 text-sm truncate flex items-center gap-2">
                        {r.flag} {r.team}
                      </span>
                      <div className="flex-1 h-4 rounded-full bg-white/5 overflow-hidden">
                        <div
                          className="h-full rounded-full transition-all duration-700"
                          style={{
                            width: `${Math.min((r.champion / (filtered[0]?.champion || 0.01)) * 100, 100)}%`,
                            background: isLatam
                              ? "linear-gradient(90deg,#c8102e,#ff6b6b)"
                              : "linear-gradient(90deg,#003087,#6699ff)",
                          }}
                        />
                      </div>
                      <span className="w-14 text-right text-sm font-bold tabular-nums">
                        {pct(r.champion)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Full table — knockout view */}
          {view === "knockout" && (
            <div className="stat-card overflow-x-auto">
              <table>
                <thead>
                  <tr>
                    <th>{T.colTeam}</th>
                    <th>{T.group}</th>
                    {knockoutStages.map((s) => (
                      <th key={s.key as string} className="text-right">{s.label}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.team} className={LATAM.has(r.team) ? "bg-yellow-500/5" : ""}>
                      <td>
                        <span className="flex items-center gap-2">
                          {r.flag} {r.team}
                        </span>
                      </td>
                      <td className="text-[var(--text-muted)]">{r.group}</td>
                      {knockoutStages.map((s) => (
                        <td key={s.key as string} className="text-right">
                          <PctBar
                            value={r[s.key] as number}
                            color={LATAM.has(r.team) ? "#c8102e" : "#6699ff"}
                          />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Groups view */}
          {view === "groups" && (
            <div className="stat-card overflow-x-auto">
              <h3 className="font-bold text-sm mb-4">
                {T.simGroupTitle} ({n.toLocaleString()} {T.simCount.toLowerCase()})
              </h3>
              <table>
                <thead>
                  <tr>
                    <th>{T.colTeam}</th>
                    <th>{T.group}</th>
                    {groupStages.map((s) => (
                      <th key={s.key as string} className="text-right">{s.label}</th>
                    ))}
                    <th className="text-right">{T.classifies}</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered
                    .slice()
                    .sort((a, b) => a.group.localeCompare(b.group) || b.first - a.first)
                    .map((r) => (
                      <tr key={r.team} className={LATAM.has(r.team) ? "bg-yellow-500/5" : ""}>
                        <td>
                          <span className="flex items-center gap-2">
                            {r.flag} {r.team}
                          </span>
                        </td>
                        <td className="text-[var(--text-muted)]">{r.group}</td>
                        <td className="text-right font-bold" style={{ color: "var(--wc-red)" }}>
                          {pct(r.first)}
                        </td>
                        <td className="text-right text-[var(--text-muted)]">{pct(r.second)}</td>
                        <td className="text-right text-[var(--text-muted)]">{pct(r.third)}</td>
                        <td className="text-right" style={{ color: "#ef4444aa" }}>{pct(r.fourth)}</td>
                        <td className="text-right">
                          <PctBar
                            value={r.r32}
                            color={LATAM.has(r.team) ? "#c8102e" : "#6699ff"}
                          />
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
              <p className="text-xs text-[var(--text-muted)] mt-2">{T.simGroupNote}</p>
            </div>
          )}

          <p className="text-xs text-[var(--text-muted)] text-center">{T.latamHighlight}</p>
        </div>
      )}
    </div>
  );
}
