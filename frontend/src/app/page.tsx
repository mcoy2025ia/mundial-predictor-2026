"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type {
  TeamInfo, Prediction, HistoricalMatch, SiteStats, FixedResults,
  Goalscorer, GroupMatch, GroupStandingEntry, LiveMatch, QatarBacktest,
} from "@/types";
import { LangContext, type Lang } from "@/lib/i18n";
import {
  buildFixedResults, buildLiveStats, buildScoreMap, buildVerdicts,
  fetchLiveMatches, type LiveStats,
} from "@/lib/live";
import Predictor      from "@/components/Predictor";
import SimulatorTab   from "@/components/Simulator";
import FunFacts       from "@/components/FunFacts";
import Groups         from "@/components/Groups";
import Knockout       from "@/components/Knockout";
import Glossary       from "@/components/Glossary";
import LiveTournament from "@/components/LiveTournament";

/* ─────────────────────────────────────────────────────────────
   UI DEL SHELL (hero, navbar, tabs, footer)
───────────────────────────────────────────────────────────── */
const SHELL = {
  es: {
    navLabel:   "Predictor ML",
    weAre26:    "WE ARE 26",
    eyebrow:    "Análisis con Machine Learning",
    subtitle:   "Probabilidades para las 48 selecciones del Mundial 2026, calculadas con un modelo XGBoost calibrado sobre 964 partidos mundialistas, ratings ELO históricos y simulación Monte Carlo.",
    tabs:       [
      { id: "envivo",        label: "En Vivo"        },
      { id: "predictor",     label: "Predictor"      },
      { id: "grupos",        label: "Grupos"         },
      { id: "proyecciones",  label: "Proyecciones"   },
      { id: "curiosidades",  label: "Stats"          },
      { id: "glosario",      label: "Glosario"       },
    ],
    projByRound: "Por ronda",
    projSim:     "Simulador",
    loading:    "Cargando datos del modelo…",
    footerBy:   "por",
    footerNote: "Modelo entrenado hasta Qatar 2022 · No afiliado a FIFA",
    kickoffIn:  "El torneo arranca en",
    liveNow:    "Torneo en vivo",
    played:     "partidos",
    goalsLabel: "goles",
    perMatch:   "/partido",
    modelTag:   "Modelo",
    hitsLabel:  "aciertos",
    lastLabel:  "Último",
    daysSuffix: "d",
  },
  en: {
    navLabel:   "ML Predictor",
    weAre26:    "WE ARE 26",
    eyebrow:    "Machine Learning Analysis",
    subtitle:   "Probabilities for all 48 teams at the 2026 World Cup, computed with a calibrated XGBoost model trained on 964 World Cup matches, historical ELO ratings and Monte Carlo simulation.",
    tabs:       [
      { id: "envivo",        label: "Live"          },
      { id: "predictor",     label: "Predictor"     },
      { id: "grupos",        label: "Groups"        },
      { id: "proyecciones",  label: "Projections"   },
      { id: "curiosidades",  label: "Stats"         },
      { id: "glosario",      label: "Glossary"      },
    ],
    projByRound: "By round",
    projSim:     "Simulator",
    loading:    "Loading model data…",
    footerBy:   "by",
    footerNote: "Model trained up to Qatar 2022 · Not affiliated with FIFA",
    kickoffIn:  "Tournament kicks off in",
    liveNow:    "Tournament live",
    played:     "matches",
    goalsLabel: "goals",
    perMatch:   "/match",
    modelTag:   "Model",
    hitsLabel:  "correct",
    lastLabel:  "Latest",
    daysSuffix: "d",
  },
  pt: {
    navLabel:   "Preditor ML",
    weAre26:    "WE ARE 26",
    eyebrow:    "Análise com Machine Learning",
    subtitle:   "Probabilidades para as 48 seleções da Copa 2026, calculadas com um modelo XGBoost calibrado sobre 964 jogos de Copa, ratings ELO históricos e simulação Monte Carlo.",
    tabs:       [
      { id: "envivo",        label: "Ao Vivo"         },
      { id: "predictor",     label: "Preditor"        },
      { id: "grupos",        label: "Grupos"          },
      { id: "proyecciones",  label: "Projeções"       },
      { id: "curiosidades",  label: "Stats"           },
      { id: "glosario",      label: "Glossário"       },
    ],
    projByRound: "Por fase",
    projSim:     "Simulador",
    loading:    "Carregando dados do modelo…",
    footerBy:   "por",
    footerNote: "Modelo treinado até o Qatar 2022 · Não afiliado à FIFA",
    kickoffIn:  "O torneio começa em",
    liveNow:    "Torneio ao vivo",
    played:     "jogos",
    goalsLabel: "gols",
    perMatch:   "/jogo",
    modelTag:   "Modelo",
    hitsLabel:  "acertos",
    lastLabel:  "Último",
    daysSuffix: "d",
  },
} as const;

type TabId = "envivo" | "predictor" | "grupos" | "proyecciones" | "curiosidades" | "glosario";

/* ─────────────────────────────────────────────────────────────
   PAGE
───────────────────────────────────────────────────────────── */
export default function Home() {
  const [lang,  setLang]  = useState<Lang>("es");
  const [tab,   setTab]   = useState<TabId>("envivo");

  const [teams,          setTeams]          = useState<Record<string, TeamInfo> | null>(null);
  const [predictions,    setPredictions]    = useState<Record<string, Prediction> | null>(null);
  const [groups,         setGroups]         = useState<Record<string, string[]> | null>(null);
  const [matches,        setMatches]        = useState<HistoricalMatch[]>([]);
  const [stats,          setStats]          = useState<SiteStats | null>(null);
  const [goalscorers,    setGoalscorers]    = useState<Goalscorer[]>([]);
  const [groupMatches,   setGroupMatches]   = useState<Record<string, GroupMatch[]> | null>(null);
  const [groupStandings, setGroupStandings] = useState<Record<string, GroupStandingEntry[]> | null>(null);
  const [liveMatches,    setLiveMatches]    = useState<LiveMatch[]>([]);
  const [qatar,          setQatar]          = useState<QatarBacktest | null>(null);
  const [loading,        setLoading]        = useState(true);

  /* Resultados reales del torneo (openfootball) — no bloquea la carga inicial.
     Se refresca cada 5 min para captar partidos que terminan con la pestaña abierta. */
  useEffect(() => {
    fetchLiveMatches().then(setLiveMatches);
    const id = setInterval(() => fetchLiveMatches().then(setLiveMatches), 5 * 60_000);
    return () => clearInterval(id);
  }, []);

  const fixedResults = useMemo(() => buildFixedResults(liveMatches), [liveMatches]);
  const liveScores   = useMemo(() => buildScoreMap(liveMatches), [liveMatches]);
  const liveStats    = useMemo(() => buildLiveStats(liveMatches), [liveMatches]);
  /* Modelo vs Realidad: un solo cálculo para el hero y la pestaña En Vivo */
  const verdicts     = useMemo(
    () => (predictions ? buildVerdicts(liveMatches, predictions) : []),
    [liveMatches, predictions]
  );
  const record       = useMemo(
    () => ({ played: verdicts.length, hits: verdicts.filter((v) => v.hit).length }),
    [verdicts]
  );

  /* Persistencia */
  useEffect(() => {
    const l = localStorage.getItem("wc-lang") as Lang | null;
    if (l === "es" || l === "en" || l === "pt") setLang(l);
  }, []);
  useEffect(() => {
    localStorage.setItem("wc-lang", lang);
  }, [lang]);

  /* Carga de datos */
  useEffect(() => {
    Promise.all([
      fetch("/data/teams.json").then((r) => r.json()),
      fetch("/data/predictions.json").then((r) => r.json()),
      fetch("/data/groups.json").then((r) => r.json()),
      fetch("/data/matches.json").then((r) => r.json()),
      fetch("/data/stats.json").then((r) => r.json()),
      fetch("/data/goalscorers.json").then((r) => r.json()),
      fetch("/data/group_matches.json").then((r) => r.json()),
      fetch("/data/group_standings.json").then((r) => r.json()),
      fetch("/data/qatar2022.json").then((r) => r.json()).catch(() => null),
    ]).then(([t, p, g, m, s, gs, gm, gst, q]) => {
      setTeams(t); setPredictions(p); setGroups(g); setMatches(m);
      setStats(s); setGoalscorers(gs); setGroupMatches(gm); setGroupStandings(gst);
      setQatar(q);
      setLoading(false);
    });
  }, []);

  const S = SHELL[lang];
  const tabNavBg = "rgba(16,22,36,0.96)";
  const mainBg   = "var(--color-arena-void)";
  const footerBg = "var(--color-arena-deep)";

  return (
    /* Context provider: toda la app recibe el idioma activo */
    <LangContext.Provider value={lang}>
      <div style={{ background: mainBg, minHeight: "100dvh", transition: "background 0.25s" }}>

        {/* ══ NAVBAR ══════════════════════════════════════════ */}
        <nav className="navbar-wc">
          <div style={{
            display: "flex", alignItems: "center", justifyContent: "space-between",
            width: "100%", maxWidth: "80rem", margin: "0 auto",
          }}>
            {/* Logo */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.3rem" }}>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(0.78rem, 2.5vw, 1rem)", letterSpacing: "0.1em", color: "#fff", whiteSpace: "nowrap" }}>
                  FIFA WC
                </span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(0.78rem, 2.5vw, 1rem)", letterSpacing: "0.1em", color: "var(--color-wc-red)" }}>
                  2026
                </span>
              </div>
              <div className="hidden sm:block" style={{ width: 1, height: 16, background: "rgba(255,255,255,0.14)" }} />
              <span className="hidden sm:block" style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", letterSpacing: "0.15em", color: "var(--color-wc-gold)", textTransform: "uppercase" }}>
                {S.navLabel}
              </span>
            </div>

            {/* Controles derechos */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              {/* Idioma */}
              <div style={{ display: "flex", gap: "2px" }}>
                {(["es", "en", "pt"] as Lang[]).map((l) => (
                  <button key={l} onClick={() => setLang(l)} style={{
                    fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.08em",
                    textTransform: "uppercase", padding: "0.28rem 0.5rem",
                    border: "none", borderRadius: "3px", cursor: "pointer",
                    minHeight: "32px",
                    background: lang === l ? "var(--color-wc-red)" : "transparent",
                    color: lang === l ? "#fff" : "rgba(255,255,255,0.4)",
                    transition: "background 0.14s, color 0.14s",
                  }}>
                    {l.toUpperCase()}
                  </button>
                ))}
              </div>
              {/* WE ARE 26 */}
              <div className="hidden md:flex" style={{ alignItems: "center", gap: "0.4rem" }}>
                <span style={{ fontSize: "0.85rem" }}>🇨🇦🇲🇽🇺🇸</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.75rem", letterSpacing: "0.18em", color: "rgba(255,255,255,0.45)" }}>
                  {S.weAre26}
                </span>
              </div>
            </div>
          </div>
        </nav>

        {/* ══ HERO — editorial compacto ════════════════════════ */}
        <header className="hero-brand">
          <div style={{
            maxWidth: "80rem", margin: "0 auto",
            padding: "clamp(1.75rem, 4vw, 2.75rem) 1.5rem clamp(1.5rem, 3vw, 2.25rem)",
          }}>
            {/* Eyebrow + estado del torneo */}
            <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.4 }}
              style={{ display: "flex", alignItems: "center", gap: "0.55rem", marginBottom: "0.9rem", flexWrap: "wrap" }}>
              <div style={{ width: 22, height: 3, background: "var(--color-wc-red)", flexShrink: 0 }} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.2em", color: "var(--color-ink-secondary)", textTransform: "uppercase" }}>
                {S.eyebrow}
              </span>
              <TournamentStatus S={S} stats={liveStats} record={record} teams={teams} />
            </motion.div>

            {/* H1 */}
            <motion.h1 initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, delay: 0.05, ease: [0.22, 1, 0.36, 1] }}
              style={{ margin: 0, lineHeight: 0.95, letterSpacing: "0.01em" }}>
              <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(2.6rem, 7vw, 4.25rem)", color: "var(--color-ink-primary)" }}>MUNDIAL 2026</span>
              <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(2.6rem, 7vw, 4.25rem)", color: "var(--color-wc-red)" }}> · PREDICTOR</span>
            </motion.h1>

            {/* Subtítulo legible */}
            <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.4, delay: 0.15 }}
              style={{ fontFamily: "var(--font-body)", fontSize: "clamp(0.9rem, 1.6vw, 1.02rem)", lineHeight: 1.55, color: "var(--color-ink-secondary)", margin: "0.85rem 0 0", maxWidth: "46rem" }}>
              {S.subtitle}
            </motion.p>
          </div>

          <div className="accent-bar" />
        </header>

        {/* ══ TABS ════════════════════════════════════════════ */}
        <div className="tab-nav-bar" style={{
          position: "sticky", top: 56, zIndex: 40,
          background: tabNavBg, backdropFilter: "blur(16px)",
          WebkitBackdropFilter: "blur(16px)", transition: "background 0.25s",
        }}>
          <div style={{ maxWidth: "80rem", margin: "0 auto", padding: "0 1.5rem", display: "flex", overflowX: "auto" }} className="scrollbar-hide">
            {S.tabs.map((t) => (
              <button key={t.id} onClick={() => setTab(t.id as TabId)}
                className={`tab-btn ${tab === t.id ? "active" : ""}`}>
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {/* ══ CONTENIDO ═══════════════════════════════════════ */}
        <main style={{ maxWidth: "72rem", margin: "0 auto", padding: "clamp(1.25rem, 4vw, 2.5rem) clamp(0.75rem, 4vw, 1.5rem) 5rem" }}>
          {loading ? (
            <LoadingState label={S.loading} />
          ) : (
            <AnimatePresence mode="wait">
              {tab === "envivo" && teams && predictions && groups && (
                <TabPane key="envivo">
                  <LiveTournament
                    teams={teams} predictions={predictions} groups={groups}
                    liveMatches={liveMatches} stats={liveStats} verdicts={verdicts}
                  />
                </TabPane>
              )}
              {tab === "predictor" && teams && predictions && (
                <TabPane key="predictor">
                  <Predictor teams={teams} predictions={predictions} matches={matches} liveMatches={liveMatches} />
                </TabPane>
              )}
              {tab === "grupos" && groupMatches && groupStandings && (
                <TabPane key="grupos">
                  <Groups groupMatches={groupMatches} groupStandings={groupStandings} liveScores={liveScores} />
                </TabPane>
              )}
              {tab === "proyecciones" && teams && predictions && groups && (
                <TabPane key="proyecciones">
                  <Projections
                    teams={teams} predictions={predictions} groups={groups}
                    fixedResults={fixedResults}
                    byRoundLabel={S.projByRound} simLabel={S.projSim}
                  />
                </TabPane>
              )}
              {tab === "curiosidades" && stats && (
                <TabPane key="curiosidades">
                  <FunFacts stats={stats} goalscorers={goalscorers} qatar={qatar} />
                </TabPane>
              )}
              {tab === "glosario" && (
                <TabPane key="glosario">
                  <Glossary />
                </TabPane>
              )}
            </AnimatePresence>
          )}
        </main>

        {/* ══ FOOTER ══════════════════════════════════════════ */}
        <footer>
          <div className="accent-bar" />
          <div style={{ background: footerBg, padding: "1.5rem", transition: "background 0.25s" }}>
            <div style={{
              maxWidth: "80rem", margin: "0 auto",
              display: "flex", alignItems: "center",
              justifyContent: "space-between", flexWrap: "wrap", gap: "0.75rem",
            }}>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.4rem" }}>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.85rem", letterSpacing: "0.12em", color: "var(--color-ink-muted)" }}>FIFA WORLD CUP</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.85rem", letterSpacing: "0.12em", color: "var(--color-wc-red)" }}>2026</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.85rem", letterSpacing: "0.12em", color: "var(--color-ink-muted)", opacity: 0.5 }}>PREDICTOR</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.4rem", flexWrap: "wrap" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.1em", color: "var(--color-ink-muted)", textTransform: "uppercase" }}>
                  {S.footerBy}
                </span>
                <a href="https://luismiguelro.com" target="_blank" rel="noopener noreferrer" style={{
                  fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.1em",
                  color: "var(--color-wc-gold)", textTransform: "uppercase",
                  textDecoration: "none", borderBottom: "1px solid rgba(212,168,67,0.35)",
                  paddingBottom: "1px", transition: "color 0.14s",
                }}>
                  luismiguelro.com
                </a>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", letterSpacing: "0.07em", color: "var(--color-ink-muted)", opacity: 0.5 }}>
                  · {S.footerNote}
                </span>
              </div>
            </div>
          </div>
        </footer>
      </div>
    </LangContext.Provider>
  );
}

/* ── Estado del torneo: countdown antes del kickoff, stats en vivo después ── */
const KICKOFF_UTC = Date.parse("2026-06-11T19:00:00Z"); // México vs Sudáfrica · Estadio Azteca · 13:00 CDMX

type ShellStrings = (typeof SHELL)[Lang];

function TournamentStatus({ S, stats, record, teams }: {
  S: ShellStrings;
  stats: LiveStats;
  record: { played: number; hits: number };
  teams: Record<string, TeamInfo> | null;
}) {
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);

  if (now === null) return null; // evita mismatch SSR/cliente

  const diff = KICKOFF_UTC - now;

  if (diff > 0) {
    const d = Math.floor(diff / 86_400_000);
    const h = Math.floor((diff % 86_400_000) / 3_600_000);
    const m = Math.floor((diff % 3_600_000) / 60_000);
    const s = Math.floor((diff % 60_000) / 1_000);
    const pad = (x: number) => String(x).padStart(2, "0");
    return (
      <span className="status-chip">
        {S.kickoffIn}
        <strong>{d}{S.daysSuffix} {pad(h)}:{pad(m)}:{pad(s)}</strong>
      </span>
    );
  }

  /* Torneo en curso: chips con data real (openfootball, se actualiza al cerrar cada partido) */
  const flag = (name: string) => teams?.[name]?.flag ?? "";
  const { last } = stats;
  const pct = record.played ? Math.round((record.hits / record.played) * 100) : 0;

  return (
    <>
      <span className="status-chip status-chip--live">
        <span className="live-dot" />
        {S.liveNow}
      </span>
      {stats.played > 0 && (
        <span className="status-chip">
          <strong>{stats.played}</strong> {S.played} · <strong>{stats.goals}</strong> {S.goalsLabel} · <strong>{stats.avg.toFixed(1)}</strong>{S.perMatch}
        </span>
      )}
      {record.played > 0 && (
        <span className="status-chip status-chip--gold">
          {S.modelTag} <strong>{record.hits}/{record.played}</strong> {S.hitsLabel} ({pct}%)
        </span>
      )}
      {last && last.score1 !== null && last.score2 !== null && (
        <span className="status-chip">
          {S.lastLabel}: <strong>{flag(last.team1)} {last.team1} {last.score1}–{last.score2} {last.team2} {flag(last.team2)}</strong>
        </span>
      )}
    </>
  );
}

/* ── Proyecciones: Monte Carlo por ronda + simulador manual en una sola pestaña ── */
function Projections({ teams, predictions, groups, fixedResults, byRoundLabel, simLabel }: {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  groups: Record<string, string[]>;
  fixedResults: FixedResults;
  byRoundLabel: string;
  simLabel: string;
}) {
  const [view, setView] = useState<"rondas" | "sim">("rondas");
  return (
    <div className="space-y-5">
      <div className="flex gap-1 bg-[var(--surface-2)] rounded-lg p-1 w-fit mx-auto">
        {([
          { key: "rondas" as const, label: byRoundLabel },
          { key: "sim"    as const, label: simLabel },
        ]).map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setView(key)}
            className={`px-4 py-1.5 rounded-md text-xs font-semibold transition-all ${
              view === key ? "bg-[var(--wc-red)] text-white" : "text-[var(--text-muted)]"
            }`}
          >
            {label}
          </button>
        ))}
      </div>
      {view === "rondas" ? (
        <Knockout teams={teams} predictions={predictions} groups={groups} />
      ) : (
        <SimulatorTab teams={teams} predictions={predictions} groups={groups} fixedResults={fixedResults} />
      )}
    </div>
  );
}

/* ── Wrappers ─────────────────────────────────────────────── */
function TabPane({ children }: { children: React.ReactNode }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }} transition={{ duration: 0.26, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}

function LoadingState({ label }: { label: string }) {
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} style={{
      display: "flex", flexDirection: "column", alignItems: "center",
      justifyContent: "center", paddingTop: "5rem", paddingBottom: "5rem", gap: "1.25rem",
    }}>
      <div style={{ position: "relative", width: 40, height: 40 }}>
        <motion.div animate={{ rotate: 360 }} transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
          style={{
            position: "absolute", inset: 0, borderRadius: "50%",
            border: "2px solid transparent", borderTopColor: "var(--color-wc-red)",
            borderRightColor: "rgba(207,10,44,0.15)",
          }} />
        <div style={{ position: "absolute", inset: "6px", borderRadius: "50%", background: "var(--color-arena-card)" }} />
      </div>
      <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.2em", textTransform: "uppercase", color: "var(--color-ink-muted)" }}>
        {label}
      </p>
      <div style={{ width: "100%", maxWidth: 380, display: "flex", flexDirection: "column", gap: "0.6rem" }}>
        {[78, 58, 70, 48].map((w, i) => (
          <div key={i} className="shimmer-skeleton" style={{ height: 10, borderRadius: 3, width: `${w}%` }} />
        ))}
      </div>
    </motion.div>
  );
}
