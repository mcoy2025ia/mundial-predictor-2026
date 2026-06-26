'use client';

import { useEffect, useState } from 'react';

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

const AGENT_META: Record<string, { dot: string; label: string; focus: string }> = {
  'Group Analyst':    { dot: '🔵', label: 'Group Analyst',    focus: 'clasificación + presión' },
  'Tactical Scout':   { dot: '🟠', label: 'Tactical Scout',   focus: 'tácticas' },
  'Sentiment Reader': { dot: '🟡', label: 'Sentiment Reader', focus: 'momentum' },
};

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
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchDebate = async () => {
      try {
        setLoading(true);
        const response = await fetch('/api/agent-debate');
        const results = await response.json();
        const matchDebate = results.find(
          (r: any) =>
            (r.home === homeTeam || r.home === homeTeam.replace('United States', 'USA')) &&
            (r.away === awayTeam || r.away === awayTeam.replace('United States', 'USA'))
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
    fetchDebate();
  }, [homeTeam, awayTeam]);

  // Silencioso: si no hay debate para este partido, no ocupar espacio
  if (loading || error || !debate) return null;

  const predictions: Prediction[] = Array.isArray(debate.predictions) ? debate.predictions : [];
  if (predictions.length === 0) return null;

  const agentPreds = predictions.filter((p) => p.agent !== 'Consensus');
  const consensus = predictions.find((p) => p.agent === 'Consensus') || null;
  const analyses = parseAnalyses(debate.consensus || '');

  // Posiciones de la tabla (reemplaza los labels vacíos del context viejo)
  const table: any[] = debate.context?.table || [];
  const rowOf = (team: string) =>
    table.find((r) => r.team === team || r.team === team.replace('United States', 'USA'));
  const homeRow = rowOf(debate.home);
  const awayRow = rowOf(debate.away);

  const winnerLabel = (w: string) =>
    w === 'home' ? `Gana ${homeTeam}` : w === 'away' ? `Gana ${awayTeam}` : 'Empate';
  const scoreStr = (p: Prediction) => `${homeTeam} ${p.home_goals}-${p.away_goals} ${awayTeam}`;

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

  const StandingsLine = () =>
    (homeRow || awayRow) ? (
      <div className="text-xs text-gray-500 mb-3 flex gap-4">
        {homeRow && <span><b>{homeTeam}</b> · {homeRow.pos}º, {homeRow.pts} pts</span>}
        {awayRow && <span><b>{awayTeam}</b> · {awayRow.pos}º, {awayRow.pts} pts</span>}
      </div>
    ) : null;

  if (variant === 'compact') {
    return (
      <details className="bg-blue-50 border border-blue-200 rounded-lg mt-4 group">
        <summary className="cursor-pointer list-none px-4 py-2.5 flex items-center justify-between">
          <span className="font-semibold text-blue-900 text-sm">🤖 Análisis de Agentes Expertos</span>
          <span className="text-xs text-blue-600 flex items-center gap-1">
            Ver detalle
            <span className="inline-block transition-transform group-open:rotate-180">▾</span>
          </span>
        </summary>
        <div className="px-4 pb-4">
          <ConsensusBanner />
          <StandingsLine />
          <div className="space-y-2">
            {agentPreds.map((p, i) => <AgentRow key={i} p={p} />)}
          </div>
        </div>
      </details>
    );
  }

  // Variant: full (para en vivo)
  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-300 rounded-lg p-5 my-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-lg text-blue-900">🤖 Debate de 3 Agentes Expertos</h3>
        {(homeRow || awayRow) && (
          <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded">
            {homeRow?.pts ?? '–'} pts vs {awayRow?.pts ?? '–'} pts
          </span>
        )}
      </div>
      <ConsensusBanner />
      <StandingsLine />
      <div className="bg-white p-4 rounded-lg border border-blue-200 space-y-2">
        <div className="text-sm font-semibold text-blue-900 mb-1">Predicción por agente</div>
        {agentPreds.map((p, i) => <AgentRow key={i} p={p} />)}
      </div>
    </div>
  );
}
