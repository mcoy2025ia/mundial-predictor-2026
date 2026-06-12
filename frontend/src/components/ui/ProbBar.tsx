"use client";
import { motion } from "framer-motion";

interface Props {
  pct: number;
  color: string;
  label: string;
  isWinner: boolean;
  delay?: number;
}

export default function ProbBar({ pct, color, label, isWinner, delay = 0 }: Props) {
  const percent = Math.round(pct * 100);

  return (
    <div>
      {/* Etiqueta + número */}
      <div className="flex items-center justify-between mb-1.5">
        <div className="flex items-center gap-2">
          {isWinner && (
            <motion.span
              initial={{ scale: 0, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ delay: delay + 1.1, type: "spring", stiffness: 320 }}
              style={{ color: "#D4A843" }}
              className="text-xs leading-none"
            >
              ★
            </motion.span>
          )}
          <span
            className="text-sm font-semibold tracking-wide"
            style={{
              fontFamily: "var(--font-heading, 'Barlow Condensed', system-ui)",
              color: isWinner ? color : "var(--color-ink-secondary, #9898BB)",
            }}
          >
            {label}
          </span>
        </div>
        <motion.span
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: delay + 0.5 }}
          className="text-2xl leading-none tabular-nums"
          style={{
            fontFamily: "var(--font-display, 'Bebas Neue', system-ui)",
            color: isWinner ? color : "var(--color-ink-muted, #4A4A6A)",
          }}
        >
          {percent}%
        </motion.span>
      </div>

      {/* Barra */}
      <div
        className="relative h-10 rounded-xl overflow-hidden"
        style={{ background: "var(--color-arena-elevated, #161628)" }}
      >
        {/* Relleno animado */}
        <motion.div
          className="absolute inset-y-0 left-0 rounded-xl"
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 1.1, delay, ease: [0.22, 1, 0.36, 1] }}
          style={{
            background: isWinner
              ? `linear-gradient(90deg, ${color}55 0%, ${color}99 100%)`
              : `linear-gradient(90deg, ${color}18 0%, ${color}30 100%)`,
            boxShadow: isWinner
              ? `0 0 22px ${color}40, inset 0 1px 0 rgba(255,255,255,0.10)`
              : "none",
          }}
        />

        {/* Sweep de luz ganador */}
        {isWinner && (
          <motion.div
            className="absolute inset-y-0 left-0 w-16 rounded-xl pointer-events-none"
            style={{
              background:
                "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.20) 50%, transparent 100%)",
            }}
            initial={{ x: "-100%" }}
            animate={{ x: "700%" }}
            transition={{ duration: 1.5, delay: delay + 1.0, ease: "easeInOut" }}
          />
        )}
      </div>
    </div>
  );
}
