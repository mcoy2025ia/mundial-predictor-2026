"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import type { GroupMatch } from "@/types";
import type { ScoreMap } from "@/lib/live";
import {
  computeAgentResults, computeAgentStatsByAgent, flattenAgentResults,
  type AgentDebateMatch,
} from "@/lib/agentDebate";
import { useLang } from "@/lib/i18n";
import type { BracketData } from "@/components/KnockoutBracket";

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  bracket?: BracketData | null;
  onGoToPredictor: () => void;
  onGoToModel: () => void;
  onGoToBracket: () => void;
}

const AGENT_NAMES = ["Group Analyst", "Tactical Scout", "Sentiment Reader", "Consensus"] as const;

/** Última ronda del bracket con al menos un cruce resuelto (equipos definidos) —
 * es la fase "actual" del torneo desde la perspectiva del usuario, aunque esa
 * ronda todavía no haya terminado de jugarse. "group" si knockout no arrancó. */
function currentPhaseKey(bracket: BracketData | null | undefined): string {
  if (!bracket) return "group";
  for (let i = bracket.round_order.length - 1; i >= 0; i--) {
    const rk = bracket.round_order[i];
    if ((bracket.rounds[rk] ?? []).some((m) => m.home && m.away)) return rk;
  }
  return "group";
}

export default function WelcomeModal({ groupMatches, liveScores, bracket, onGoToPredictor, onGoToModel, onGoToBracket }: Props) {
  const T = useLang();
  const [open, setOpen] = useState(false);
  const [agentDebateResults, setAgentDebateResults] = useState<AgentDebateMatch[]>([]);
  const phaseKey = useMemo(() => currentPhaseKey(bracket), [bracket]);

  useEffect(() => {
    let active = true;
    fetch("/api/agent-debate")
      .then((r) => r.json())
      .then((data) => { if (active && Array.isArray(data)) setAgentDebateResults(data); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  const agentResults = useMemo(
    () => computeAgentResults(groupMatches, liveScores, agentDebateResults),
    [groupMatches, liveScores, agentDebateResults]
  );
  const flatAgentResults = useMemo(() => flattenAgentResults(agentResults), [agentResults]);
  const agentStatsByAgent = useMemo(() => computeAgentStatsByAgent(agentResults), [agentResults]);

  const bestAgent = useMemo(() => {
    let best: { name: string; pct: number } | null = null;
    for (const name of AGENT_NAMES) {
      const stats = agentStatsByAgent[name];
      if (!stats || stats.played === 0) continue;
      const pct = Math.round((stats.hits / stats.played) * 100);
      if (!best || pct > best.pct) best = { name, pct };
    }
    return best;
  }, [agentStatsByAgent]);

  const agentSummary = useMemo(() => {
    if (!flatAgentResults.length) return null;
    const hits = flatAgentResults.filter((r) => r.hit).length;
    return {
      hits,
      played: flatAgentResults.length,
      pct: Math.round((hits / flatAgentResults.length) * 100),
    };
  }, [flatAgentResults]);

  // Solo se abre una vez que hay algo real que contar.
  useEffect(() => {
    if (agentSummary && bestAgent) setOpen(true);
  }, [agentSummary, bestAgent]);

  if (!open || !agentSummary || !bestAgent) return null;

  function go(action: () => void) {
    setOpen(false);
    action();
  }

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
        onClick={() => setOpen(false)}
        className="welcome-backdrop"
      >
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.97 }} transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          onClick={(e) => e.stopPropagation()}
          className="welcome-panel"
          role="dialog"
          aria-modal="true"
          aria-labelledby="welcome-title"
        >
          <button
            onClick={() => setOpen(false)} aria-label="Cerrar"
            className="welcome-close"
          >
            ✕
          </button>

          <div className="welcome-heading">
            <span className="welcome-code">AG</span>
            <div>
              <p>Evaluación multiagente · {phaseKey}</p>
              <h2 id="welcome-title">{T.welcomeBadge}</h2>
            </div>
          </div>

          <div className="welcome-metrics" aria-label="Resumen de agentes">
            <div><span>Evaluadas</span><b>{agentSummary.played}</b></div>
            <div><span>Precisión</span><b>{agentSummary.pct}%</b></div>
            <div><span>Top agent</span><b>{bestAgent.pct}%</b><small>{bestAgent.name}</small></div>
          </div>

          <p className="welcome-copy">
            {T.welcomeIntro(agentSummary.played, agentSummary.pct, phaseKey)}{" "}
            {T.welcomeBestAgent(bestAgent.name, bestAgent.pct)}
          </p>

          <div className="welcome-path">
            <span>Benchmark</span><i>→</i><span>Agentes</span><i>→</i><span>Realidad</span>
            <p>{T.welcomePath}</p>
          </div>

          <div className="welcome-actions">
            <button onClick={() => go(onGoToModel)} className="welcome-primary">
              {T.welcomeCtaModel}
            </button>
            <button onClick={() => go(onGoToPredictor)} className="welcome-secondary">
              {T.welcomeCtaPredictor}
            </button>
            <button onClick={() => go(onGoToBracket)} className="welcome-tertiary">
              {T.welcomeCtaBestThirds}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
