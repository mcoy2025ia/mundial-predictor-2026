"use client";

import { useState, useMemo, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  RadialBarChart, RadialBar, PolarAngleAxis,
  ResponsiveContainer, Tooltip,
} from "recharts";
import type { TeamInfo, Prediction, HistoricalMatch, LiveMatch } from "@/types";
import VsOrb from "@/components/ui/VsOrb";
import ProbBar from "@/components/ui/ProbBar";
import { staggerContainer, fadeUp, popIn } from "@/lib/animations";
import { fixturesOfTheDay } from "@/lib/live";
import { useLang } from "@/lib/i18n";

const TEAM_COLORS: Record<string, string> = {
  Argentina:              "#74ACDF",
  Brazil:                 "#009C3B",
  Colombia:               "#FCD116",
  Uruguay:                "#5EB6E4",
  Ecuador:                "#FFD100",
  Venezuela:              "#CF142B",
  Chile:                  "#D52B1E",
  Peru:                   "#D91023",
  Paraguay:               "#D52B1E",
  Bolivia:                "#F4E400",
  France:                 "#002395",
  Spain:                  "#AA151B",
  England:                "#CF0A2C",
  Portugal:               "#006600",
  Germany:                "#444455",
  Netherlands:            "#FF4F00",
  Belgium:                "#EF3340",
  Croatia:                "#D22D3D",
  Italy:                  "#003399",
  Switzerland:            "#D0021B",
  Sweden:                 "#006AA7",
  Norway:                 "#EF2B2D",
  Austria:                "#ED2939",
  Denmark:                "#C60C30",
  Poland:                 "#DC143C",
  Serbia:                 "#C6363C",
  Scotland:               "#003F87",
  "Czech Republic":       "#D7141A",
  Turkey:                 "#E30A17",
  "Bosnia and Herzegovina": "#002395",
  "United States":        "#1C3F94",
  Mexico:                 "#006847",
  Canada:                 "#FF0000",
  Panama:                 "#D21034",
  "Costa Rica":           "#002B7F",
  Honduras:               "#0073CF",
  Jamaica:                "#000000",
  Morocco:                "#C1272D",
  Senegal:                "#00853F",
  Nigeria:                "#008751",
  Ghana:                  "#006B3F",
  "Ivory Coast":          "#F77F00",
  Cameroon:               "#007A5E",
  Egypt:                  "#CE1126",
  Algeria:                "#006233",
  Tunisia:                "#E70013",
  "South Africa":         "#007A4D",
  "DR Congo":             "#007FFF",
  "Cape Verde":           "#003893",
  Japan:                  "#BC002D",
  "South Korea":          "#C60C30",
  Australia:              "#00843D",
  Iran:                   "#239F40",
  "Saudi Arabia":         "#006C35",
  Iraq:                   "#CE1126",
  Qatar:                  "#8D1B3D",
  Uzbekistan:             "#1EB53A",
  Jordan:                 "#007A3D",
  Curacao:                "#002B7F",
  "New Zealand":          "#00247D",
  Haiti:                  "#00209F",
};

function getTeamColor(name: string): string {
  return TEAM_COLORS[name] ?? "#6666AA";
}

function getPrediction(
  predictions: Record<string, Prediction>,
  home: string,
  away: string
): Prediction {
  if (predictions[`${home}|${away}`]) return predictions[`${home}|${away}`];
  const rev = predictions[`${away}|${home}`];
  if (rev) return { home_win: rev.away_win, draw: rev.draw, away_win: rev.home_win };
  return { home_win: 0.34, draw: 0.32, away_win: 0.34 };
}

function getWinnerKey(pred: Prediction): "home" | "draw" | "away" {
  if (pred.home_win >= pred.draw && pred.home_win >= pred.away_win) return "home";
  if (pred.away_win >= pred.draw && pred.away_win >= pred.home_win) return "away";
  return "draw";
}

interface Props {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  matches: HistoricalMatch[];
  liveMatches?: LiveMatch[];
}

/* ══════════════════════════════════════════════════════
   PREDICTOR PRINCIPAL
══════════════════════════════════════════════════════ */
function poissonPmf(k: number, lam: number): number {
  let f = 1;
  for (let i = 2; i <= k; i++) f *= i;
  return (Math.exp(-lam) * Math.pow(lam, k)) / f;
}

/**
 * Marcador más probable vía Poisson independiente (λ = promedio goles
 * anotados vs recibidos), condicionado al resultado que predijo el modelo.
 */
function mostLikelyScore(
  homeInfo: TeamInfo | undefined,
  awayInfo: TeamInfo | undefined,
  pred: Prediction
): { s1: number; s2: number } {
  const l1 = Math.max(0.2, ((homeInfo?.goals_scored ?? 1.3) + (awayInfo?.goals_conceded ?? 1.2)) / 2);
  const l2 = Math.max(0.2, ((awayInfo?.goals_scored ?? 1.3) + (homeInfo?.goals_conceded ?? 1.2)) / 2);
  const outcome =
    pred.home_win >= pred.draw && pred.home_win >= pred.away_win ? "home"
    : pred.away_win >= pred.draw ? "away" : "draw";

  let best = { s1: 1, s2: 1, p: -1 };
  for (let i = 0; i <= 5; i++) {
    for (let j = 0; j <= 5; j++) {
      const consistent = outcome === "home" ? i > j : outcome === "away" ? i < j : i === j;
      if (!consistent) continue;
      const p = poissonPmf(i, l1) * poissonPmf(j, l2);
      if (p > best.p) best = { s1: i, s2: j, p };
    }
  }
  return best;
}

export default function Predictor({ teams, predictions, matches, liveMatches }: Props) {
  const T = useLang();
  const teamList = useMemo(
    () => Object.entries(teams).sort((a, b) => a[0].localeCompare(b[0])),
    [teams]
  );

  const [home, setHome]           = useState("Colombia");
  const [away, setAway]           = useState("Portugal");
  const [predicted, setPredicted] = useState(false);
  const [loading, setLoading]     = useState(false);

  /* Partidos del día (fecha local). Solo fixtures con ambos equipos
     definidos en el modelo — descarta placeholders del knockout. */
  const todayStr = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
  const day = useMemo(() => {
    const { date, fixtures } = fixturesOfTheDay(liveMatches ?? [], todayStr);
    return { date, fixtures: fixtures.filter((f) => teams[f.team1] && teams[f.team2]) };
  }, [liveMatches, teams, todayStr]);

  /* Carga por defecto el primer partido pendiente del día: solo queda dar Predecir */
  const autoloaded = useRef(false);
  useEffect(() => {
    if (autoloaded.current || day.fixtures.length === 0) return;
    autoloaded.current = true;
    const next = day.fixtures.find((f) => f.score1 === null) ?? day.fixtures[0];
    setHome(next.team1);
    setAway(next.team2);
  }, [day]);

  const homeInfo  = teams[home];
  const awayInfo  = teams[away];
  const pred      = getPrediction(predictions, home, away);
  const homeColor = getTeamColor(home);
  const awayColor = getTeamColor(away);
  const winnerKey = getWinnerKey(pred);

  const donutData = [
    { name: `${homeInfo?.flag ?? ""} ${home}`, value: +(pred.home_win * 100).toFixed(1), fill: homeColor },
    { name: T.draw,                             value: +(pred.draw     * 100).toFixed(1), fill: "#666688" },
    { name: `${awayInfo?.flag ?? ""} ${away}`, value: +(pred.away_win * 100).toFixed(1), fill: awayColor },
  ];

  const h2h = useMemo(
    () =>
      matches
        .filter(
          (m) =>
            (m.home_team === home && m.away_team === away) ||
            (m.home_team === away && m.away_team === home)
        )
        .sort((a, b) => b.year - a.year)
        .slice(0, 6),
    [matches, home, away]
  );

  function handlePredict() {
    if (home === away) return;
    setLoading(true);
    setPredicted(false);
    setTimeout(() => {
      setLoading(false);
      setPredicted(true);
    }, 1400);
  }

  function handleSwap() {
    setHome(away);
    setAway(home);
    setPredicted(false);
  }

  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="visible" className="space-y-5">
      {/* ── Partidos del día: clic para cargarlos en el predictor ── */}
      {day.fixtures.length > 0 && (
        <motion.div
          variants={fadeUp}
          className="rounded-2xl p-4"
          style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="live-dot" />
            <span
              className="text-[10px] uppercase tracking-widest"
              style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
            >
              {day.date === todayStr ? T.todayTitle : T.nextMatchesTitle} ·{" "}
              {new Date(day.date + "T12:00:00").toLocaleDateString(T.locale, {
                weekday: "short", day: "numeric", month: "short",
              })}
            </span>
          </div>
          <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide">
            {day.fixtures.map((f) => {
              const isSel =
                (home === f.team1 && away === f.team2) ||
                (home === f.team2 && away === f.team1);
              const done = f.score1 !== null && f.score2 !== null;
              return (
                <button
                  key={`${f.team1}|${f.team2}`}
                  onClick={() => { setHome(f.team1); setAway(f.team2); setPredicted(false); }}
                  className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all"
                  style={{
                    background: isSel ? "rgba(212,168,67,0.12)" : "var(--color-arena-elevated)",
                    border: `1px solid ${isSel ? "rgba(212,168,67,0.45)" : "rgba(255,255,255,0.07)"}`,
                    color: "var(--color-ink-primary)",
                    fontFamily: "var(--font-body)",
                    cursor: "pointer",
                  }}
                >
                  <span>{teams[f.team1]?.flag} {f.team1}</span>
                  <span
                    className="tabular-nums"
                    style={{
                      fontFamily: "var(--font-mono)", fontSize: "0.7rem",
                      color: done ? "var(--color-wc-gold)" : "var(--color-ink-muted)",
                    }}
                  >
                    {done ? `${f.score1}–${f.score2}` : "vs"}
                  </span>
                  <span>{f.team2} {teams[f.team2]?.flag}</span>
                </button>
              );
            })}
          </div>
        </motion.div>
      )}

      {/* ── Tarjeta principal ── */}
      <motion.div variants={fadeUp} className="relative">
        <div className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none" aria-hidden>
          <motion.div
            className="absolute inset-0"
            animate={{ background: `radial-gradient(ellipse 45% 70% at 8% 50%, ${homeColor}1E 0%, transparent 70%)` }}
            transition={{ duration: 0.9, ease: "easeInOut" }}
          />
          <motion.div
            className="absolute inset-0"
            animate={{ background: `radial-gradient(ellipse 45% 70% at 92% 50%, ${awayColor}1E 0%, transparent 70%)` }}
            transition={{ duration: 0.9, ease: "easeInOut" }}
          />
        </div>

        <div
          className="relative rounded-2xl overflow-hidden"
          style={{
            background: "rgba(15,15,30,0.96)",
            border: "1px solid rgba(255,255,255,0.07)",
            boxShadow: "0 28px 72px rgba(0,0,0,0.75), inset 0 1px 0 rgba(255,255,255,0.06)",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 sm:px-6 pt-4 sm:pt-6 pb-3 sm:pb-4">
            <div className="flex items-center gap-3">
              <div className="w-0.5 h-5 rounded-full" style={{ background: "var(--color-wc-gold)" }} />
              <span
                className="text-[11px] tracking-widest uppercase"
                style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
              >
                {T.matchPredictor}
              </span>
            </div>
            <span
              className="text-[10px] tracking-wider hidden sm:block"
              style={{ fontFamily: "var(--font-mono)", color: "rgba(212,168,67,0.50)" }}
            >
              {T.wcTag}
            </span>
          </div>

          <div
            className="h-px mx-6 mb-5"
            style={{ background: "linear-gradient(90deg, transparent, rgba(212,168,67,0.20), transparent)" }}
          />

          {/* Selectores */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-3 px-3 sm:px-6 pb-4 sm:pb-6">
            <TeamPicker
              label={T.home}
              selected={home}
              teamList={teamList}
              info={homeInfo}
              onChange={(v) => { setHome(v); setPredicted(false); }}
              side="left"
            />
            <VsOrb isPredicted={predicted} onSwap={handleSwap} />
            <TeamPicker
              label={T.away}
              selected={away}
              teamList={teamList}
              info={awayInfo}
              onChange={(v) => { setAway(v); setPredicted(false); }}
              side="right"
            />
          </div>

          <div style={{ height: 1, background: "rgba(255,255,255,0.05)" }} />

          {/* Zona de resultados */}
          <div className="px-3 sm:px-6 py-4 sm:py-5" style={{ minHeight: 120 }}>
            <AnimatePresence mode="wait">
              {loading ? (
                <ScannerLoader key="loading" homeFlag={homeInfo?.flag} awayFlag={awayInfo?.flag} />
              ) : predicted ? (
                <ResultsZone
                  key="results"
                  pred={pred}
                  home={home}
                  away={away}
                  homeInfo={homeInfo}
                  awayInfo={awayInfo}
                  homeColor={homeColor}
                  awayColor={awayColor}
                  winnerKey={winnerKey}
                  donutData={donutData}
                />
              ) : (
                <IdleHint key="idle" />
              )}
            </AnimatePresence>
          </div>

          <div className="px-3 sm:px-6 pb-4 sm:pb-6">
            <PredictCTA onClick={handlePredict} disabled={loading || home === away} loading={loading} />
          </div>
        </div>
      </motion.div>

      {/* ── Marcador más probable (Poisson) ── */}
      <AnimatePresence>
        {predicted && (() => {
          const score = mostLikelyScore(homeInfo, awayInfo, pred);
          return (
            <motion.div
              variants={fadeUp} initial="hidden" animate="visible" exit="exit"
              className="rounded-2xl p-4 flex items-center gap-3 flex-wrap"
              style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              <span className="text-xs uppercase tracking-widest font-mono" style={{ color: "var(--color-ink-muted)" }}>
                {T.likelyScore}
              </span>
              <span className="score-final">
                {homeInfo?.flag} {score.s1}–{score.s2} {awayInfo?.flag}
              </span>
              <span className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
                {T.likelyScoreNote}
              </span>
            </motion.div>
          );
        })()}
      </AnimatePresence>

      {/* ── H2H ── */}
      <AnimatePresence>
        {predicted && (
          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="rounded-2xl p-5"
            style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
          >
            <h3
              className="text-sm mb-4 flex items-center gap-2 uppercase tracking-wider"
              style={{ fontFamily: "var(--font-heading)", fontWeight: 700, color: "var(--color-ink-secondary)" }}
            >
              <span>⚔️</span>
              <span>{T.h2hTitle}</span>
              <span
                className="font-normal text-[11px]"
                style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
              >
                ({h2h.length} {T.h2hMatches})
              </span>
            </h3>

            {h2h.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--color-ink-muted)" }}>
                {T.noH2H}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table>
                  <thead>
                    <tr>
                      {[T.year, T.home, T.scoreCol, T.away, T.winnerCol].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {h2h.map((m, i) => {
                      const winner =
                        m.outcome === "home_win" ? m.home_team
                        : m.outcome === "away_win" ? m.away_team
                        : null;
                      const isHomeWin = winner === home;
                      const wColor = isHomeWin ? homeColor : awayColor;
                      return (
                        <tr key={i}>
                          <td style={{ color: "var(--color-ink-muted)" }}>{m.year}</td>
                          <td>{teams[m.home_team]?.flag} {m.home_team}</td>
                          <td
                            className="tabular-nums"
                            style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}
                          >
                            {m.home_score}–{m.away_score}
                          </td>
                          <td>{teams[m.away_team]?.flag} {m.away_team}</td>
                          <td>
                            {winner ? (
                              <span
                                className="text-xs font-bold px-2 py-0.5 rounded-full"
                                style={{ background: `${wColor}20`, color: wColor }}
                              >
                                {teams[winner]?.flag} {winner}
                              </span>
                            ) : (
                              <span className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
                                {T.draw}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {predicted && (
        <motion.p
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="text-center text-xs"
          style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
        >
          ℹ️ {T.modelNote}
        </motion.p>
      )}
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   TEAM PICKER
══════════════════════════════════════════════════════ */
function TeamPicker({
  label, selected, teamList, info, onChange, side,
}: {
  label: string;
  selected: string;
  teamList: [string, TeamInfo][];
  info: TeamInfo | undefined;
  onChange: (v: string) => void;
  side: "left" | "right";
}) {
  const T     = useLang();
  const [open, setOpen]     = useState(false);
  const [search, setSearch] = useState("");
  const ref                 = useRef<HTMLDivElement>(null);
  const color               = getTeamColor(selected);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = teamList.filter(([name]) =>
    name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div ref={ref} className={`relative flex flex-col ${side === "left" ? "items-start" : "items-end"}`}>
      <span
        className="text-[10px] tracking-widest uppercase mb-2"
        style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
      >
        {label}
      </span>

      <motion.button
        onClick={() => setOpen(!open)}
        whileTap={{ scale: 0.96 }}
        className="w-full flex flex-col items-center gap-2 p-2 sm:p-4 rounded-2xl transition-all duration-300 focus:outline-none"
        style={{
          background: `linear-gradient(135deg, ${color}12 0%, var(--color-arena-card) 100%)`,
          border: `1px solid ${color}28`,
          boxShadow: open ? `0 0 20px ${color}20` : "none",
        }}
      >
        <motion.span
          key={selected}
          initial={{ scale: 0.5, opacity: 0, rotate: -12 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 20 }}
          className="text-4xl sm:text-5xl leading-none"
          style={{ filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.5))" }}
        >
          {info?.flag ?? "🏳️"}
        </motion.span>

        <div className="text-center">
          <p
            className="text-base leading-tight font-bold tracking-wide"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-ink-primary)" }}
          >
            {selected}
          </p>
          {info && (
            <p
              className="text-[10px] tracking-widest mt-0.5"
              style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
            >
              ELO {info.elo.toFixed(0)} · #{info.rank}
            </p>
          )}
        </div>

        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.18 }}
          className="text-[10px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          ▼
        </motion.span>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scaleY: 0.88 }}
            animate={{ opacity: 1, y: 0, scaleY: 1 }}
            exit={{ opacity: 0, y: -8, scaleY: 0.88 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            style={{ transformOrigin: "top" }}
            className={`absolute top-full mt-2 z-50 w-56 sm:w-64 max-w-[calc(100vw-2rem)] rounded-2xl overflow-hidden ${
              side === "left" ? "left-0" : "right-0"
            }`}
          >
            <div
              style={{
                background: "var(--color-arena-deep)",
                border: "1px solid rgba(255,255,255,0.10)",
                boxShadow: "0 24px 60px rgba(0,0,0,0.82)",
              }}
            >
              <div className="p-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <input
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={T.searchTeam}
                  className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none transition-colors"
                  style={{
                    background: "var(--color-arena-elevated)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    color: "var(--color-ink-primary)",
                    fontFamily: "var(--font-body)",
                  }}
                />
              </div>

              <div className="max-h-60 overflow-y-auto">
                {filtered.length === 0 ? (
                  <p className="text-center text-sm py-6" style={{ color: "var(--color-ink-muted)" }}>
                    {T.noResults}
                  </p>
                ) : (
                  filtered.map(([name, t]) => {
                    const tc = getTeamColor(name);
                    return (
                      <motion.button
                        key={name}
                        whileHover={{ backgroundColor: "rgba(255,255,255,0.038)" }}
                        onClick={() => { onChange(name); setOpen(false); setSearch(""); }}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
                        style={{ backgroundColor: name === selected ? "rgba(255,255,255,0.04)" : "transparent" }}
                      >
                        <span className="text-2xl shrink-0">{t.flag}</span>
                        <div className="flex-1 min-w-0">
                          <p
                            className="text-sm truncate"
                            style={{ color: "var(--color-ink-primary)", fontFamily: "var(--font-body)" }}
                          >
                            {name}
                          </p>
                          <p
                            className="text-[10px]"
                            style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
                          >
                            {t.confederation} · {T.group} {t.group}
                          </p>
                        </div>
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-md shrink-0"
                          style={{
                            fontFamily: "var(--font-mono)",
                            background: `${tc}18`,
                            color: tc,
                            border: `1px solid ${tc}28`,
                          }}
                        >
                          {t.elo.toFixed(0)}
                        </span>
                      </motion.button>
                    );
                  })
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   ESTADOS DE LA ZONA DE RESULTADOS
══════════════════════════════════════════════════════ */
function IdleHint() {
  const T = useLang();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex flex-col items-center justify-center gap-2 py-5"
    >
      <span className="text-3xl">⚽</span>
      <p className="text-sm text-center" style={{ fontFamily: "var(--font-body)", color: "var(--color-ink-muted)" }}>
        {T.selectIdle}
      </p>
    </motion.div>
  );
}

function ScannerLoader({ homeFlag, awayFlag }: { homeFlag?: string; awayFlag?: string }) {
  const T = useLang();
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col gap-4">
      <div
        className="flex items-center justify-center gap-4 text-lg tracking-wider"
        style={{ fontFamily: "var(--font-heading)", fontWeight: 700, color: "var(--color-ink-secondary)" }}
      >
        <span>{homeFlag}</span>
        <motion.span
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 0.9, repeat: Infinity }}
          style={{ color: "var(--color-wc-gold)" }}
        >
          ···
        </motion.span>
        <span>{awayFlag}</span>
      </div>

      <div
        className="relative h-12 rounded-xl overflow-hidden"
        style={{ background: "var(--color-arena-elevated)", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        <motion.div
          className="absolute left-0 right-0 h-px"
          style={{ background: "linear-gradient(90deg, transparent, rgba(212,168,67,0.85), transparent)" }}
          animate={{ y: [0, 46] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
        />
        <div className="flex items-center justify-center h-full">
          <span className="text-[10px] tracking-widest uppercase" style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}>
            {T.scannerText}
          </span>
        </div>
      </div>

      <div className="space-y-2.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 h-4 rounded shimmer-skeleton" />
            <div className="flex-1 h-9 rounded-xl shimmer-skeleton" />
            <div className="w-10 h-5 rounded shimmer-skeleton" />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function ResultsZone({
  pred, home, away, homeInfo, awayInfo,
  homeColor, awayColor, winnerKey, donutData,
}: {
  pred: Prediction;
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  homeColor: string; awayColor: string;
  winnerKey: "home" | "draw" | "away";
  donutData: { name: string; value: number; fill: string }[];
}) {
  const T = useLang();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Donut chart */}
        <div
          className="rounded-xl p-4 flex flex-col items-center"
          style={{ background: "var(--color-arena-elevated)" }}
        >
          <p
            className="text-[10px] uppercase tracking-widest mb-3"
            style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
          >
            {T.probabilities}
          </p>
          <ResponsiveContainer width="100%" height={176}>
            <RadialBarChart innerRadius="50%" outerRadius="88%" data={donutData} startAngle={90} endAngle={-270}>
              <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
              <RadialBar dataKey="value" cornerRadius={5} />
              <Tooltip
                formatter={(v: number) => `${(+v).toFixed(1)}%`}
                contentStyle={{
                  background: "var(--color-arena-deep)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--color-ink-primary)",
                }}
              />
            </RadialBarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 flex-wrap justify-center mt-1">
            {donutData.map((d) => (
              <span key={d.name} className="flex items-center gap-1.5 text-xs" style={{ fontFamily: "var(--font-body)", color: "var(--color-ink-secondary)" }}>
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.fill }} />
                {d.name}
              </span>
            ))}
          </div>
        </div>

        {/* Barras animadas */}
        <div className="flex flex-col justify-center space-y-3.5">
          <ProbBar pct={pred.home_win} color={homeColor} label={`${homeInfo?.flag ?? ""} ${home}`} isWinner={winnerKey === "home"} delay={0} />
          <ProbBar pct={pred.draw}     color="#777799"   label={T.draw}                               isWinner={winnerKey === "draw"} delay={0.12} />
          <ProbBar pct={pred.away_win} color={awayColor} label={`${awayInfo?.flag ?? ""} ${away}`} isWinner={winnerKey === "away"} delay={0.24} />
        </div>
      </div>

      {/* Cards de ELO */}
      <div className="grid grid-cols-2 gap-4">
        {[
          { team: home, info: homeInfo, color: homeColor },
          { team: away, info: awayInfo, color: awayColor },
        ].map(({ team, info, color }) => (
          <motion.div
            key={team}
            variants={popIn}
            initial="hidden"
            animate="visible"
            whileHover={{ y: -3, scale: 1.02 }}
            transition={{ type: "spring", stiffness: 300, damping: 22 }}
            className="rounded-xl p-4 text-center"
            style={{
              background: `linear-gradient(135deg, ${color}0D 0%, var(--color-arena-card) 100%)`,
              border: `1px solid ${color}22`,
            }}
          >
            <div className="text-3xl mb-1.5">{info?.flag}</div>
            <div className="text-sm font-bold tracking-wide" style={{ fontFamily: "var(--font-heading)", color: "var(--color-ink-primary)" }}>
              {team}
            </div>
            <div className="text-3xl mt-2 leading-none tabular-nums" style={{ fontFamily: "var(--font-display)", color }}>
              {info?.elo.toFixed(0)}
            </div>
            <div className="text-[10px] mt-0.5" style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}>
              {T.eloLabel}{info?.rank}
            </div>
            <div className="text-[10px] mt-2" style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}>
              {info?.goals_scored.toFixed(2)} {T.goalsScored}
            </div>
            <div className="text-[10px]" style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}>
              {info?.wc_matches} {T.wcMatches}
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   BOTÓN CTA
══════════════════════════════════════════════════════ */
function PredictCTA({ onClick, disabled, loading }: { onClick: () => void; disabled: boolean; loading: boolean }) {
  const T = useLang();
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { scale: 1.02, y: -2 }}
      whileTap={disabled ? {} : { scale: 0.97, y: 0 }}
      className="relative w-full h-14 rounded-xl overflow-hidden"
      style={{
        fontFamily: "var(--font-heading)",
        fontWeight: 700,
        fontSize: "1.1rem",
        letterSpacing: "0.06em",
        textTransform: "uppercase",
        background: disabled
          ? "rgba(212,168,67,0.16)"
          : "linear-gradient(135deg, #D4A843 0%, #F5CC6A 45%, #D4A843 100%)",
        color: disabled ? "rgba(212,168,67,0.40)" : "#07070F",
        boxShadow: disabled ? "none" : "0 8px 28px rgba(212,168,67,0.30), inset 0 1px 0 rgba(255,255,255,0.20)",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background 0.3s, box-shadow 0.3s",
      }}
    >
      {!disabled && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.22) 50%, transparent 100%)" }}
          initial={{ x: "-100%" }}
          whileHover={{ x: "200%" }}
          transition={{ duration: 0.55 }}
        />
      )}

      <span className="relative z-10 flex items-center justify-center gap-2">
        {loading ? (
          <>
            <motion.span
              animate={{ rotate: 360 }}
              transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
              className="inline-block w-4 h-4 rounded-full border-2 border-current border-t-transparent"
            />
            {T.calculating}
          </>
        ) : (
          T.predictBtn
        )}
      </span>
    </motion.button>
  );
}
