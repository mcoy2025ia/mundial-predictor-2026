/**
 * POST /api/chat
 * RAG sobre datos del Mundial 2026 + respuesta streaming via DeepSeek.
 *
 * Protecciones de costo:
 *   1. Topic filter  — descarta preguntas fuera del fútbol/Mundial antes de tocar APIs
 *   2. Response cache — Map en memoria, SHA-256 de pregunta normalizada, TTL 2h, max 400 entradas
 *   3. Rate limit    — ventana deslizante 20 req/hora por IP; retorna 429 si se supera
 *
 * Body: { message: string, history: { role: "user"|"assistant", content: string }[] }
 * Response: text/plain streaming
 */
import { createHash } from "crypto";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { NextRequest, NextResponse } from "next/server";

// ── Types ──────────────────────────────────────────────────────────────────────
interface RagChunk  { id: string; type: string; text: string; embedding: number[] }
interface RagIndex  { model: string; dimensions: number; n_chunks: number; chunks: RagChunk[] }
interface Message   { role: "user" | "assistant"; content: string }
type DSMessage      = { role: "system" | "user" | "assistant"; content: string }

// ─────────────────────────────────────────────────────────────────────────────
//  1. TOPIC FILTER — palabras clave en ES / EN / PT que indican pregunta válida
// ─────────────────────────────────────────────────────────────────────────────
const FOOTBALL_KEYWORDS = [
  // tourneys / editions
  "mundial","world cup","copa","torneo","wc","2026","copa del mundo","coupe du monde",
  // football terms
  "fútbol","futbol","football","soccer","gol","goal","partido","match","game","jogo",
  "jornada","fase","grupo","group","ronda","round","octavos","cuartos","semifinal","final",
  "eliminatoria","knockout","playoff","penalti","penalty","shoot","shootout",
  // teams — the 48 WC2026 participants (partial, high-signal)
  "colombia","argentina","brasil","brazil","mexico","españa","spain","france","francia",
  "alemania","germany","england","inglaterra","portugal","países bajos","netherlands","holanda",
  "bélgica","belgium","croacia","croatia","japón","japan","marruecos","morocco","senegal",
  "nigeria","ghana","camerún","cameroon","costa de marfil","ivory coast","túnez","tunisia",
  "egipto","egypt","argelia","algeria","sudáfrica","south africa","corea","korea","iran",
  "arabia saudita","saudi","australia","iraq","jordania","jordan","uzbekistán","uzbekistan",
  "catar","qatar","estados unidos","united states","usa","canadá","canada","venezuela",
  "uruguay","ecuador","paraguay","chile","perú","peru","bolivia","panamá","panama",
  "haití","haiti","curazao","curacao","suecia","sweden","noruega","norway","austria",
  "chequia","czech","escocia","scotland","república checa","bosnia","suiza","switzerland",
  "turquía","turkey","nueva zelanda","new zealand","cape verde","cabo verde",
  // stats / model terms
  "elo","predicción","prediction","probabilidad","probability","modelo","model",
  "clasificación","standings","tabla","puntos","points","goles","goals","estadio","stadium",
  "sede","venue","árbitro","referee","lesión","injury","convocatoria","squad","selección",
  "seleccion","equipo","team","jugador","player","portero","goalkeeper","delantero",
  "mediocampista","defensa","defender","entrenador","coach","manager",
];

const KEYWORD_RE = new RegExp(FOOTBALL_KEYWORDS.join("|"), "i");

const OFF_TOPIC_REPLIES: Record<string, string> = {
  es: "Solo puedo responder preguntas sobre el Mundial FIFA 2026, equipos, predicciones y estadios. ¿Tienes alguna pregunta sobre el torneo?",
  en: "I can only answer questions about the FIFA World Cup 2026, teams, predictions, and venues. Do you have a question about the tournament?",
  pt: "Só consigo responder perguntas sobre a Copa do Mundo FIFA 2026, equipes, previsões e estádios. Você tem alguma pergunta sobre o torneio?",
};

function isFootballQuestion(text: string): boolean {
  return KEYWORD_RE.test(text);
}

function detectLang(text: string): "es" | "en" | "pt" {
  const lower = text.toLowerCase();
  const ptScore = (lower.match(/\b(você|brasil|copa|vou|não|está|equipe|jogo)\b/g) ?? []).length;
  const enScore = (lower.match(/\b(the|is|are|who|will|can|team|game|match|play)\b/g) ?? []).length;
  if (ptScore >= 2) return "pt";
  if (enScore >= 2) return "en";
  return "es";
}

// ─────────────────────────────────────────────────────────────────────────────
//  2. RESPONSE CACHE — module-level, TTL 2h, max 400 entradas
// ─────────────────────────────────────────────────────────────────────────────
const CACHE_TTL_MS  = 2 * 60 * 60 * 1000;  // 2 horas
const CACHE_MAX     = 400;

interface CacheEntry { response: string; ts: number }
const _responseCache = new Map<string, CacheEntry>();

const TOURNAMENT_TIME_ZONE = "America/Bogota";

function todayInTournamentTimeZone(date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: TOURNAMENT_TIME_ZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((p) => [p.type, p.value]));
  return `${byType.year}-${byType.month}-${byType.day}`;
}

function cacheKey(msg: string, scope = ""): string {
  const normalized = msg.trim().toLowerCase().replace(/\s+/g, " ");
  return createHash("sha256").update(`${scope}::${normalized}`).digest("hex").slice(0, 16);
}

function cacheGet(key: string): string | null {
  const entry = _responseCache.get(key);
  if (!entry) return null;
  if (Date.now() - entry.ts > CACHE_TTL_MS) { _responseCache.delete(key); return null; }
  return entry.response;
}

function cacheSet(key: string, response: string): void {
  if (_responseCache.size >= CACHE_MAX) {
    // evict oldest
    const oldest = [..._responseCache.entries()].sort((a, b) => a[1].ts - b[1].ts)[0];
    if (oldest) _responseCache.delete(oldest[0]);
  }
  _responseCache.set(key, { response, ts: Date.now() });
}

// ─────────────────────────────────────────────────────────────────────────────
//  3. RATE LIMITER — ventana deslizante 20 req / 60 min por IP
// ─────────────────────────────────────────────────────────────────────────────
const RATE_LIMIT      = 20;
const RATE_WINDOW_MS  = 60 * 60 * 1000;  // 1 hora

interface RateEntry { timestamps: number[] }
const _rateLimiter = new Map<string, RateEntry>();

function getClientIP(req: NextRequest): string {
  return (
    req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ??
    req.headers.get("x-real-ip") ??
    "unknown"
  );
}

/** Devuelve true si la IP supera el límite, false si está dentro. */
function isRateLimited(ip: string): boolean {
  const now   = Date.now();
  const entry = _rateLimiter.get(ip) ?? { timestamps: [] };
  // purgar timestamps fuera de la ventana
  entry.timestamps = entry.timestamps.filter((t) => now - t < RATE_WINDOW_MS);
  if (entry.timestamps.length >= RATE_LIMIT) {
    _rateLimiter.set(ip, entry);
    return true;
  }
  entry.timestamps.push(now);
  _rateLimiter.set(ip, entry);
  return false;
}

function remainingRequests(ip: string): number {
  const now   = Date.now();
  const entry = _rateLimiter.get(ip);
  if (!entry) return RATE_LIMIT;
  const active = entry.timestamps.filter((t) => now - t < RATE_WINDOW_MS).length;
  return Math.max(0, RATE_LIMIT - active);
}

// ─────────────────────────────────────────────────────────────────────────────
//  RAG Index — lazy load + module-level cache
// ─────────────────────────────────────────────────────────────────────────────
let _ragIndex: RagChunk[] | null = null;

function loadRagIndex(): RagChunk[] {
  if (_ragIndex) return _ragIndex;
  const p = join(process.cwd(), "public", "data", "rag_index.json");
  if (!existsSync(p)) return [];
  try {
    const parsed: RagIndex = JSON.parse(readFileSync(p, "utf-8"));
    _ragIndex = parsed.chunks ?? [];
    return _ragIndex;
  } catch { return []; }
}

// ─────────────────────────────────────────────────────────────────────────────
//  Tournament context — lazy load group matches + standings for chat context
// ─────────────────────────────────────────────────────────────────────────────
interface GroupMatch { date: string; round: string; ground: string; team1: string; team2: string; team1_flag: string; team2_flag: string; t1_win: number; draw: number; t2_win: number }
interface StandingEntry { team: string; flag: string; first: number; second: number }
interface LivePrediction {
  home_team: string;
  away_team: string;
  p_home: number;
  p_draw: number;
  p_away: number;
  kickoff?: string;
  group?: string;
  venue?: string;
  round?: string;
  model?: string;
  group_context?: Record<string, unknown>;
  agent_notes?: Record<string, string>;
}

let _groupMatches: Record<string, GroupMatch[]> | null = null;
let _groupStandings: Record<string, StandingEntry[]> | null = null;
let _livePredictions: LivePrediction[] | null = null;

function loadGroupMatches(): Record<string, GroupMatch[]> {
  if (_groupMatches) return _groupMatches;
  const p = join(process.cwd(), "public", "data", "group_matches.json");
  try { _groupMatches = JSON.parse(readFileSync(p, "utf-8")); }
  catch { _groupMatches = {}; }
  return _groupMatches!;
}

function loadGroupStandings(): Record<string, StandingEntry[]> {
  if (_groupStandings) return _groupStandings;
  const p = join(process.cwd(), "public", "data", "group_standings.json");
  try { _groupStandings = JSON.parse(readFileSync(p, "utf-8")); }
  catch { _groupStandings = {}; }
  return _groupStandings!;
}

function loadLivePredictions(): LivePrediction[] {
  if (_livePredictions) return _livePredictions;
  const p = join(process.cwd(), "public", "data", "live_predictions.json");
  try { _livePredictions = JSON.parse(readFileSync(p, "utf-8")); }
  catch { _livePredictions = []; }
  return _livePredictions!;
}

function dateInTournamentTimeZone(value?: string): string {
  if (!value) return "";
  const d = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(d.getTime())) return "";
  return todayInTournamentTimeZone(d);
}

function fmtPct(n: number): string {
  return `${Math.round(n * 1000) / 10}%`;
}

function livePredictionLine(p: LivePrediction, localDate = dateInTournamentTimeZone(p.kickoff)): string {
  const ctx = p.group_context ?? {};
  const pressure = ctx.matchday
    ? ` | J${ctx.matchday}: ${p.home_team} ${ctx.home_points ?? "?"}pts, ${p.away_team} ${ctx.away_points ?? "?"}pts`
    : "";
  const simultaneous = ctx.simultaneous_group_matches ? ` | Simultaneo grupo: ${ctx.simultaneous_group_matches}` : "";
  const thirds = ctx.third_place_context ? ` | Mejores terceros: ${ctx.third_place_context}` : "";
  const agents = p.agent_notes
    ? ` | Agentes: ${Object.entries(p.agent_notes).map(([k, v]) => `${k}: ${v}`).join(" ; ")}`
    : "";
  return `${localDate} ${p.group ?? ""}: ${p.home_team} vs ${p.away_team} - ${p.venue ?? "sede ?"} - Modelo vivo ${p.model ?? "live"}: ${p.home_team} ${fmtPct(p.p_home)}, Empate ${fmtPct(p.p_draw)}, ${p.away_team} ${fmtPct(p.p_away)} (${p.round ?? ""})${pressure}${simultaneous}${thirds}${agents}`;
}

function detectVenueQuery(message: string): string | null {
  const q = message.toLowerCase();
  if (q.includes("mexico city") || q.includes("ciudad de mexico") || q.includes("ciudad de méxico")) {
    return "Mexico City";
  }
  if (q.includes("guadalajara")) return "Guadalajara";
  if (q.includes("monterrey")) return "Monterrey";
  if (q.includes("atlanta")) return "Atlanta";
  if (q.includes("houston")) return "Houston";
  if (q.includes("miami")) return "Miami";
  return null;
}

function buildTournamentContext(message = ""): string {
  const today = todayInTournamentTimeZone();
  const groupMatches = loadGroupMatches();
  const standings = loadGroupStandings();
  const livePredictions = loadLivePredictions();

  // Matches today
  const todayMatches: string[] = [];
  for (const [group, matches] of Object.entries(groupMatches)) {
    for (const m of matches) {
      if (m.date === today) {
        todayMatches.push(
          `Grupo ${group}: ${m.team1_flag} ${m.team1} vs ${m.team2_flag} ${m.team2} — Sede: ${m.ground} — Probs: ${Math.round(m.t1_win * 100)}% / ${Math.round(m.draw * 100)}% / ${Math.round(m.t2_win * 100)}% (${m.round})`
        );
      }
    }
  }

  // Next 3 days of upcoming matches (excl. today)
  const upcoming: string[] = [];
  for (const [group, matches] of Object.entries(groupMatches)) {
    for (const m of matches) {
      if (m.date > today) {
        upcoming.push(`${m.date} Grupo ${group}: ${m.team1_flag} ${m.team1} vs ${m.team2_flag} ${m.team2} (${m.round})`);
      }
    }
  }
  upcoming.sort();
  const next3Days = upcoming.slice(0, 16);

  const liveToday = livePredictions.filter((p) => dateInTournamentTimeZone(p.kickoff) === today);
  const liveUpcoming = livePredictions
    .filter((p) => {
      const d = dateInTournamentTimeZone(p.kickoff);
      return d && d > today;
    })
    .sort((a, b) => String(a.kickoff ?? "").localeCompare(String(b.kickoff ?? "")))
    .slice(0, 16);
  const requestedVenue = detectVenueQuery(message);
  const liveTodayAtVenue = requestedVenue
    ? liveToday.filter((p) => (p.venue ?? "").toLowerCase().includes(requestedVenue.toLowerCase()))
    : [];

  // Group standings summary
  const standingLines: string[] = [];
  for (const [group, teams] of Object.entries(standings)) {
    const line = teams.map((t) => `${t.flag}${t.team} (1ro: ${Math.round(t.first * 100)}%)`).join(", ");
    standingLines.push(`Grupo ${group}: ${line}`);
  }

  const lines: string[] = [
    `FECHA HOY (${TOURNAMENT_TIME_ZONE}): ${today}`,
    "",
    todayMatches.length > 0
      ? `PARTIDOS DE HOY (${today}):\n${todayMatches.join("\n")}`
      : `No hay partidos de grupo programados para hoy (${today}).`,
    "",
    next3Days.length > 0
      ? `PRÓXIMOS PARTIDOS:\n${next3Days.join("\n")}`
      : "",
    "",
    `PROBABILIDADES DE CLASIFICAR PRIMERO POR GRUPO (modelo):\n${standingLines.join("\n")}`,
  ];
  const liveLines: string[] = [
    "",
    liveToday.length > 0
      ? `PREDICCIONES VIVAS DE HOY (${today}) - fuente preferida para preguntas de partidos:\n${liveToday.map((p) => livePredictionLine(p, today)).join("\n")}`
      : `No hay predicciones vivas para hoy (${today}).`,
    "",
    liveUpcoming.length > 0
      ? `PREDICCIONES VIVAS PROXIMAS:\n${liveUpcoming.map((p) => livePredictionLine(p)).join("\n")}`
      : "",
    "",
    requestedVenue
      ? liveTodayAtVenue.length > 0
        ? `FILTRO DE SEDE SOLICITADA HOY (${requestedVenue}):\n${liveTodayAtVenue.map((p) => livePredictionLine(p, today)).join("\n")}`
        : `FILTRO DE SEDE SOLICITADA HOY (${requestedVenue}): no hay partidos hoy en esta sede. No sustituyas por partidos en otra ciudad.`
      : "",
  ];
  return [...lines, ...liveLines].filter((l) => l !== undefined).join("\n");
}

// ─────────────────────────────────────────────────────────────────────────────
//  Vector math
// ─────────────────────────────────────────────────────────────────────────────
function cosine(a: number[], b: number[]): number {
  let dot = 0, na = 0, nb = 0;
  for (let i = 0; i < a.length; i++) { dot += a[i]*b[i]; na += a[i]*a[i]; nb += b[i]*b[i]; }
  const d = Math.sqrt(na) * Math.sqrt(nb);
  return d === 0 ? 0 : dot / d;
}

function topK(query: number[], chunks: RagChunk[], k = 4): RagChunk[] {
  return chunks.length === 0 ? [] : chunks
    .map((c) => ({ chunk: c, score: cosine(query, c.embedding) }))
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map((x) => x.chunk);
}

// ─────────────────────────────────────────────────────────────────────────────
//  DashScope embedding
// ─────────────────────────────────────────────────────────────────────────────
async function embedQuery(text: string): Promise<number[] | null> {
  const key = process.env.DASHSCOPE_API_KEY;
  if (!key) return null;
  try {
    const res = await fetch(
      "https://dashscope.aliyuncs.com/compatible-mode/v1/embeddings",
      {
        method: "POST",
        headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: "text-embedding-v3", input: text, dimensions: 512, encoding_format: "float" }),
      }
    );
    if (!res.ok) return null;
    const data = await res.json();
    return data?.data?.[0]?.embedding ?? null;
  } catch { return null; }
}

// ─────────────────────────────────────────────────────────────────────────────
//  System prompt
// ─────────────────────────────────────────────────────────────────────────────
const SYSTEM_PROMPT = `Eres el asistente oficial de Mundial Predictor 2026, una app de predicciones del FIFA World Cup 2026.

Tienes acceso a los siguientes datos reales del torneo (actualizados diariamente):
- Calendario completo de partidos de grupo con fechas, sedes y probabilidades del modelo ML
- Probabilidades de clasificación por grupo (modelo XGBoost + Poisson + ELO ensemble)
- Los 48 equipos participantes y sus grupos

INSTRUCCIONES:
- Responde SOLO sobre fútbol y el Mundial FIFA 2026
- Responde en el MISMO IDIOMA que la pregunta del usuario (español, inglés o portugués)
- Para preguntas sobre partidos de hoy o próximos, usa SIEMPRE el CONTEXTO DEL TORNEO que se te provee abajo — es la fuente de verdad
- Sé preciso con los números del contexto; las probabilidades son del modelo estadístico, no certezas
- Sé conciso (máx 3-4 párrafos)
- No inventes resultados, lesiones, goles ni datos que no estén en el contexto

CONTEXTO DEL TORNEO (datos actuales):
{TOURNAMENT_CONTEXT}

CONTEXTO ADICIONAL (RAG):
{RAG_CONTEXT}`;

// ─────────────────────────────────────────────────────────────────────────────
//  LLM streaming — DeepSeek primario, Anthropic fallback
// ─────────────────────────────────────────────────────────────────────────────
async function streamLLM(
  messages: DSMessage[],
  signal: AbortSignal
): Promise<ReadableStream<Uint8Array>> {
  // ── Intento 1: DeepSeek ─────────────────────────────────────────────────
  const dsKey = (process.env.DEEPSEEK_API_KEY ?? "").replace(/^﻿/, "").trim();
  if (dsKey) {
    try {
      const res = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${dsKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({ model: "deepseek-chat", messages, stream: true, max_tokens: 700, temperature: 0.65 }),
        signal,
      });
      if (res.ok) return buildOpenAIStream(res);
      // saldo insuficiente u otro error → caer al fallback
    } catch { /* network error → fallback */ }
  }

  // ── Fallback: Anthropic claude-sonnet-4-6 ───────────────────────────────
  const anKey = (process.env.ANTHROPIC_API_KEY ?? "").replace(/^﻿/, "").trim();
  if (!anKey) throw new Error("Sin proveedor LLM disponible (configura DEEPSEEK_API_KEY o ANTHROPIC_API_KEY).");

  const system = messages.find((m) => m.role === "system")?.content ?? "";
  const userMessages = messages.filter((m) => m.role !== "system");
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": anKey, "anthropic-version": "2023-06-01", "Content-Type": "application/json" },
    body: JSON.stringify({ model: "claude-sonnet-4-6", max_tokens: 700, system, messages: userMessages, stream: true }),
    signal,
  });
  if (!res.ok) throw new Error(`Anthropic error ${res.status}: ${await res.text()}`);
  return buildAnthropicStream(res);
}

function buildOpenAIStream(res: Response): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const json = line.slice(6).trim();
          if (json === "[DONE]") { controller.close(); return; }
          try {
            const content = JSON.parse(json)?.choices?.[0]?.delta?.content;
            if (content) controller.enqueue(encoder.encode(content));
          } catch { /* skip */ }
        }
      }
      controller.close();
    },
  });
}

function buildAnthropicStream(res: Response): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    async start(controller) {
      const reader  = res.body!.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const parsed = JSON.parse(line.slice(6).trim());
            if (parsed.type === "content_block_delta" && parsed.delta?.type === "text_delta")
              controller.enqueue(encoder.encode(parsed.delta.text));
            else if (parsed.type === "message_stop") { controller.close(); return; }
          } catch { /* skip */ }
        }
      }
      controller.close();
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Streamed cache response (sends cached text as a stream so client code works)
// ─────────────────────────────────────────────────────────────────────────────
function streamText(text: string): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      // Send in small chunks to keep streaming UX
      const words = text.split(" ");
      let i = 0;
      function push() {
        if (i >= words.length) { controller.close(); return; }
        const chunk = words.slice(i, i + 5).join(" ") + (i + 5 < words.length ? " " : "");
        controller.enqueue(encoder.encode(chunk));
        i += 5;
        setTimeout(push, 12);
      }
      push();
    },
  });
}

// ─────────────────────────────────────────────────────────────────────────────
//  Handler
// ─────────────────────────────────────────────────────────────────────────────
export async function POST(req: NextRequest) {
  const ip = getClientIP(req);

  // ── 1. Rate limit ─────────────────────────────────────────────────────────
  if (isRateLimited(ip)) {
    return NextResponse.json(
      { error: "Límite de 20 consultas por hora alcanzado. Inténtalo más tarde." },
      {
        status: 429,
        headers: {
          "Retry-After": "3600",
          "X-RateLimit-Limit":     String(RATE_LIMIT),
          "X-RateLimit-Remaining": "0",
        },
      }
    );
  }

  let message: string;
  let history: Message[];
  try {
    const body = await req.json();
    message = String(body.message ?? "").trim();
    history = Array.isArray(body.history) ? body.history : [];
  } catch {
    return NextResponse.json({ error: "JSON inválido" }, { status: 400 });
  }
  if (!message) return NextResponse.json({ error: "message requerido" }, { status: 400 });

  const remaining = remainingRequests(ip);

  // ── 2. Topic filter ───────────────────────────────────────────────────────
  if (!isFootballQuestion(message)) {
    const lang = detectLang(message);
    const reply = OFF_TOPIC_REPLIES[lang];
    return new Response(streamText(reply), {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Source":              "topic-filter",
        "X-RateLimit-Remaining": String(remaining),
      },
    });
  }

  // ── 3. Response cache ─────────────────────────────────────────────────────
  const key     = cacheKey(message, todayInTournamentTimeZone());
  const cached  = cacheGet(key);
  if (cached) {
    return new Response(streamText(cached), {
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
        "Cache-Control": "no-cache",
        "X-Source":              "cache",
        "X-RateLimit-Remaining": String(remaining),
      },
    });
  }

  // ── 4. RAG retrieval ──────────────────────────────────────────────────────
  let contextText = "";
  const queryVec = await embedQuery(message);
  if (queryVec) {
    const index = loadRagIndex();
    if (index.length > 0) {
      const relevant = topK(queryVec, index, 5);
      contextText = relevant.map((c) => `[${c.type.toUpperCase()}]\n${c.text}`).join("\n\n---\n\n");
    }
  }

  const tournamentCtx = buildTournamentContext(message);
  const venueGuard = [
    "REGLAS CRITICAS DE FILTRO:",
    "- Si la pregunta menciona una sede o ciudad, filtra por sede exacta antes de hablar de equipos.",
    "- No confundas Mexico City con la seleccion Mexico.",
    "- Si no hay partido hoy en la sede mencionada, dilo explicitamente y no sustituyas por otro partido en otra ciudad.",
    "- Para preguntas con 'hoy', prioriza PREDICCIONES VIVAS DE HOY sobre otros bloques.",
    "",
  ].join("\n");
  const systemContent = venueGuard + SYSTEM_PROMPT
    .replace("{TOURNAMENT_CONTEXT}", tournamentCtx)
    .replace("{RAG_CONTEXT}", contextText || "Sin contexto RAG adicional.");

  const dsMessages: DSMessage[] = [
    { role: "system", content: systemContent },
    ...(history.slice(-6) as DSMessage[]),
    { role: "user", content: message },
  ];

  // ── 5. Stream LLM + capture para cache ───────────────────────────────────
  try {
    const upstream = await streamLLM(dsMessages, req.signal);

    // Tee the stream: one goes to client, one accumulates for cache
    const encoder  = new TextEncoder();
    const decoder  = new TextDecoder();
    let accumulated = "";

    const [forClient, forCache] = upstream.tee();

    // Background: accumulate and cache the full response
    (async () => {
      const reader = forCache.getReader();
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        accumulated += decoder.decode(value, { stream: true });
      }
      if (accumulated.length > 20) cacheSet(key, accumulated);
    })().catch(() => { /* don't fail the request if cache write fails */ });

    return new Response(forClient, {
      headers: {
        "Content-Type":          "text/plain; charset=utf-8",
        "Cache-Control":         "no-cache",
        "X-Source":              "anthropic",
        "X-Rag-Chunks":          contextText ? "5" : "0",
        "X-RateLimit-Remaining": String(remaining),
      },
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ error: msg }, { status: 503 });
  }
}
