"use client";

import { useState, useEffect, useMemo, useRef } from "react";
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
import KnockoutBracket, { type BracketData } from "@/components/KnockoutBracket";
import Knockout       from "@/components/Knockout";
import LiveTournament, { type LiveSection } from "@/components/LiveTournament";
import ModelTab       from "@/components/ModelTab";
import ChatTab        from "@/components/ChatTab";
import StatsTab       from "@/components/StatsTab";
import WelcomeModal    from "@/components/WelcomeModal";

/* ─────────────────────────────────────────────────────────────
   UI DEL SHELL (hero, navbar, tabs, footer)
───────────────────────────────────────────────────────────── */
const _shellEs = {
  navLabel:    "Predictor ML",
  weAre26:     "WE ARE 26",
  eyebrow:     "Análisis con Machine Learning",
  subtitle:    "Sigue el Mundial 2026 en tiempo real: resultados, probabilidades por partido y quién tiene más opciones de llegar a la final.",
  tabs: [
    { id: "envivo",        label: "En Vivo"       },
    { id: "predictor",     label: "Predictor"     },
    { id: "eliminatorias", label: "Eliminatorias" },
    { id: "modelo",        label: "Modelo"        },
    { id: "chat",          label: "Chat IA"       },
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
    { id: "envivo",        label: "Live"        },
    { id: "predictor",     label: "Predictor"   },
    { id: "eliminatorias", label: "Knockout"    },
    { id: "modelo",        label: "Model"       },
    { id: "chat",          label: "AI Chat"     },
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

type TabId = "envivo" | "predictor" | "eliminatorias" | "grupos" | "proyecciones" | "curiosidades" | "modelo" | "chat";

/* ─────────────────────────────────────────────────────────────
   PAGE
───────────────────────────────────────────────────────────── */
export default function Home() {
  const [lang,  setLang]  = useState<Lang>("bogotano");
  const [tab,   setTab]   = useState<TabId>("envivo");
  const [theme, setTheme] = useState<"dark"|"light">("dark");
  const [liveJumpSection, setLiveJumpSection] = useState<LiveSection | null>(null);
  const [liveJumpToken,   setLiveJumpToken]   = useState(0);

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
  const [bracket,        setBracket]        = useState<BracketData | null>(null);
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
      fetch("/data/knockout_bracket.json").then((r) => r.json()).catch(() => null),
    ]).then(([t, p, g, m, s, gs, gm, gst, q, lp, nar, groupNar, brk]) => {
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
      if (brk && brk.rounds) setBracket(brk);
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
  const modelPct = record.played ? Math.round((record.hits / record.played) * 100) : 0;

  return (
    /* Context provider: toda la app recibe el idioma activo */
    <LangContext.Provider value={lang}>
      <div data-theme={theme} style={{ background: mainBg, minHeight: "100dvh", transition: "background 0.25s" }}>

        {/* ══ VENTANA EMERGENTE: cómo van los Agentes de IA ══════ */}
        {groupMatches && (
          <WelcomeModal
            groupMatches={groupMatches}
            liveScores={liveScores}
            bracket={bracket}
            onGoToPredictor={() => { setTab("envivo"); setLiveJumpSection("proximos"); setLiveJumpToken((n) => n + 1); }}
            onGoToModel={() => setTab("modelo")}
            onGoToBracket={() => { setTab("eliminatorias"); }}
          />
        )}

        {/* ══ NAVBAR ══════════════════════════════════════════ */}
        <nav className="navbar-wc" aria-label="Barra principal">
          <div className="shell-nav">
            <button
              type="button"
              className="app-brand"
              onClick={() => setTab("envivo")}
              aria-label="Mundial Predictor 2026, ir a En Vivo"
            >
              <span className="app-brand-mark">26</span>
              <span className="app-brand-copy">
                <b>Mundial Predictor</b>
                <small>Decision intelligence · live</small>
              </span>
            </button>

            <div className="nav-controls">
              <div className="language-switch hidden sm:flex" role="group" aria-label="Seleccionar dialecto">
                {LANGS.map(({ key, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setLang(key)}
                    className={lang === key ? "language-option active" : "language-option"}
                    aria-pressed={lang === key}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="language-compact flex sm:hidden" role="group" aria-label="Cambiar dialecto">
                <button type="button" onClick={() => cycleLang(-1)} aria-label="Dialecto anterior">‹</button>
                <span>{LANGS[langIdx].label}</span>
                <button type="button" onClick={() => cycleLang(1)} aria-label="Dialecto siguiente">›</button>
              </div>
              <button
                type="button"
                onClick={() => setTheme((current) => current === "dark" ? "light" : "dark")}
                className="theme-toggle"
                aria-label={theme === "dark" ? "Activar tema claro" : "Activar tema oscuro"}
              >
                {theme === "dark" ? "☼" : "◐"}
              </button>
            </div>
          </div>
        </nav>

        {/* ══ AVISO FUENTE EN VIVO ══════════════════════════════
            Solo se muestra cuando la fuente primaria no respondió. */}
        <LiveSourceBanner source={liveSource} hasData={liveEverLoaded} lastFailure={liveLastFailure} />

        {/* ══ HERO ══════════════════════════════════════════════ */}
        <header className="hero-brand">
          <SignalCanvas />
          <div className="hero-veil" aria-hidden />

          <div className="hero-shell">
            <motion.div
              className="hero-copy"
              initial={{ opacity: 0, y: 18 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="hero-kicker">
                <span className="live-dot" />
                Cuartos de final · sistema activo
              </div>
              <h1>
                <span>Mundial</span>
                <span>Predictor <em>2026</em></span>
              </h1>
              <p>{S.subtitle}</p>
              <div className="hero-status-row">
                <TournamentStatus S={S} stats={liveStats} record={record} teams={teams} />
              </div>
            </motion.div>

            <motion.aside
              className="decision-field"
              initial={{ opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.55, delay: 0.12, ease: [0.16, 1, 0.3, 1] }}
              aria-label="Arquitectura de decisión activa"
            >
              <div className="decision-field-head">
                <span>Decision layer</span>
                <b>Live · QF</b>
              </div>
              <div className="decision-map">
                <div className="decision-node node-model"><b>ML</b><span>ELO + Poisson + XGB</span></div>
                <div className="decision-node node-agents"><b>AG</b><span>Agentes de contexto</span></div>
                <div className="decision-node node-oracle"><b>OR</b><span>Oráculo KO</span></div>
                <div className="decision-core">
                  <span>{record.played ? modelPct : "—"}{record.played ? "%" : ""}</span>
                  <small>precisión viva</small>
                </div>
                <i className="decision-line line-one" aria-hidden />
                <i className="decision-line line-two" aria-hidden />
                <i className="decision-line line-three" aria-hidden />
              </div>
              <div className="decision-field-foot">
                <span>Benchmark</span><span>Debate</span><span>Evaluación</span>
              </div>
            </motion.aside>
          </div>

          <div className="hero-metric-rail">
            <div><span>Partidos jugados</span><b>{liveStats.played || "—"}</b></div>
            <div><span>Goles registrados</span><b>{liveStats.goals || "—"}</b></div>
            <div><span>Modelo vs realidad</span><b>{record.played ? record.hits + "/" + record.played : "—"}</b></div>
            <div><span>Debates publicados</span><b>100</b></div>
          </div>
        </header>

        {/* ══ TABS ════════════════════════════════════════════ */}
        <div className="tab-nav-bar">
          <div className="app-tab-list scrollbar-hide" role="tablist" aria-label="Secciones del producto">
            {S.tabs.map((item, index) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id as TabId)}
                className={`tab-btn ${tab === item.id ? "active" : ""}`}
              >
                <span>{String(index + 1).padStart(2, "0")}</span>
                {item.label}
              </button>
            ))}
          </div>
        </div>

        {/* ══ CONTENIDO ═══════════════════════════════════════ */}
        <main className="app-main">
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
                    jumpToSection={liveJumpSection}
                    jumpToken={liveJumpToken}
                  />
                </TabPane>
              )}
              {tab === "predictor" && teams && predictions && (
                <TabPane key="predictor">
                  <Predictor teams={teams} predictions={predictions} matches={matches} liveMatches={liveMatches} narrations={narrations} agentNotes={agentNotes} onSelectDialect={setLang} />
                </TabPane>
              )}
              {tab === "eliminatorias" && teams && (
                <TabPane key="eliminatorias">
                  {bracket
                    ? <KnockoutBracket data={bracket} roundKey="Round of 32" teams={teams} />
                    : <div className="stat-card text-center py-10 text-[var(--text-muted)]">Cargando bracket de eliminatorias…</div>}
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
                  <ModelTab groupMatches={groupMatches ?? {}} liveScores={liveScores} teams={teams ?? {}} bracket={bracket} />
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
        <footer className="app-footer" style={{ background: footerBg }}>
          <div className="app-footer-inner">
            <div className="app-footer-brand"><span>26</span><b>Mundial Predictor</b></div>
            <p>Modelo, agentes y realidad en el mismo marcador.</p>
            <div className="app-footer-meta">
              <b>Manuel Coy · AI Data Strategist</b>
              <span>{S.footerNote}</span>
            </div>
          </div>
        </footer>
      </div>
    </LangContext.Provider>
  );
}

function SignalCanvas() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvasElement = canvasRef.current;
    if (!canvasElement) return;
    const canvas: HTMLCanvasElement = canvasElement;
    const drawingContext = canvas.getContext("2d");
    if (!drawingContext) return;
    const context: CanvasRenderingContext2D = drawingContext;

    const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const palette = ["#b9ff66", "#3d7dff", "#ff654f", "#ffda45", "#63ddb0"];
    let nodes: Array<{ x: number; y: number; vx: number; vy: number; radius: number; color: string }> = [];
    let width = 1;
    let height = 1;
    let animationFrame = 0;

    function resize() {
      const bounds = canvas.getBoundingClientRect();
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = Math.max(1, bounds.width);
      height = Math.max(1, bounds.height);
      canvas.width = Math.round(width * ratio);
      canvas.height = Math.round(height * ratio);
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      const count = width < 720 ? 20 : 34;
      nodes = Array.from({ length: count }, (_, index) => ({
        x: width * (0.34 + Math.random() * 0.64),
        y: 30 + Math.random() * Math.max(80, height - 60),
        vx: (Math.random() - 0.5) * 0.16,
        vy: (Math.random() - 0.5) * 0.16,
        radius: index % 8 === 0 ? 4.5 : 2.2,
        color: palette[index % palette.length],
      }));
    }

    function draw() {
      context.clearRect(0, 0, width, height);
      nodes.forEach((node, index) => {
        if (!reducedMotion) {
          node.x += node.vx;
          node.y += node.vy;
          if (node.x < width * 0.31 || node.x > width - 16) node.vx *= -1;
          if (node.y < 18 || node.y > height - 18) node.vy *= -1;
        }

        for (let otherIndex = index + 1; otherIndex < nodes.length; otherIndex += 1) {
          const other = nodes[otherIndex];
          const deltaX = node.x - other.x;
          const deltaY = node.y - other.y;
          const distance = Math.sqrt(deltaX * deltaX + deltaY * deltaY);
          if (distance < 135) {
            context.strokeStyle = "rgba(255,255,255," + ((1 - distance / 135) * 0.16) + ")";
            context.lineWidth = 1;
            context.beginPath();
            context.moveTo(node.x, node.y);
            context.lineTo(other.x, other.y);
            context.stroke();
          }
        }

        context.globalAlpha = node.radius > 3 ? 0.9 : 0.5;
        context.fillStyle = node.color;
        context.beginPath();
        context.arc(node.x, node.y, node.radius, 0, Math.PI * 2);
        context.fill();
        context.globalAlpha = 1;
      });

      if (!reducedMotion) animationFrame = window.requestAnimationFrame(draw);
    }

    const resizeObserver = new ResizeObserver(() => {
      resize();
      if (reducedMotion) draw();
    });
    resizeObserver.observe(canvas);
    resize();
    draw();

    return () => {
      resizeObserver.disconnect();
      window.cancelAnimationFrame(animationFrame);
    };
  }, []);

  return <canvas ref={canvasRef} className="hero-signal-canvas" aria-hidden="true" />;
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
    <div className="live-source-banner" role="status" aria-live="polite" style={{
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
