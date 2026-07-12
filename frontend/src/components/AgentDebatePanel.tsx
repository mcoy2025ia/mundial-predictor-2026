'use client';

import { useEffect, useState, type CSSProperties } from 'react';

interface AgentDebateProps {
  homeTeam: string;
  awayTeam: string;
  variant?: 'compact' | 'full'; // compact para predictor, full para en vivo
}

interface Prediction {
  home_goals: number;
  away_goals: number;
  probability: number;
  predicted_winner: 'home' | 'draw' | 'away';
  agent: string;
}

interface Upset {
  home: string;
  away: string;
  favorite: string;
  underdog: string;
  scoreline: string | null;       // "H-A" en 90'
  upset_plausibility: number;
  upset_pick: boolean;
  one_liner: string;
  key_factors: string[];
}

const AGENT_META: Record<string, { dot: string; label: string; focus: string }> = {
  'Group Analyst':    { dot: '🔵', label: 'Group Analyst',    focus: 'clasificación + presión' },
  'Tactical Scout':   { dot: '🟠', label: 'Tactical Scout',   focus: 'tácticas' },
  'Sentiment Reader': { dot: '🟡', label: 'Sentiment Reader', focus: 'momentum' },
};

// ── Oráculo de Eliminatorias (QF/SF/Final) — voz premium de avance real ──
interface OracleVerdict {
  agente: string;
  marcador_90_minutos: { equipo_local: number; equipo_visitante: number } | null;
  marcador_120_minutos: { equipo_local: number; equipo_visitante: number } | null;
  resultado_penaltis: { equipo_local: number; equipo_visitante: number } | null;
  equipo_clasificado: string | null;
  fase_de_definicion: '90_minutos' | 'tiempo_extra' | 'penaltis';
  conviccion: 'baja' | 'media' | 'alta';
  explicacion: string;
  valido: boolean;
}

interface OracleMatch {
  home: string;
  away: string;
  round: string;
  panel: OracleVerdict[];
  consensus: OracleVerdict | null;
  model?: { favorite: string | null; fav_prob: number | null };
}

// Monograma, especialidad y color de acento por voz del panel (paleta de la app).
const ORA_VOICES: Record<string, { ini: string; spec: string; vc: string }> = {
  'Group Analyst':                { ini: 'GA', spec: 'campaña y regularidad', vc: '#0A84FF' },
  'Tactical Scout':               { ini: 'TS', spec: 'táctica y balón parado', vc: '#32D4F5' },
  'Sentiment Reader':             { ini: 'SR', spec: 'momentum y temple',      vc: '#5E9BFF' },
  'Especialista en Definiciones': { ini: 'ED', spec: 'prórroga y penales',     vc: '#F0BE4A' },
};

const PHASE_LABEL: Record<string, string> = {
  '90_minutos': 'en los 90′',
  'tiempo_extra': 'en la prórroga',
  'penaltis': 'en penaltis',
};
const PHASE_SHORT: Record<string, string> = {
  '90_minutos': '90′',
  'tiempo_extra': 'Prórroga',
  'penaltis': 'Penales',
};
const ROUND_ES: Record<string, string> = {
  'Quarter-final': 'Cuartos de final',
  'Semi-final': 'Semifinal',
  'Final': 'Final',
  'Match for third place': 'Tercer puesto',
};

// Código de 3 letras para la insignia del equipo (Spain → SPA, etc.).
function teamCode(name: string | null): string {
  if (!name) return '—';
  return name.replace(/[^A-Za-zÁÉÍÓÚÜÑáéíóúüñ]/g, '').slice(0, 3).toUpperCase();
}

const dash = (o: { equipo_local: number; equipo_visitante: number } | null) =>
  o ? `${o.equipo_local}–${o.equipo_visitante}` : '—';

// Segmentos del timeline de eliminatoria: 90′ → Prórroga → Penales.
// Estado: 'decisive' (define la llave), 'reached' (se jugó pero no definió), 'ghost' (no se alcanzó).
function oraSegments(v: OracleVerdict): { label: string; score: string; state: string }[] {
  const fase = v.fase_de_definicion;
  return [
    {
      label: '90 minutos', score: dash(v.marcador_90_minutos),
      state: fase === '90_minutos' ? 'decisive' : 'reached',
    },
    {
      label: 'Prórroga',
      score: fase === '90_minutos' ? '—' : dash(v.marcador_120_minutos || v.marcador_90_minutos),
      state: fase === 'tiempo_extra' ? 'decisive' : fase === 'penaltis' ? 'reached' : 'ghost',
    },
    {
      label: 'Penaltis',
      score: fase === 'penaltis' ? dash(v.resultado_penaltis) : '—',
      state: fase === 'penaltis' ? 'decisive' : 'ghost',
    },
  ];
}

// Compacto por voz: "90′ · 2–0" / "Penales · 3–4".
function oraPickPhase(v: OracleVerdict): string {
  const fase = v.fase_de_definicion;
  const score = fase === 'penaltis' ? dash(v.resultado_penaltis)
    : fase === 'tiempo_extra' ? dash(v.marcador_120_minutos || v.marcador_90_minutos)
    : dash(v.marcador_90_minutos);
  return `${PHASE_SHORT[fase]} · ${score}`;
}

// Nivel de confianza cualitativo — evita presentar un marcador exacto como si
// tuviera 50% de probabilidad literal (eso no es realista para un score puntual).
function confLevel(p: number): { text: string; cls: string } {
  if (p >= 0.5) return { text: 'convicción alta', cls: 'bg-emerald-100 text-emerald-700' };
  if (p >= 0.35) return { text: 'convicción media', cls: 'bg-amber-100 text-amber-700' };
  return { text: 'convicción baja', cls: 'bg-gray-100 text-gray-600' };
}

// Extrae la línea "Análisis: ..." de cada agente del texto del consenso,
// SIN incluir el bloque RESULTADO_JSON ni el scaffolding del prompt.
function parseAnalyses(consensusText: string): Record<string, string> {
  const out: Record<string, string> = {};
  if (!consensusText) return out;
  const lines = consensusText.split('\n');
  let current: string | null = null;
  for (const raw of lines) {
    const line = raw.trim();
    if (line.startsWith('RESULTADO_JSON')) break; // nunca pasar de aquí
    const hit = Object.keys(AGENT_META).find((name) => line.includes(name));
    if (hit) { current = hit; continue; }
    if (current && /^an[aá]lisis\s*:/i.test(line)) {
      out[current] = line.replace(/^an[aá]lisis\s*:/i, '').trim();
      current = null;
    }
  }
  return out;
}

export default function AgentDebatePanel({
  homeTeam,
  awayTeam,
  variant = 'compact',
}: AgentDebateProps) {
  const [debate, setDebate] = useState<any>(null);
  const [upset, setUpset] = useState<Upset | null>(null);
  const [oracle, setOracle] = useState<OracleMatch | null>(null);
  const [flags, setFlags] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const matches = (a: string, b: string) =>
      a === b || a === b.replace('United States', 'USA') || b === a.replace('United States', 'USA');

    const fetchDebate = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/agent-debate');
        const results = await response.json();
        const matchDebate = results.find(
          (r: any) => matches(r.home, homeTeam) && matches(r.away, awayTeam)
        );
        if (matchDebate) setDebate(matchDebate);
        else setError('Agent debate not available');
      } catch (err) {
        setError('Failed to load agent debate');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    // Cazador de Sorpresas (4ª voz). Estático en /data; si no existe, se ignora.
    const fetchUpset = async () => {
      try {
        const res = await fetch('/data/upset_predictions.json');
        if (!res.ok) return;
        const data = await res.json();
        const list: Upset[] = Array.isArray(data?.upsets) ? data.upsets : [];
        const hit = list.find((u) => matches(u.home, homeTeam) && matches(u.away, awayTeam));
        if (hit) setUpset(hit);
      } catch {
        /* opcional: sin sorpresa, no pasa nada */
      }
    };

    // Oráculo de Eliminatorias (solo QF/SF/Final). Estático en /data; si no existe, se ignora.
    const fetchOracle = async () => {
      try {
        const res = await fetch('/data/knockout_oracle_predictions.json');
        if (!res.ok) return;
        const data = await res.json();
        const list: OracleMatch[] = Array.isArray(data?.matches) ? data.matches : [];
        const hit = list.find(
          (o) => 'error' in o === false &&
            ((matches(o.home, homeTeam) && matches(o.away, awayTeam)) ||
             (matches(o.home, awayTeam) && matches(o.away, homeTeam)))
        );
        if (hit) setOracle(hit);
      } catch {
        /* opcional: sin oráculo, no pasa nada */
      }
    };

    // Banderas de teams.json (misma convención que el bracket). Si no carga, se ignora.
    const fetchFlags = async () => {
      try {
        const res = await fetch('/data/teams.json');
        if (!res.ok) return;
        const data = await res.json();
        const map: Record<string, string> = {};
        for (const [name, info] of Object.entries<any>(data)) {
          if (info?.flag) map[name] = info.flag;
        }
        setFlags(map);
      } catch {
        /* sin banderas, se usa el fallback de código */
      }
    };

    fetchDebate();
    fetchUpset();
    fetchOracle();
    fetchFlags();
  }, [homeTeam, awayTeam]);

  // Bandera emoji por nombre de equipo (con alias USA/United States).
  const flagOf = (name: string | null): string => {
    if (!name) return '';
    return flags[name] || flags[name.replace('United States', 'USA')] || flags[name.replace('USA', 'United States')] || '';
  };

  // Silencioso mientras carga. Renderiza si hay debate de 3 agentes O si hay
  // Oráculo de Eliminatorias (este último puede existir sin el debate).
  if (loading) return null;
  const predictions: Prediction[] = debate && Array.isArray(debate.predictions) ? debate.predictions : [];
  const hasDebate = predictions.length > 0;
  if (!hasDebate && !oracle) return null;

  // Cuando hay Oráculo (QF/SF/Final), es la voz canónica: se oculta el debate
  // viejo de 3 agentes para no duplicar los mismos nombres con predicciones de
  // solo 90'. El debate de 3 agentes solo se muestra cuando NO hay Oráculo.
  const showOldDebate = hasDebate && !oracle;
  const agentPreds = predictions.filter((p) => p.agent !== 'Consensus');
  const consensus = predictions.find((p) => p.agent === 'Consensus') || null;
  const analyses = hasDebate ? parseAnalyses(debate.consensus || '') : {};

  // Posiciones de la tabla (reemplaza los labels vacíos del context viejo)
  const table: any[] = debate?.context?.table || [];
  const rowOf = (team: string) =>
    table.find((r) => r.team === team || r.team === team.replace('United States', 'USA'));
  const homeRow = hasDebate ? rowOf(debate.home) : undefined;
  const awayRow = hasDebate ? rowOf(debate.away) : undefined;

  const winnerLabel = (w: string) =>
    w === 'home' ? `Gana ${homeTeam}` : w === 'away' ? `Gana ${awayTeam}` : 'Empate';
  const scoreStr = (p: Prediction) => `${homeTeam} ${p.home_goals}-${p.away_goals} ${awayTeam}`;

  // Iconos SVG (línea) — reemplazan los emojis del diseño anterior.
  const IcoOrbit = ({ s = 16 }: { s?: number }) => (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6l1.4 1.4M17 17l1.4 1.4M18.4 5.6L17 7M7 17l-1.4 1.4" /><circle cx="12" cy="12" r="3.4" />
    </svg>
  );
  const IcoArrow = ({ s = 13 }: { s?: number }) => (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h13M13 6l6 6-6 6" /></svg>
  );
  const IcoClock = ({ s = 13 }: { s?: number }) => (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="8.5" /><path d="M12 8v4.5l3 1.6" /></svg>
  );
  const IcoCheck = ({ s = 14 }: { s?: number }) => (
    <svg width={s} height={s} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 6.5" /></svg>
  );

  // Timeline de eliminatoria (elemento estrella)
  const OraTimeline = ({ v }: { v: OracleVerdict }) => (
    <div className="ora-tl" role="img" aria-label={`Resolución de la llave: ${oraPickPhase(v)}`}>
      {oraSegments(v).map((seg, i) => (
        <div key={i} className={`ora-seg is-${seg.state}`}>
          <div className="k">{i === 0 && <IcoClock s={11} />}{seg.label}</div>
          <div className="v">{seg.score}</div>
          {seg.state === 'decisive' && <span className="tick"><IcoCheck s={15} /></span>}
        </div>
      ))}
    </div>
  );

  // Fila de una voz del panel
  const OraVoice = ({ v, dissent }: { v: OracleVerdict; dissent: boolean }) => {
    const meta = ORA_VOICES[v.agente] || { ini: '··', spec: '', vc: '#0A84FF' };
    return (
      <div className="ora-voice">
        <div className="ora-mono" style={{ '--vc': meta.vc } as CSSProperties}>{meta.ini}</div>
        <div className="ora-vbody">
          <div className="ora-vr1">
            <span className="ora-aname">{v.agente}</span>
            <span className="ora-aspec">{meta.spec}</span>
            {dissent && <span className="ora-dissent">Discrepa</span>}
          </div>
          <div className="ora-pick">
            <span className={`ora-padv${dissent ? ' is-up' : ''}`}><span className="arw">→</span> {flagOf(v.equipo_clasificado)} {v.equipo_clasificado}</span>
            <span className="ora-pmini">{oraPickPhase(v)}</span>
            <span className={`ora-conv is-${v.conviccion}${dissent ? ' is-up' : ''}`}><i /><i /><i /></span>
          </div>
          {v.explicacion && <div className="ora-vwhy">{v.explicacion}</div>}
        </div>
      </div>
    );
  };

  // Cazador de Sorpresas (rediseñado, dentro de la tarjeta del Oráculo)
  const OraCazador = () => {
    if (!upset) return null;
    const plaus = Math.round((upset.upset_plausibility || 0) * 100);
    return (
      <aside className="ora-caz">
        <div className="ora-caz-h">
          <span className="ora-caz-ico" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="8.5" /><circle cx="12" cy="12" r="3.4" /><path d="M12 1.5V4M12 20v2.5M22.5 12H20M4 12H1.5" /></svg>
          </span>
          <span className="ora-caz-t">Cazador de Sorpresas <span>· gana {upset.underdog}</span></span>
          <span className="ora-caz-p">{plaus}%</span>
        </div>
        <div className="ora-gauge" role="img" aria-label={`Plausibilidad del batacazo: ${plaus}%`}>
          <i style={{ width: `${Math.max(4, Math.min(100, plaus))}%` }} />
        </div>
        {upset.one_liner && <div className="ora-caz-q">«{upset.one_liner}»</div>}
        <div className="ora-caz-f">Voz aparte · defiende al menos favorito como contrapeso del consenso</div>
      </aside>
    );
  };

  // Cuerpo del Oráculo (veredicto + timeline + meta + voces + cazador)
  const OracleBody = ({ cons, validPanel }: { cons: OracleVerdict | null; validPanel: OracleVerdict[] }) => {
    const consWinner = cons?.equipo_clasificado || null;
    const agree = validPanel.filter((v) => v.equipo_clasificado === consWinner).length;
    const fav = oracle?.model?.favorite;
    const favPct = oracle?.model?.fav_prob != null ? Math.round(oracle.model.fav_prob * 100) : null;
    return (
      <>
        {cons && (
          <section className="ora-verdict">
            <div className="ora-vlabel">Veredicto del consenso</div>
            <div className="ora-champ">
              <div className={`ora-badge${flagOf(cons.equipo_clasificado) ? ' has-flag' : ''}`}>
                {flagOf(cons.equipo_clasificado) || teamCode(cons.equipo_clasificado)}
              </div>
              <div className="ora-who">
                <span className="ora-adv"><IcoArrow s={13} /> Avanza</span>
                <span className="ora-name">{cons.equipo_clasificado}</span>
              </div>
              <span className="ora-phase"><IcoClock s={13} /> Resuelto {PHASE_LABEL[cons.fase_de_definicion]}</span>
            </div>
            <OraTimeline v={cons} />
            {cons.explicacion && <p className="ora-why">{cons.explicacion}</p>}
          </section>
        )}
        <div className="ora-meta">
          <span><b>{flagOf(oracle!.home)} {oracle!.home}</b> vs <b>{flagOf(oracle!.away)} {oracle!.away}</b></span>
          {fav && favPct != null && (<><span className="d" /><span>Modelo: <b>{flagOf(fav)} {fav}</b> {favPct}%</span></>)}
        </div>
        <section className="ora-panel">
          <div className="ora-cap">
            <span>Las {validPanel.length} voces</span>
            {consWinner && <span className="agree">{agree} de {validPanel.length} · {consWinner}</span>}
          </div>
          {validPanel.map((v, i) => (
            <OraVoice key={i} v={v} dissent={!!consWinner && v.equipo_clasificado !== consWinner} />
          ))}
        </section>
        <OraCazador />
      </>
    );
  };

  const AgentRow = ({ p }: { p: Prediction }) => {
    const meta = AGENT_META[p.agent] || { dot: '⚪', label: p.agent, focus: '' };
    const conf = confLevel(p.probability);
    const analysis = analyses[p.agent];
    return (
      <div className="border-l-4 border-blue-300 pl-3 py-1.5">
        <div className="flex items-center gap-2 flex-wrap text-xs">
          <span className="font-semibold text-gray-800">{meta.dot} {meta.label}</span>
          <span className="text-gray-400">·</span>
          <span className="font-mono text-gray-700">{scoreStr(p)}</span>
          <span className="text-blue-700 font-medium">{winnerLabel(p.predicted_winner)}</span>
          <span className={`px-1.5 py-0.5 rounded ${conf.cls}`}>{conf.text}</span>
        </div>
        {analysis && <div className="text-xs text-gray-500 mt-1">{analysis}</div>}
      </div>
    );
  };

  const ConsensusBanner = () =>
    consensus ? (
      <div className="bg-white rounded-md border border-blue-200 px-3 py-2 mb-3">
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span>🏆</span>
          <span className="font-bold text-blue-900">Consenso:</span>
          <span className="font-mono text-gray-800">{scoreStr(consensus)}</span>
          <span className="text-blue-700 font-semibold">{winnerLabel(consensus.predicted_winner)}</span>
        </div>
        <div className="text-[11px] text-gray-400 mt-0.5">
          Marcador más probable según los agentes · no es probabilidad literal del resultado exacto
        </div>
      </div>
    ) : null;

  const UpsetBanner = () => {
    if (!upset) return null;
    const live = upset.upset_pick;
    const plaus = Math.round((upset.upset_plausibility || 0) * 100);
    // scoreline "H-A" → orientado local-visitante
    const sl = upset.scoreline?.match(/(\d+)\s*-\s*(\d+)/);
    const scoreStr = sl ? `${homeTeam} ${sl[1]}-${sl[2]} ${awayTeam}` : null;
    return (
      <div className={`rounded-md border px-3 py-2 mb-3 ${live ? 'bg-orange-50 border-orange-300' : 'bg-gray-50 border-gray-200'}`}>
        <div className="flex items-center gap-2 flex-wrap text-sm">
          <span>🚨</span>
          <span className="font-bold text-orange-900">Cazador de Sorpresas:</span>
          {scoreStr && <span className="font-mono text-gray-800">{scoreStr}</span>}
          <span className="text-orange-700 font-semibold">Gana {upset.underdog}</span>
          <span className={`px-1.5 py-0.5 rounded text-xs ${live ? 'bg-orange-100 text-orange-700' : 'bg-gray-100 text-gray-600'}`}>
            {live ? 'sorpresa viva' : 'palo lejano'} · plausibilidad {plaus}%
          </span>
        </div>
        {upset.one_liner && <div className="text-xs text-gray-600 mt-1 italic">«{upset.one_liner}»</div>}
        <div className="text-[11px] text-gray-400 mt-0.5">
          Voz aparte: defiende el batacazo del menos favorito · contrapeso al consenso
        </div>
      </div>
    );
  };

  const StandingsLine = () =>
    (homeRow || awayRow) ? (
      <div className="text-xs text-gray-500 mb-3 flex gap-4">
        {homeRow && <span><b>{homeTeam}</b> · {homeRow.pos}º, {homeRow.pts} pts</span>}
        {awayRow && <span><b>{awayTeam}</b> · {awayRow.pos}º, {awayRow.pts} pts</span>}
      </div>
    ) : null;

  // ── Rama Oráculo (QF/SF/Final): tarjeta rediseñada, reemplaza el chrome azul ──
  if (oracle) {
    const cons = oracle.consensus && oracle.consensus.valido ? oracle.consensus : null;
    const validPanel = (oracle.panel || []).filter((v) => v.valido && v.marcador_90_minutos);
    if (cons || validPanel.length > 0) {
      const roundEs = ROUND_ES[oracle.round] || oracle.round;
      if (variant === 'compact') {
        return (
          <details className="ora mt-4">
            <summary className="ora-sum">
              <span className="ora-glyph"><IcoOrbit s={15} /></span>
              {cons ? (
                <span className="ora-sum-adv"><small>Oráculo · avanza</small><b>{flagOf(cons.equipo_clasificado)} {cons.equipo_clasificado}</b></span>
              ) : (
                <span className="ora-sum-adv"><b>Oráculo de Eliminatorias</b></span>
              )}
              {cons && <span className="ora-sum-phase">Resuelto {PHASE_LABEL[cons.fase_de_definicion]}</span>}
              <span className="ora-sum-open"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round"><path d="M6 9l6 6 6-6" /></svg></span>
            </summary>
            <div className="ora-rule" />
            <OracleBody cons={cons} validPanel={validPanel} />
          </details>
        );
      }
      return (
        <div className="ora my-4">
          <div className="ora-head">
            <div className="ora-brand">
              <span className="ora-glyph"><IcoOrbit s={16} /></span>
              <div><b>Oráculo de Eliminatorias</b><em>Panel · {validPanel.length} voces + consenso</em></div>
            </div>
            <span className="ora-chip">{roundEs}</span>
          </div>
          <div className="ora-rule" />
          <OracleBody cons={cons} validPanel={validPanel} />
        </div>
      );
    }
  }

  if (variant === 'compact') {
    return (
      <details className="agent-debate agent-debate-compact mt-4 group">
        <summary className="cursor-pointer list-none px-4 py-2.5 flex items-center justify-between">
          <span className="agent-debate-title font-semibold text-sm">AG · Análisis de agentes expertos</span>
          <span className="agent-debate-open text-xs flex items-center gap-1">
            Ver detalle
            <span className="inline-block transition-transform group-open:rotate-180">▾</span>
          </span>
        </summary>
        <div className="px-4 pb-4">
          {showOldDebate && <ConsensusBanner />}
          <UpsetBanner />
          <StandingsLine />
          {showOldDebate && (
            <div className="space-y-2">
              {agentPreds.map((p, i) => <AgentRow key={i} p={p} />)}
            </div>
          )}
        </div>
      </details>
    );
  }

  // Variant: full (para en vivo)
  return (
    <div className="agent-debate agent-debate-full p-5 my-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-lg agent-debate-title">
          {hasDebate ? 'AG · Debate de 3 agentes expertos' : 'KO · Análisis de eliminatorias'}
        </h3>
        {(homeRow || awayRow) && (
          <span className="text-xs agent-debate-score px-2 py-1 rounded">
            {homeRow?.pts ?? '–'} pts vs {awayRow?.pts ?? '–'} pts
          </span>
        )}
      </div>
      {showOldDebate && <ConsensusBanner />}
      <UpsetBanner />
      <StandingsLine />
      {showOldDebate && (
        <div className="bg-white p-4 rounded-lg border border-blue-200 space-y-2">
          <div className="text-sm font-semibold text-blue-900 mb-1">Predicción por agente</div>
          {agentPreds.map((p, i) => <AgentRow key={i} p={p} />)}
        </div>
      )}
    </div>
  );
}
