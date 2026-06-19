'use client';

import { useEffect, useState } from 'react';

interface AgentDebateProps {
  homeTeam: string;
  awayTeam: string;
  variant?: 'compact' | 'full'; // compact para predictor, full para en vivo
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

        // Buscar el debate para este partido
        const matchDebate = results.find(
          (r: any) =>
            (r.home === homeTeam || r.home === homeTeam.replace('United States', 'USA')) &&
            (r.away === awayTeam || r.away === awayTeam.replace('United States', 'USA'))
        );

        if (matchDebate) {
          setDebate(matchDebate);
        } else {
          setError('Agent debate not available');
        }
      } catch (err) {
        setError('Failed to load agent debate');
        console.error(err);
      } finally {
        setLoading(false);
      }
    };

    fetchDebate();
  }, [homeTeam, awayTeam]);

  if (loading) return <div className="text-sm text-gray-500">Cargando análisis de agentes...</div>;
  if (error) return <div className="text-sm text-gray-500">{error}</div>;
  if (!debate) return null;

  const context = debate.context;
  const homeCtx = context?.home_team;
  const awayCtx = context?.away_team;

  // Extraer los 3 marcadores principales del consenso
  const consensoText = debate.consensus || '';
  const marcadores = consensoText
    .split('\n')
    .filter((line: string) => line.includes('PREDICCION') || line.includes('Predicción'))
    .slice(0, 3);

  if (variant === 'compact') {
    return (
      <div className="bg-blue-50 border border-blue-200 rounded-lg p-4 mt-4">
        <h3 className="font-bold text-blue-900 mb-3">🤖 Análisis de Agentes Expertos</h3>

        {/* Presión/Status */}
        <div className="text-xs mb-3 space-y-1">
          <div>
            <span className="font-semibold">{homeTeam}:</span> {homeCtx?.status}
          </div>
          <div>
            <span className="font-semibold">{awayTeam}:</span> {awayCtx?.status}
          </div>
        </div>

        {/* Top 3 marcadores */}
        <div className="text-sm space-y-2">
          <div className="font-semibold text-blue-900">Top 3 Predicciones:</div>
          {marcadores.slice(0, 3).map((line: string, idx: number) => (
            <div key={idx} className="text-xs text-gray-700 line-clamp-2">
              {line.replace(/[*#]+/g, '').trim()}
            </div>
          ))}
        </div>

        <details className="mt-3 cursor-pointer">
          <summary className="text-xs font-semibold text-blue-600 hover:text-blue-800">
            Ver consenso completo
          </summary>
          <div className="text-xs text-gray-600 mt-2 bg-white p-2 rounded border border-blue-100 max-h-40 overflow-y-auto">
            {consensoText.substring(0, 800)}...
          </div>
        </details>
      </div>
    );
  }

  // Variant: full (para en vivo)
  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border border-blue-300 rounded-lg p-5 my-4">
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-bold text-lg text-blue-900">🤖 Debate de 3 Agentes Expertos</h3>
        <span className="text-xs bg-blue-600 text-white px-2 py-1 rounded">
          {homeCtx?.points} pts vs {awayCtx?.points} pts
        </span>
      </div>

      {/* Contexto */}
      <div className="grid grid-cols-2 gap-4 mb-4 text-sm">
        <div className="bg-white p-3 rounded border border-blue-200">
          <div className="font-semibold text-blue-900">{homeTeam}</div>
          <div className="text-xs text-gray-600 mt-1">{homeCtx?.status}</div>
          <div className="text-xs text-gray-500 mt-1">MD1: {homeCtx?.md1_result}</div>
        </div>
        <div className="bg-white p-3 rounded border border-indigo-200">
          <div className="font-semibold text-indigo-900">{awayTeam}</div>
          <div className="text-xs text-gray-600 mt-1">{awayCtx?.status}</div>
          <div className="text-xs text-gray-500 mt-1">MD1: {awayCtx?.md1_result}</div>
        </div>
      </div>

      {/* Consenso principal */}
      <div className="bg-white p-4 rounded-lg border border-blue-200">
        <div className="text-sm font-semibold text-blue-900 mb-3">Consenso Final - Top 3 Marcadores:</div>
        <div className="space-y-2 text-sm">
          {marcadores.slice(0, 3).map((line: string, idx: number) => (
            <div key={idx} className="border-l-4 border-blue-400 pl-3 py-1 bg-blue-50 rounded">
              {line.replace(/[*#]+/g, '').trim()}
            </div>
          ))}
        </div>
      </div>

      {/* Análisis completo */}
      <details className="mt-4 cursor-pointer">
        <summary className="font-semibold text-blue-600 hover:text-blue-800 text-sm">
          📊 Ver análisis completo de los 3 agentes
        </summary>
        <div className="mt-3 text-xs text-gray-700 bg-white p-4 rounded border border-blue-200 max-h-64 overflow-y-auto whitespace-pre-wrap">
          {consensoText}
        </div>
      </details>
    </div>
  );
}
