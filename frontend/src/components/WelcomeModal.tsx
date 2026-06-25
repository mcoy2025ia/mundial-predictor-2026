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
}

const AGENT_NAMES = ["Group Analyst", "Tactical Scout", "Sentiment Reader", "Consensus"] as const;

function buildByMd(results: { groupMd: number; hit: boolean }[]) {
  const map: Record<number, { hits: number; played: number }> = {};
  for (const r of results) {
    if (!map[r.groupMd]) map[r.groupMd] = { hits: 0, played: 0 };
    map[r.groupMd].played++;
    if (r.hit) map[r.groupMd].hits++;
  }
  return map;
}

export default function WelcomeModal({ groupMatches, liveScores, onGoToPredictor }: Props) {
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
  const agentByMd = useMemo(() => buildByMd(flattenAgentResults(agentResults)), [agentResults]);
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

  const currentMd = useMemo(() => {
    for (const md of [3, 2, 1]) {
      if (agentByMd[md]) return md;
    }
    return null;
  }, [agentByMd]);

  const mdStats = currentMd !== null ? agentByMd[currentMd] : null;
  const mdPct = mdStats ? Math.round((mdStats.hits / mdStats.played) * 100) : null;

  // Solo se abre una vez que hay algo real que contar.
  useEffect(() => {
    if (mdPct !== null && bestAgent) setOpen(true);
  }, [mdPct, bestAgent]);

  if (!open || mdPct === null || !bestAgent) return null;

  function go() {
    setOpen(false);
    onGoToPredictor();
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
            {T.welcomeIntro(currentMd ?? 3, mdPct)}{" "}
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

          <button
            onClick={go}
            style={{
              marginTop: "1.1rem", width: "100%", padding: "0.7rem 1rem", borderRadius: 12,
              border: "none", cursor: "pointer", fontFamily: "var(--font-body)", fontWeight: 700,
              fontSize: "0.85rem", color: "#1a1410",
              background: "linear-gradient(135deg, var(--color-wc-gold), #e8c873)",
            }}
          >
            {T.welcomeCta}
          </button>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
}
