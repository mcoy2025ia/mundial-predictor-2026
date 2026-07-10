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

interface Props {
  groupMatches: Record<string, GroupMatch[]>;
  liveScores: ScoreMap;
  onGoToPredictor: () => void;
  onGoToModel: () => void;
  onGoToBracket: () => void;
}

const AGENT_NAMES = ["Group Analyst", "Tactical Scout", "Sentiment Reader", "Consensus"] as const;

export default function WelcomeModal({ groupMatches, liveScores, onGoToPredictor, onGoToModel, onGoToBracket }: Props) {
  const T = useLang();
  const [open, setOpen] = useState(false);
  const [agentDebateResults, setAgentDebateResults] = useState<AgentDebateMatch[]>([]);

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
        style={{
          position: "fixed", inset: 0, zIndex: 200,
          background: "rgba(8,6,10,0.72)", backdropFilter: "blur(3px)",
          display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
        }}
      >
        <motion.div
          initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.97 }} transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          onClick={(e) => e.stopPropagation()}
          style={{
            maxWidth: 440, width: "100%",
            background: "var(--color-arena-card)", border: "1px solid rgba(212,168,67,0.25)",
            borderRadius: 20, padding: "1.5rem", position: "relative",
            boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
          }}
        >
          <button
            onClick={() => setOpen(false)} aria-label="Cerrar"
            style={{
              position: "absolute", top: 12, right: 12, width: 28, height: 28, borderRadius: 8,
              border: "1px solid rgba(255,255,255,0.1)", background: "rgba(255,255,255,0.04)",
              color: "var(--color-ink-muted)", cursor: "pointer", fontSize: "0.9rem", lineHeight: 1,
            }}
          >
            ✕
          </button>

          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.75rem" }}>
            <span style={{ fontSize: "1.4rem" }}>🤖</span>
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.14em",
              textTransform: "uppercase", color: "var(--color-wc-gold)", fontWeight: 700,
            }}>
              {T.welcomeBadge}
            </span>
          </div>

          <p style={{
            fontFamily: "var(--font-body)", fontSize: "0.92rem", lineHeight: 1.65,
            color: "var(--color-ink-primary)", margin: 0,
          }}>
            {T.welcomeIntro(agentSummary.played, agentSummary.pct)}{" "}
            {T.welcomeBestAgent(bestAgent.name, bestAgent.pct)}
          </p>

          <div style={{
            marginTop: "1rem", padding: "0.75rem 0.9rem", borderRadius: 12,
            background: "rgba(212,168,67,0.07)", border: "1px solid rgba(212,168,67,0.18)",
          }}>
            <p style={{
              fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.04em",
              color: "var(--color-ink-secondary)", margin: 0, lineHeight: 1.7,
            }}>
              {T.welcomePath}
            </p>
          </div>

          <div style={{ marginTop: "1.1rem", display: "flex", flexDirection: "column", gap: "0.55rem" }}>
            <button
              onClick={() => go(onGoToModel)}
              style={{
                width: "100%", padding: "0.85rem 1rem", borderRadius: 12,
                border: "none", cursor: "pointer", fontFamily: "var(--font-body)", fontWeight: 800,
                fontSize: "0.92rem", color: "#fff",
                background: "linear-gradient(135deg, var(--color-wc-red), #ff4d5e)",
                boxShadow: "0 8px 24px rgba(207,10,44,0.4)",
              }}
            >
              {T.welcomeCtaModel}
            </button>
            <button
              onClick={() => go(onGoToPredictor)}
              style={{
                width: "100%", padding: "0.6rem 1rem", borderRadius: 12,
                border: "1px solid rgba(212,168,67,0.3)", cursor: "pointer",
                fontFamily: "var(--font-body)", fontWeight: 600, fontSize: "0.78rem",
                color: "var(--color-wc-gold)", background: "rgba(212,168,67,0.05)",
              }}
            >
              {T.welcomeCtaPredictor}
            </button>
            <button
              onClick={() => go(onGoToBracket)}
              style={{
                width: "100%", padding: "0.65rem 1rem", borderRadius: 12,
                border: "1px solid rgba(255,255,255,0.12)", cursor: "pointer",
                fontFamily: "var(--font-body)", fontWeight: 600, fontSize: "0.8rem",
                color: "var(--color-ink-secondary)", background: "rgba(255,255,255,0.03)",
              }}
            >
              {T.welcomeCtaBestThirds}
            </button>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
