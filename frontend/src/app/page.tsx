"use client";

import { useState, useEffect, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import type {
  TeamInfo, Prediction, HistoricalMatch, SiteStats, FixedResults,
  Goalscorer, GroupMatch, GroupStandingEntry, LiveMatch, QatarBacktest,
} from "@/types";
import { LangContext, UI, type Lang } from "@/lib/i18n";
import {
  buildFixedResults, buildLiveStats, buildScoreMap, buildVerdicts,
  fetchLiveStatus, type LiveStats, type LiveSource, type FetchFailure, type FetchFailureReason,
} from "@/lib/live";
import Predictor      from "@/components/Predictor";
import SimulatorTab   from "@/components/Simulator";
import Groups         from "@/components/Groups";
import Knockout       from "@/components/Knockout";
import LiveTournament from "@/components/LiveTournament";
import ModelTab       from "@/components/ModelTab";
import ChatTab        from "@/components/ChatTab";
import StatsTab       from "@/components/StatsTab";

/* ─────────────────────────────────────────────────────────────
   UI DEL SHELL (hero, navbar, tabs, footer)
───────────────────────────────────────────────────────────── */
const _shellEs = {
  navLabel:    "Predictor ML",
  weAre26:     "WE ARE 26",
  eyebrow:     "Análisis con Machine Learning",
  subtitle:    "Sigue el Mundial 2026 en tiempo real: resultados, probabilidades por partido y quién tiene más opciones de llegar a la final.",
  tabs: [
    { id: "envivo",       label: "En Vivo"      },
    { id: "predictor",    label: "Predictor"    },
    { id: "grupos",       label: "Grupos"       },
    { id: "proyecciones", label: "Proyecciones" },
    { id: "curiosidades", label: "Stats"        },
    { id: "modelo",       label: "Modelo"       },
    { id: "chat",         label: "Chat IA"      },
  ],
  projByRound: "Por ronda",
  projSim:     "Simulador",
  loading:     "Cargando datos del modelo…",
  footerBy:    "por",
  footerNote:  "Modelo entrenado hasta Qatar 2022 · No afiliado a FIFA",
  kickoffIn:   "El torneo arranca en",
  liveNow:     "Torneo en vivo",
  played:      "partidos",
  goalsLabel:  "goles",
  perMatch:    "/partido",
  modelTag:    "Modelo",
  hitsLabel:   "aciertos",
  lastLabel:   "Último",
  daysSuffix:  "d",
} as const;

const _shellEn = {
  navLabel:    "ML Predictor",
  weAre26:     "WE ARE 26",
  eyebrow:     "Machine Learning Analysis",
  subtitle:    "Follow the 2026 World Cup live: scores, match probabilities and who has the best shot at lifting the trophy.",
  tabs: [
    { id: "envivo",       label: "Live"        },
    { id: "predictor",    label: "Predictor"   },
    { id: "grupos",       label: "Groups"      },
    { id: "proyecciones", label: "Projections" },
    { id: "curiosidades", label: "Stats"       },
    { id: "modelo",       label: "Model"       },
    { id: "chat",         label: "AI Chat"     },
  ],
  projByRound: "By round",
  projSim:     "Simulator",
  loading:     "Loading model data…",
  footerBy:    "by",
  footerNote:  "Model trained up to Qatar 2022 · Not affiliated with FIFA",
  kickoffIn:   "Tournament kicks off in",
  liveNow:     "Tournament live",
  played:      "matches",
  goalsLabel:  "goals",
  perMatch:    "/match",
  modelTag:    "Model",
  hitsLabel:   "correct",
  lastLabel:   "Latest",
  daysSuffix:  "d",
} as const;

const SHELL = {
  bogotano: _shellEs,
  paisa:    _shellEs,
  boyaco:   _shellEs,
  costeño:  _shellEs,
  en:       _shellEn,
} as const;

type TabId = "envivo" | "predictor" | "grupos" | "proyecciones" | "curiosidades" | "modelo" | "chat";

/* ─────────────────────────────────────────────────────────────
   PAGE
───────────────────────────────────────────────────────────── */
export default function Home() {
  const [lang,  setLang]  = useState<Lang>("bogotano");
  const [tab,   setTab]   = useState<TabId>("envivo");
  const [theme, setTheme] = useState<"dark"|"light">("dark");

  const [teams,          setTeams]          = useState<Record<string, TeamInfo> | null>(null);
  const [predictions,    setPredictions]    = useState<Record<string, Prediction> | null>(null);
  const [groups,         setGroups]         = useState<Record<string, string[]> | null>(null);
  const [matches,        setMatches]        = useState<HistoricalMatch[]>([]);
  const [stats,          setStats]          = useState<SiteStats | null>(null);
  const [goalscorers,    setGoalscorers]    = useState<Goalscorer[]>([]);
  const [groupMatches,   setGroupMatches]   = useState<Record<string, GroupMatch[]> | null>(null);
  const [groupStandings, setGroupStandings] = useState<Record<string, GroupStandingEntry[]> | null>(null);
  const [liveMatches,    setLiveMatches]    = useState<LiveMatch[]>([]);
  const [liveSource,     setLiveSource]     = useState<LiveSource>("api");
  const [liveEverLoaded, setLiveEverLoaded] = useState(false);
  const [liveLastFailure,setLiveLastFailure]= useState<FetchFailure | undefined>(undefined);
  const [qatar,          setQatar]          = useState<QatarBacktest | null>(null);
  const [narrations,     setNarrations]     = useState<Record<string, string>>({});
  const [groupNarratives,setGroupNarratives]= useState<Record<string, string>>({});
  const [agentNotes,     setAgentNotes]     = useState<Record<string, string>>({});
  const [loading,        setLoading]        = useState(true);

  /* Resultados reales del torneo — no bloquea la carga inicial.
     Polling adaptativo:
       - éxito (api):        refresco normal cada 90s (tablas/marcadores al día durante partidos en vivo)
       - respaldo (openfootball): reintenta la primaria cada 90s (aviso suave)
       - fallo total (none): backoff 30s → 4 min, conserva los últimos datos buenos
     Se pausa cuando la pestaña está oculta y se reanuda (con lectura inmediata) al volver. */
  useEffect(() => {
    const OK_INTERVAL    = 90_000;
    const DEGRADED_RETRY = 90_000;
    const RETRY_BASE     = 30_000;
    const RETRY_MAX      = 4 * 60_000;

    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failCount = 0;

    function schedule(delay: number) {
      if (timer) clearTimeout(timer);
      if (typeof document !== "undefined" && document.hidden) return; // reanuda en visibilitychange
      timer = setTimeout(tick, delay);
    }

    async function tick() {
      const { matches, source, lastFailure } = await fetchLiveStatus();
      if (cancelled) return;
      setLiveSource(source);
      setLiveLastFailure(lastFailure);
      if (source === "none") {
        failCount += 1; // conservamos los últimos datos buenos, no pisamos con []
        schedule(Math.min(RETRY_BASE * 2 ** (failCount - 1), RETRY_MAX));
      } else {
        failCount = 0;
        setLiveMatches(matches);
        setLiveEverLoaded(true);
        schedule(source === "openfootball" ? DEGRADED_RETRY : OK_INTERVAL);
      }
    }

    function onVisibility() {
      if (cancelled) return;
      if (document.hidden) {
        if (timer) clearTimeout(timer);
      } else {
        tick(); // al volver al frente: refrescar de inmediato
      }
    }

    tick();
    document.addEventListener("visibilitychange", onVisibility);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
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
    if (l === "bogotano" || l === "paisa" || l === "boyaco" || l === "costeño" || l === "en") setLang(l);
    const t = localStorage.getItem("wc-theme");
    if (t === "dark" || t === "light") setTheme(t);
  }, []);
  useEffect(() => { localStorage.setItem("wc-lang", lang); }, [lang]);
  useEffect(() => { localStorage.setItem("wc-theme", theme); }, [theme]);

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
      fetch("/data/live_predictions.json").then((r) => r.json()).catch(() => null),
      fetch("/data/narrations.json").then((r) => r.json()).catch(() => ({})),
      fetch("/data/group_narratives.json").then((r) => r.json()).catch(() => ({})),
    ]).then(([t, p, g, m, s, gs, gm, gst, q, lp, nar, groupNar]) => {
      // Merge live_predictions (agent-adjusted) on top of base predictions
      const notes: Record<string, string> = {};
      if (lp && Array.isArray(lp)) {
        for (const entry of lp) {
          const key = `${entry.home_team}|${entry.away_team}`;
          p[key] = { home_win: entry.p_home, draw: entry.p_draw, away_win: entry.p_away };
          const fifaNote = entry.agent_notes?.["FIFA-Regs-Strategist"];
          if (fifaNote) notes[key] = fifaNote;
        }
      }
      setAgentNotes(notes);
      setTeams(t); setPredictions(p); setGroups(g); setMatches(m);
      setStats(s); setGoalscorers(gs); setGroupMatches(gm); setGroupStandings(gst);
      setQatar(q);
      if (nar && typeof nar === "object") setNarrations(nar);
      if (groupNar && typeof groupNar === "object") setGroupNarratives(groupNar);
      setLoading(false);
    });
  }, []);

  const S = SHELL[lang];
  const mainBg   = "var(--color-arena-void)";

  const LANGS: Array<{ key: Lang; label: string }> = [
    { key: "bogotano", label: "Bog." },
    { key: "paisa",    label: "Pai." },
    { key: "boyaco",   label: "Boy." },
    { key: "costeño",  label: "Cos." },
    { key: "en",       label: "EN"   },
  ];
  const langIdx  = LANGS.findIndex(l => l.key === lang);
  const cycleLang = (dir: 1 | -1) =>
    setLang(LANGS[(langIdx + dir + LANGS.length) % LANGS.length].key);
  const footerBg = "var(--color-arena-deep)";

  return (
    /* Context provider: toda la app recibe el idioma activo */
    <LangContext.Provider value={lang}>
      <div data-theme={theme} style={{ background: mainBg, minHeight: "100dvh", transition: "background 0.25s" }}>

        {/* ══ NAVBAR ══════════════════════════════════════════ */}
        <nav className="navbar-wc">
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", width: "100%", maxWidth: "80rem", margin: "0 auto" }}>
            {/* Logo */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.55rem" }}>
              {/* WC Trophy SVG icon */}
              <svg width="22" height="26" viewBox="0 0 22 26" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden>
                <path d="M7 2h8l-1 11a5 5 0 01-6 0L7 2z" fill="url(#trophy-grad)"/>
                <path d="M3 4c-2 3-1 6 2 7" stroke="#C9981F" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
                <path d="M19 4c2 3 1 6-2 7" stroke="#C9981F" strokeWidth="1.4" strokeLinecap="round" fill="none"/>
                <rect x="9" y="17" width="4" height="4" rx="0.5" fill="#C9981F" opacity="0.85"/>
                <rect x="5.5" y="21" width="11" height="2.2" rx="1" fill="url(#trophy-base)"/>
                <rect x="3.5" y="23" width="15" height="2" rx="1" fill="#C9981F" opacity="0.6"/>
                <defs>
                  <linearGradient id="trophy-grad" x1="7" y1="2" x2="15" y2="15" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#F5CC6A"/>
                    <stop offset="1" stopColor="#C9981F"/>
                  </linearGradient>
                  <linearGradient id="trophy-base" x1="5.5" y1="21" x2="16.5" y2="23" gradientUnits="userSpaceOnUse">
                    <stop stopColor="#C9981F"/>
                    <stop offset="1" stopColor="#7A5C0F"/>
                  </linearGradient>
                </defs>
              </svg>
              <div style={{ display: "flex", alignItems: "baseline", gap: "0.28rem" }}>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(0.95rem, 2.5vw, 1.15rem)", letterSpacing: "0.08em", color: "var(--color-ink-primary)" }}>FIFA</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "clamp(0.95rem, 2.5vw, 1.15rem)", letterSpacing: "0.08em", color: "var(--color-wc-red)" }}>WC 2026</span>
              </div>
            </div>

            {/* Controls */}
            <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
              {/* Lang — desktop: 5 botones · móvil: ‹ activo › */}
              <div className="hidden sm:flex" style={{ gap: "1px", background: "rgba(255,255,255,0.04)", borderRadius: 6, padding: "2px" }}>
                {LANGS.map(({ key, label }) => (
                  <button key={key} onClick={() => setLang(key)} style={{
                    fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.06em",
                    padding: "0.25rem 0.55rem",
                    border: "none", borderRadius: 4, cursor: "pointer", minHeight: 28,
                    background: lang === key ? "var(--color-wc-red)" : "transparent",
                    color: lang === key ? "#fff" : "var(--color-ink-muted)",
                    transition: "background 0.15s, color 0.15s",
                  }}>{label}</button>
                ))}
              </div>
              <div className="flex sm:hidden" style={{ alignItems: "center", background: "rgba(255,255,255,0.04)", borderRadius: 6, padding: "2px", gap: 0 }}>
                <button onClick={() => cycleLang(-1)} aria-label="Dialecto anterior" style={{
                  fontFamily: "var(--font-mono)", fontSize: "0.9rem", lineHeight: 1,
                  padding: "0.2rem 0.45rem", border: "none", borderRadius: 4,
                  background: "transparent", color: "var(--color-ink-muted)", cursor: "pointer", minHeight: 28,
                }}>‹</button>
                <span style={{
                  fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.06em",
                  padding: "0 0.3rem", color: "#fff", minWidth: 32, textAlign: "center",
                }}>{LANGS[langIdx].label}</span>
                <button onClick={() => cycleLang(1)} aria-label="Dialecto siguiente" style={{
                  fontFamily: "var(--font-mono)", fontSize: "0.9rem", lineHeight: 1,
                  padding: "0.2rem 0.45rem", border: "none", borderRadius: 4,
                  background: "transparent", color: "var(--color-ink-muted)", cursor: "pointer", minHeight: 28,
                }}>›</button>
              </div>
              {/* Theme toggle */}
              <button onClick={() => setTheme(t => t === "dark" ? "light" : "dark")} className="theme-toggle" aria-label="Toggle theme">
                {theme === "dark" ? "☀" : "☾"}
              </button>
            </div>
          </div>
        </nav>

        {/* ══ AVISO FUENTE EN VIVO ══════════════════════════════
            Solo se muestra cuando la fuente primaria no respondió. */}
        <LiveSourceBanner source={liveSource} hasData={liveEverLoaded} lastFailure={liveLastFailure} />

        {/* ══ HERO ══════════════════════════════════════════════ */}
        <header className="hero-brand">
          {/* Aurora background */}
          <div className="hero-aurora" aria-hidden />

          <div style={{
            position: "relative", zIndex: 1,
            maxWidth: "80rem", margin: "0 auto",
            padding: "clamp(2.25rem, 5vw, 3.5rem) clamp(1rem, 4vw, 1.5rem) 0",
            display: "flex",
            alignItems: "flex-end",
            gap: "clamp(0.5rem, 2vw, 2rem)",
          }}>
            {/* Columna texto — ocupa todo el espacio disponible */}
            <div style={{ flex: 1, minWidth: 0, paddingBottom: "clamp(1.75rem, 3vw, 2.5rem)" }}>

              {/* WC Logo + eyebrow row */}
              <motion.div
                initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                style={{ display: "flex", alignItems: "center", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}
              >
                {/* Trophy icon — animated glow */}
                <motion.div
                  animate={{ boxShadow: ["0 0 12px rgba(201,152,31,0.2)", "0 0 32px rgba(201,152,31,0.55)", "0 0 12px rgba(201,152,31,0.2)"] }}
                  transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
                  style={{
                    width: 44, height: 44, borderRadius: 12, flexShrink: 0,
                    background: "linear-gradient(135deg, rgba(229,0,45,0.18) 0%, rgba(201,152,31,0.14) 50%, rgba(0,50,200,0.12) 100%)",
                    border: "1px solid rgba(201,152,31,0.35)",
                    display: "flex", alignItems: "center", justifyContent: "center",
                  }}
                >
                  <svg width="26" height="30" viewBox="0 0 26 30" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M8 2h10l-1.5 13a6 6 0 01-7 0L8 2z" fill="url(#hero-trophy)"/>
                    <path d="M3.5 4.5C1 8 2 12 5.5 13.5" stroke="#F5CC6A" strokeWidth="1.6" strokeLinecap="round" fill="none"/>
                    <path d="M22.5 4.5C25 8 24 12 20.5 13.5" stroke="#F5CC6A" strokeWidth="1.6" strokeLinecap="round" fill="none"/>
                    <rect x="11" y="19" width="4" height="4.5" rx="0.8" fill="#C9981F"/>
                    <rect x="6.5" y="23.5" width="13" height="2.5" rx="1.2" fill="url(#hero-base)"/>
                    <rect x="4" y="26" width="18" height="2.5" rx="1.2" fill="#7A5C0F" opacity="0.7"/>
                    <ellipse cx="11" cy="8" rx="2" ry="1.2" fill="white" opacity="0.18"/>
                    <defs>
                      <linearGradient id="hero-trophy" x1="8" y1="2" x2="18" y2="17" gradientUnits="userSpaceOnUse">
                        <stop stopColor="#FDEAAC"/>
                        <stop offset="0.5" stopColor="#F5CC6A"/>
                        <stop offset="1" stopColor="#C9981F"/>
                      </linearGradient>
                      <linearGradient id="hero-base" x1="6.5" y1="23.5" x2="19.5" y2="26" gradientUnits="userSpaceOnUse">
                        <stop stopColor="#D4A843"/>
                        <stop offset="1" stopColor="#7A5C0F"/>
                      </linearGradient>
                    </defs>
                  </svg>
                </motion.div>

                <div style={{ display: "flex", flexDirection: "column", gap: "0.15rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: "0.52rem", letterSpacing: "0.2em",
                      color: "var(--color-wc-gold-bright)", textTransform: "uppercase",
                    }}>FIFA WORLD CUP</span>
                    <span style={{ width: 1, height: 8, background: "rgba(255,255,255,0.12)" }} />
                    <span style={{
                      fontFamily: "var(--font-mono)", fontSize: "0.52rem", letterSpacing: "0.16em",
                      color: "var(--color-ink-muted)", textTransform: "uppercase",
                    }}>{S.eyebrow}</span>
                  </div>
                </div>

                <div style={{ marginLeft: "auto", display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                  <TournamentStatus S={S} stats={liveStats} record={record} teams={teams} />
                </div>
              </motion.div>

              {/* H1 */}
              <motion.h1
                initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.55, delay: 0.07, ease: [0.16, 1, 0.3, 1] }}
                style={{ margin: 0, lineHeight: 0.9, letterSpacing: "-0.01em" }}
              >
                <span style={{ display: "block", fontFamily: "var(--font-display)", fontSize: "clamp(2.6rem, 7.5vw, 5.5rem)", color: "var(--color-ink-primary)" }}>
                  MUNDIAL
                </span>
                <span style={{ display: "block", fontFamily: "var(--font-display)", fontSize: "clamp(2.6rem, 7.5vw, 5.5rem)" }}>
                  <span style={{ color: "var(--color-wc-red)" }}>2026</span>
                  <span style={{ color: "rgba(255,255,255,0.18)", margin: "0 0.2em" }}>·</span>
                  <span style={{ color: "var(--color-ink-primary)" }}>PREDICTOR</span>
                </span>
              </motion.h1>

              {/* Subtitle */}
              <motion.p
                initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.45, delay: 0.2 }}
                style={{
                  fontFamily: "var(--font-body)", fontSize: "clamp(0.85rem, 1.4vw, 0.95rem)",
                  lineHeight: 1.65, color: "var(--color-ink-secondary)",
                  margin: "1rem 0 0", maxWidth: "42rem", fontWeight: 400,
                }}
              >{S.subtitle}</motion.p>

            </div>

            {/* Columna mascota — solo md+ */}
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/images/mascotas.webp"
              alt=""
              aria-hidden
              className="hidden md:block"
              style={{
                flexShrink: 0,
                alignSelf: "flex-end",
                height: "clamp(160px, 24vw, 300px)",
                width: "auto",
                objectFit: "contain",
                objectPosition: "bottom",
                pointerEvents: "none",
                userSelect: "none",
              }}
            />
          </div>

          <div className="accent-bar" />
        </header>

        {/* ══ TABS ════════════════════════════════════════════ */}
        <div className="tab-nav-bar" style={{ position: "sticky", top: 52, zIndex: 40 }}>
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
                    groupNarratives={groupNarratives}
                  />
                </TabPane>
              )}
              {tab === "predictor" && teams && predictions && (
                <TabPane key="predictor">
                  <Predictor teams={teams} predictions={predictions} matches={matches} liveMatches={liveMatches} narrations={narrations} agentNotes={agentNotes} />
                </TabPane>
              )}
              {tab === "grupos" && groupMatches && groupStandings && (
                <TabPane key="grupos">
                  <Groups groupMatches={groupMatches} groupStandings={groupStandings} liveScores={liveScores} groupNarratives={groupNarratives} />
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
              {tab === "curiosidades" && (
                <TabPane key="curiosidades">
                  <StatsTab
                    liveMatches={liveMatches}
                    groupMatches={groupMatches ?? {}}
                    liveScores={liveScores}
                    teams={teams ?? {}}
                  />
                </TabPane>
              )}
              {tab === "modelo" && (
                <TabPane key="modelo">
                  <ModelTab groupMatches={groupMatches ?? {}} liveScores={liveScores} teams={teams ?? {}} />
                </TabPane>
              )}
              {tab === "chat" && (
                <TabPane key="chat">
                  <ChatTab groupMatches={groupMatches ?? {}} />
                </TabPane>
              )}
            </AnimatePresence>
          )}
        </main>

        {/* ══ FOOTER ══════════════════════════════════════════ */}
        <footer>
          <div className="accent-bar" />
          <div style={{ background: footerBg, padding: "1.25rem clamp(1rem, 4vw, 1.5rem)", transition: "background 0.3s" }}>
            <div style={{ maxWidth: "80rem", margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "0.6rem" }}>
              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem" }}>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.8rem", letterSpacing: "0.1em", color: "var(--color-ink-muted)" }}>FIFA WC</span>
                <span style={{ fontFamily: "var(--font-display)", fontSize: "0.8rem", letterSpacing: "0.1em", color: "var(--color-wc-red)" }}>2026</span>
                <span style={{ width: 1, height: 10, background: "rgba(255,255,255,0.08)" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", letterSpacing: "0.08em", color: "var(--color-ink-muted)", textTransform: "uppercase", opacity: 0.6 }}>Predictor</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexWrap: "wrap" }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", letterSpacing: "0.08em", color: "var(--color-wc-gold)", textTransform: "uppercase" }}>
                  Manuel Coy · AI Data Strategist
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--color-ink-muted)", opacity: 0.45 }}>
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

/* ── Aviso de fuente en vivo ──
   Banner discreto que confirma cuándo la fuente primaria de resultados no
   responde. "openfootball" = degradado (usando respaldo); "none" = sin datos,
   reintentando solo. Con "api" no se renderiza nada. */
const FAILURE_REASON_LABEL: Record<FetchFailureReason, string> = {
  timeout:        "no respondió a tiempo",
  http_error:     "respondió con error HTTP",
  empty_data:     "respondió vacío",
  parse_error:    "devolvió datos inválidos",
  network_error:  "falló por red/conexión",
};

function LiveSourceBanner({
  source, hasData, lastFailure,
}: { source: LiveSource; hasData: boolean; lastFailure?: FetchFailure }) {
  if (source === "api") return null;

  const degraded = source === "openfootball";
  const cause = lastFailure
    ? ` (${FAILURE_REASON_LABEL[lastFailure.reason]}: ${lastFailure.detail})`
    : "";
  const text = degraded
    ? `Fuente principal de resultados no disponible${cause} — mostrando datos de respaldo. Reintentando…`
    : hasData
      ? `No se pudo actualizar los resultados en vivo${cause} — mostrando los últimos datos disponibles. Reintentando…`
      : `No se pudo conectar con los resultados en vivo${cause}. Reintentando automáticamente…`;

  const bg     = degraded ? "rgba(201,152,31,0.12)" : "rgba(201,42,42,0.12)";
  const border = degraded ? "rgba(201,152,31,0.45)" : "rgba(201,42,42,0.5)";
  const dot    = degraded ? "#C9981F" : "#C92A2A";

  return (
    <div role="status" aria-live="polite" style={{
      display: "flex", alignItems: "center", justifyContent: "center", gap: "0.5rem",
      maxWidth: "80rem", margin: "0 auto", padding: "0.4rem 1rem",
      background: bg, borderBottom: `1px solid ${border}`,
      fontFamily: "var(--font-mono)", fontSize: "0.66rem", letterSpacing: "0.03em",
      color: "var(--color-ink-primary)",
    }}>
      <span style={{
        width: 7, height: 7, borderRadius: "50%", background: dot,
        flexShrink: 0, animation: "live-pulse 1.6s ease-in-out infinite",
      }} />
      <span>{text}</span>
    </div>
  );
}

/* ── Estado del torneo: countdown antes del kickoff, stats en vivo después ── */
const KICKOFF_UTC = Date.parse("2026-06-11T19:00:00Z"); // México vs Sudáfrica · Estadio Azteca · 13:00 CDMX

type ShellStrings = typeof _shellEs | typeof _shellEn;

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
