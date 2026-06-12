"use client";
import { motion } from "framer-motion";

interface Props {
  isPredicted: boolean;
  onSwap: () => void;
}

export default function VsOrb({ isPredicted, onSwap }: Props) {
  return (
    <div className="flex flex-col items-center gap-3 shrink-0">
      {/* Orbe VS */}
      <motion.div
        animate={
          isPredicted
            ? {
                boxShadow: [
                  "0 0 18px rgba(212,168,67,0.55)",
                  "0 0 42px rgba(212,168,67,0.18)",
                  "0 0 18px rgba(212,168,67,0.55)",
                ],
              }
            : { boxShadow: "0 0 0px transparent" }
        }
        transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
        className="relative"
      >
        {/* Anillo giratorio */}
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
          className="absolute inset-0 rounded-full pointer-events-none"
          style={{
            border: "2px solid transparent",
            borderTopColor:   "rgba(212,168,67,0.65)",
            borderRightColor: "rgba(212,168,67,0.12)",
          }}
        />

        {/* Core */}
        <div
          className="relative w-14 h-14 rounded-full flex items-center justify-center"
          style={{
            background: "linear-gradient(135deg, #1A1A30 0%, #0F0F20 100%)",
            border: "1.5px solid rgba(212,168,67,0.28)",
            boxShadow: "inset 0 1px 0 rgba(255,255,255,0.07)",
          }}
        >
          <span
            className="text-lg tracking-widest"
            style={{
              fontFamily: "var(--font-display, 'Bebas Neue', system-ui)",
              color: "#D4A843",
            }}
          >
            VS
          </span>
        </div>
      </motion.div>

      {/* Swap */}
      <motion.button
        onClick={onSwap}
        whileHover={{ scale: 1.18, rotate: 180 }}
        whileTap={{ scale: 0.85 }}
        transition={{ type: "spring", stiffness: 380, damping: 18 }}
        title="Intercambiar equipos"
        className="text-base leading-none select-none"
        style={{ color: "var(--color-ink-muted, #4A4A6A)" }}
      >
        ⇄
      </motion.button>
    </div>
  );
}
