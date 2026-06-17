"use client";

import { useState, useRef, useEffect, useCallback, useMemo, useContext } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useLang, LangContext, type Lang } from "@/lib/i18n";
import type { GroupMatch } from "@/types";

interface Message {
  role: "user" | "assistant";
  content: string;
  id: string;
}

function uid() {
  return Math.random().toString(36).slice(2, 9);
}

/* ══════════════════════════════════════════════════════
   CHAT TAB PRINCIPAL
══════════════════════════════════════════════════════ */
// ── Sugerencias dinámicas basadas en los partidos de hoy ─────────────────────

const HIGH_ALT_VENUES = ["Mexico City", "Guadalajara", "Ciudad de México", "Monterrey"];

function buildTodaySuggestions(
  groupMatches: Record<string, GroupMatch[]>,
  lang: Lang
): string[] {
  const today = new Date().toLocaleDateString("en-CA");
  const todayFixtures: Array<{ group: string; m: GroupMatch }> = [];

  for (const [group, matches] of Object.entries(groupMatches)) {
    for (const m of matches) {
      if (m.date === today) todayFixtures.push({ group, m });
    }
  }

  if (todayFixtures.length === 0) return [];

  const sugs: string[] = [];
  const es = lang !== "en";

  // Preguntas por partido (máx 2)
  for (const { m } of todayFixtures.slice(0, 2)) {
    sugs.push(es
      ? `¿Cuál es la predicción del modelo para ${m.team1} vs ${m.team2} hoy?`
      : `What's the model prediction for ${m.team1} vs ${m.team2} today?`
    );
  }

  // Pregunta de clasificación por grupo (máx 2 grupos distintos)
  const groups = [...new Set(todayFixtures.map((f) => f.group))].slice(0, 2);
  for (const grp of groups) {
    sugs.push(es
      ? `¿Quién clasifica del ${grp} dependiendo de los resultados de hoy?`
      : `Who advances from ${grp} depending on today's results?`
    );
  }

  // Forma del equipo más favorito de hoy
  const topMatch = [...todayFixtures].sort((a, b) =>
    Math.max(b.m.t1_win, b.m.t2_win) - Math.max(a.m.t1_win, a.m.t2_win)
  )[0];
  const favTeam = topMatch.m.t1_win > topMatch.m.t2_win ? topMatch.m.team1 : topMatch.m.team2;
  sugs.push(es
    ? `¿Cómo viene ${favTeam} en el torneo y cuáles son sus opciones de clasificar?`
    : `How is ${favTeam} doing in the tournament and what are their chances?`
  );

  // Altitud si aplica
  const altVenue = todayFixtures.find((f) =>
    HIGH_ALT_VENUES.some((v) => f.m.ground?.includes(v))
  );
  if (altVenue) {
    sugs.push(es
      ? `¿Cómo afecta la altitud de ${altVenue.m.ground} a los equipos que juegan hoy?`
      : `How does the altitude in ${altVenue.m.ground} affect today's match?`
    );
  }

  return sugs.slice(0, 6);
}

// ─────────────────────────────────────────────────────────────────────────────

interface ChatTabProps {
  initialQuestion?: string;
  groupMatches?: Record<string, GroupMatch[]>;
}

export default function ChatTab({ initialQuestion, groupMatches }: ChatTabProps = {}) {
  const T = useLang();
  const lang = useContext(LangContext);

  const suggestions = useMemo(() => {
    const dynamic = groupMatches ? buildTodaySuggestions(groupMatches, lang) : [];
    return dynamic.length > 0 ? dynamic : (T.chatSuggestions as unknown as string[]);
  }, [groupMatches, lang, T.chatSuggestions]);

  const [messages,  setMessages]  = useState<Message[]>([]);
  const [input,     setInput]     = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error,     setError]     = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef  = useRef<HTMLTextAreaElement>(null);
  const abortRef  = useRef<AbortController | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  const hasSentInitial = useRef(false);
  useEffect(() => {
    if (initialQuestion && !hasSentInitial.current) {
      hasSentInitial.current = true;
      sendMessage(initialQuestion);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || streaming) return;
    setError("");

    const userMsg: Message = { role: "user", content: text.trim(), id: uid() };
    const assistantId = uid();

    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "", id: assistantId }]);
    setInput("");
    setStreaming(true);

    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    abortRef.current = new AbortController();
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text.trim(), history }),
        signal: abortRef.current.signal,
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: "Error del servidor" }));
        throw new Error(err.error ?? `Error ${res.status}`);
      }

      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let full = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        full += chunk;
        setMessages((prev) =>
          prev.map((m) => m.id === assistantId ? { ...m, content: full } : m)
        );
      }
    } catch (err) {
      if ((err as Error).name === "AbortError") return;
      const msg = err instanceof Error ? err.message : "Error desconocido";
      setError(msg);
      setMessages((prev) => prev.filter((m) => m.id !== assistantId));
    } finally {
      setStreaming(false);
      abortRef.current = null;
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [messages, streaming]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    sendMessage(input);
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage(input);
    }
  }

  const showSuggestions = messages.length === 0;

  return (
    <div className="flex flex-col" style={{ height: "calc(100dvh - 200px)", minHeight: 520, maxHeight: 820 }}>

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-4 shrink-0">
        <div className="flex items-center gap-3">
          <div style={{ width: 3, height: 22, background: "var(--color-wc-gold)", borderRadius: 2 }} />
          <div>
            <h2 style={{ fontFamily: "var(--font-display)", fontSize: "1.4rem", letterSpacing: "0.05em", color: "var(--color-ink-primary)", margin: 0 }}>
              {T.chatTab}
            </h2>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", letterSpacing: "0.14em", color: "var(--color-ink-muted)", textTransform: "uppercase", margin: 0 }}>
              {T.chatPowered}
            </p>
          </div>
        </div>
        {messages.length > 0 && (
          <button
            onClick={() => { setMessages([]); setError(""); }}
            style={{
              fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.1em",
              textTransform: "uppercase", padding: "0.3rem 0.7rem", border: "1px solid rgba(255,255,255,0.10)",
              borderRadius: 4, background: "transparent", color: "var(--color-ink-muted)",
              cursor: "pointer", transition: "color 0.14s, border-color 0.14s",
            }}
          >
            ✕ Nueva
          </button>
        )}
      </div>

      {/* ── Mensajes ── */}
      <div
        className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-hide"
        style={{ paddingBottom: "0.5rem" }}
      >
        <AnimatePresence initial={false}>
          {showSuggestions ? (
            <motion.div
              key="suggestions"
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-4 pt-6"
            >
              <span className="text-4xl">⚽</span>
              <p className="text-center text-sm max-w-sm" style={{ fontFamily: "var(--font-body)", color: "var(--color-ink-muted)", lineHeight: 1.6 }}>
                {T.chatEmpty}
              </p>
              <div className="flex flex-wrap gap-2 justify-center mt-2">
                {suggestions.map((s: string, i: number) => (
                  <motion.button
                    key={i}
                    initial={{ opacity: 0, scale: 0.9 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.06 }}
                    onClick={() => sendMessage(s)}
                    className="text-xs px-3 py-2 rounded-xl text-left transition-all"
                    style={{
                      fontFamily: "var(--font-body)",
                      background: "var(--color-arena-elevated)",
                      border: "1px solid rgba(255,255,255,0.07)",
                      color: "var(--color-ink-secondary)",
                      cursor: "pointer",
                      maxWidth: "22rem",
                    }}
                  >
                    {s}
                  </motion.button>
                ))}
              </div>
            </motion.div>
          ) : (
            messages.map((msg) => (
              <motion.div
                key={msg.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className="max-w-[88%] sm:max-w-[76%] rounded-2xl px-4 py-3 text-sm"
                  style={{
                    fontFamily: "var(--font-body)",
                    lineHeight: 1.65,
                    ...(msg.role === "user"
                      ? {
                          background: "var(--color-wc-red)",
                          color: "#fff",
                          borderBottomRightRadius: 4,
                        }
                      : {
                          background: "var(--color-arena-card)",
                          color: "var(--color-ink-primary)",
                          border: "1px solid rgba(255,255,255,0.07)",
                          borderBottomLeftRadius: 4,
                        }),
                  }}
                >
                  {msg.role === "assistant" && msg.content === "" ? (
                    <ThinkingDots label={T.chatThinking} />
                  ) : (
                    <FormattedText text={msg.content} isStreaming={streaming && msg === messages[messages.length - 1]} />
                  )}
                </div>
              </motion.div>
            ))
          )}
        </AnimatePresence>

        {/* Error */}
        {error && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="rounded-xl px-4 py-3 text-xs"
            style={{
              background: "rgba(207,10,44,0.08)",
              border: "1px solid rgba(207,10,44,0.25)",
              color: "var(--color-wc-red)",
              fontFamily: "var(--font-mono)",
            }}
          >
            {T.chatError} — {error}
          </motion.div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <form
        onSubmit={handleSubmit}
        className="shrink-0 mt-3 flex gap-2 items-end"
        style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.875rem" }}
      >
        <textarea
          ref={inputRef}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={T.chatPlaceholder}
          rows={1}
          disabled={streaming}
          className="flex-1 resize-none rounded-xl px-4 py-3 text-sm focus:outline-none transition-colors"
          style={{
            fontFamily: "var(--font-body)",
            background: "var(--color-arena-elevated)",
            border: "1px solid rgba(255,255,255,0.08)",
            color: "var(--color-ink-primary)",
            lineHeight: 1.5,
            maxHeight: 120,
            opacity: streaming ? 0.6 : 1,
          }}
          onInput={(e) => {
            const el = e.currentTarget;
            el.style.height = "auto";
            el.style.height = Math.min(el.scrollHeight, 120) + "px";
          }}
        />
        <motion.button
          type="submit"
          disabled={streaming || !input.trim()}
          whileTap={streaming || !input.trim() ? {} : { scale: 0.95 }}
          className="shrink-0 w-11 h-11 rounded-xl flex items-center justify-center transition-all"
          style={{
            background:
              streaming || !input.trim()
                ? "rgba(212,168,67,0.15)"
                : "linear-gradient(135deg, #D4A843, #F5CC6A)",
            border: "none",
            cursor: streaming || !input.trim() ? "not-allowed" : "pointer",
            boxShadow:
              streaming || !input.trim() ? "none" : "0 4px 14px rgba(212,168,67,0.3)",
            color: streaming || !input.trim() ? "rgba(212,168,67,0.4)" : "#07070F",
          }}
        >
          {streaming ? (
            <motion.span
              animate={{ rotate: 360 }}
              transition={{ duration: 0.9, repeat: Infinity, ease: "linear" }}
              className="inline-block w-4 h-4 rounded-full border-2 border-current border-t-transparent"
            />
          ) : (
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          )}
        </motion.button>
      </form>
    </div>
  );
}

/* ── Animación "pensando" ── */
function ThinkingDots({ label }: { label: string }) {
  return (
    <div className="flex items-center gap-2" style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", fontSize: "0.75rem" }}>
      <span>{label}</span>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          animate={{ opacity: [0.2, 1, 0.2] }}
          transition={{ duration: 1.1, repeat: Infinity, delay: i * 0.22 }}
          style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "var(--color-wc-gold)" }}
        />
      ))}
    </div>
  );
}

/* ── Texto con cursor de streaming ── */
function FormattedText({ text, isStreaming }: { text: string; isStreaming: boolean }) {
  return (
    <span style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
      {text}
      {isStreaming && (
        <motion.span
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity }}
          style={{ display: "inline-block", width: 2, height: "1em", background: "var(--color-wc-gold)", marginLeft: 2, verticalAlign: "text-bottom", borderRadius: 1 }}
        />
      )}
    </span>
  );
}
