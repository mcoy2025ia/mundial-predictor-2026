/**
 * POST /api/narrator
 *
 * Modo FULL (agent_summary presente): recibe JSON consolidado del partido →
 *   usa el system prompt "Narrator AI futbolero colombiano" → responde markdown.
 * Modo SIMPLE (legacy): match data mínimo → personas cortas por dialecto.
 *
 * Cache por partido+dialecto+modo (TTL 30 min). Rate limit 40 req/hora por IP.
 */
import { createHash } from "crypto";
import { existsSync, readFileSync } from "fs";
import { join } from "path";
import { NextRequest, NextResponse } from "next/server";

// ── System prompt FULL ─────────────────────────────────────────────────────
const FULL_SYSTEM = `Actúa como **Narrator AI futbolero colombiano** para una app de predicción del Mundial 2026.

Tu trabajo NO es recalcular el modelo.
Tu trabajo es convertir el JSON compacto recibido en una narración futbolera, clara, jocosa y regional.

Usa únicamente los datos recibidos.
No inventes lesiones, jugadores, cuotas, clima, sanciones, historial ni resultados.

## Dialectos disponibles

Usa el dialecto indicado en \`dialecto\`:

### bogotano
Tono urbano, irónico y futbolero.
Expresiones permitidas: "uy no", "parce", "qué visaje", "esto está pesado", "no den papaya", "se armó la vuelta", "pailas", "de alquilar balcón".

### paisa
Tono enérgico, competitivo y jocoso.
Expresiones permitidas: "parce", "pues", "home", "qué cosa tan brava", "esto está berraco", "ojo pues", "con verraquera", "no se pueden dormir".

### costeño
Tono alegre, sabroso y expresivo.
Expresiones permitidas: "eche", "mi llave", "compae", "ajá", "esa vaina", "se prendió esto", "le meten candela", "queda bailando con la más fea".

### boyacense
Tono noble, pícaro y campesino-jovial.
Expresiones permitidas: "sumercé", "ala", "mijitico", "la vaina está brava", "no se achante", "quedó viendo un chispero", "se le pone la ruana al revés".

### en
Tono sharp sports commentator. Analytical, bold, no fluff.

Regla: el dialecto debe sonar divertido, pero nunca ofensivo ni caricaturesco.

## Formato de salida obligatorio

Entrega solo Markdown. Usa esta estructura:

\`\`\`
👑 **[Título jocoso del partido]**

⚙️ **Narrator AI — modo [dialecto]**

[Apertura narrativa de 2 a 4 párrafos cortos]

🏟️ **Sede**
[Estadio, ciudad y ambiente]

🔥 **Contexto competitivo**
[Explica grupo o eliminatoria con presión, clasificación o eliminación]

📊 **Probabilidades del modelo**
[Emoji home]: [prob_home]%
🤝 Empate: [prob_draw]%
[Emoji away]: [prob_away]%

[Interpretación jocosa de las probabilidades]

⚽ **Marcador más probable**
[Marcador score_prediction]

[Interpretación del marcador]

🧠 **Capa Multi-Agente**
[Resumen del consenso de agentes en lenguaje humano]

🎯 **Lectura de agentes**
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]
- **[Agente / categoría]:** [veredicto, confianza y explicación jocosa]

🧾 **Conclusión final**
[Predicción final, favorito, riesgo principal y frase regional de cierre]
\`\`\`

## Reglas de ahorro de tokens

1. No repitas datos innecesarios.
2. No expliques fórmulas.
3. No menciones que eres un modelo de lenguaje.
4. No hagas análisis largo por agente.
5. Máximo 1 frase jocosa por sección.
6. Máximo 900 palabras.
7. Si agent_summary trae pocos agentes, trabaja solo con esos.
8. Si el consenso está dividido, dilo claramente.
9. Si el dialecto cambia, conserva el análisis y solo cambia el estilo narrativo.
10. No generes recomendaciones de apuestas ni manejo de dinero.

Genera la narración final lista para mostrarse en la app.`;

// ── System prompts SIMPLE (legacy) ────────────────────────────────────────
const PERSONA: Record<string, string> = {
  bogotano: `Eres CACHACONARRADOR, comentarista de Bogotá. Dialecto cachaco: "parce", "bacano", "chimba", "no le dé papaya", "manda la parada". EXACTAMENTE 3 oraciones cortas. Sin emojis.`,
  paisa:    `Eres PAISANARRADOR, comentarista de Medellín. Dialecto paisa: "parcero", "berraco", "de una", "no se raja". EXACTAMENTE 3 oraciones. Sin emojis.`,
  boyaco:   `Eres BOYACONARRADOR, comentarista boyacense. Dialecto: "sumercé", "juerte", "poquitico", "pos mire". EXACTAMENTE 3 oraciones. Sin emojis.`,
  costeño:  `Eres COSTERNARRADOR, comentarista barranquillero. Dialecto: "mano", "epa", "ombe", "vaina", "acho". EXACTAMENTE 3 oraciones. Sin emojis.`,
  en:       `You are a sharp World Cup commentator. Write EXACTLY 3 punchy sentences. No emojis.`,
};

const SCENARIO_CTX: Record<string, string> = {
  titan_clash:     "Duelo de élite: ambos en el top 12 mundial.",
  continental_war: "Clásico de la misma confederación.",
  redemption:      "El underdog tiene más experiencia mundialista.",
  perfect_storm:   "El modelo no encuentra favorito claro.",
  executioner:     "Un favorito claro vs rival con menos ELO.",
  equilibrio:      "Partido abierto y equilibrado.",
};

// ── Pre-computed narrations (generated daily by scripts/precompute_narrations.py) ──
let _narrations: Record<string, string> | null = null;

function loadNarrations(): Record<string, string> {
  if (_narrations) return _narrations;
  const p = join(process.cwd(), "public", "data", "narrations.json");
  if (!existsSync(p)) { _narrations = {}; return {}; }
  try {
    _narrations = JSON.parse(readFileSync(p, "utf-8"));
    return _narrations!;
  } catch { _narrations = {}; return {}; }
}

// ── Cache ──────────────────────────────────────────────────────────────────
interface CacheEntry { text: string; ts: number }
const _cache = new Map<string, CacheEntry>();
const CACHE_TTL = 30 * 60 * 1000;

function cacheKey(parts: string[]) {
  return createHash("sha256").update(parts.join("__")).digest("hex").slice(0, 22);
}
function cacheGet(k: string) {
  const e = _cache.get(k);
  if (!e) return null;
  if (Date.now() - e.ts > CACHE_TTL) { _cache.delete(k); return null; }
  return e.text;
}
function cacheSet(k: string, text: string) {
  if (_cache.size >= 300) {
    const oldest = [..._cache.entries()].sort((a, b) => a[1].ts - b[1].ts)[0];
    if (oldest) _cache.delete(oldest[0]);
  }
  _cache.set(k, { text, ts: Date.now() });
}

// ── Rate limit ─────────────────────────────────────────────────────────────
const _rl = new Map<string, number[]>();
function isRateLimited(ip: string) {
  const now = Date.now();
  const ts = (_rl.get(ip) ?? []).filter(t => now - t < 3_600_000);
  if (ts.length >= 40) { _rl.set(ip, ts); return true; }
  ts.push(now);
  _rl.set(ip, ts);
  return false;
}
function getIP(req: NextRequest) {
  return req.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
}

// ── Simulated stream for cache hits ──────────────────────────────────────
function streamCached(text: string): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  return new ReadableStream({
    start(ctrl) {
      const words = text.split(" ");
      let i = 0;
      function push() {
        if (i >= words.length) { ctrl.close(); return; }
        ctrl.enqueue(enc.encode(words.slice(i, i + 6).join(" ") + (i + 6 < words.length ? " " : "")));
        i += 6;
        setTimeout(push, 14);
      }
      push();
    },
  });
}

// ── LLM streaming — DeepSeek primario, Anthropic fallback ─────────────────
async function callLLM(
  systemPrompt: string,
  userMsg: string,
  maxTokens: number,
  signal: AbortSignal
): Promise<ReadableStream<Uint8Array> | null> {
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  let accumulated = "";

  function wrapStream(
    res: Response,
    extractChunk: (parsed: unknown) => string | null,
    isDone: (parsed: unknown) => boolean
  ): ReadableStream<Uint8Array> {
    return new ReadableStream<Uint8Array>({
      async start(ctrl) {
        const reader = res.body!.getReader();
        let buffer = "";
        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += dec.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              if (!line.startsWith("data: ")) continue;
              const json = line.slice(6).trim();
              if (json === "[DONE]") { ctrl.close(); return; }
              try {
                const parsed = JSON.parse(json);
                if (isDone(parsed)) { ctrl.close(); return; }
                const chunk = extractChunk(parsed);
                if (chunk) { accumulated += chunk; ctrl.enqueue(enc.encode(chunk)); }
              } catch { /* skip */ }
            }
          }
        } finally {
          ctrl.close();
          if (accumulated.length > 50) cacheSet("__pending__", accumulated);
        }
      },
    });
  }

  // ── Intento 1: DeepSeek ────────────────────────────────────────────────
  const dsKey = (process.env.DEEPSEEK_API_KEY ?? "").replace(/^﻿/, "").trim();
  if (dsKey) {
    try {
      const res = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { Authorization: `Bearer ${dsKey}`, "Content-Type": "application/json" },
        body: JSON.stringify({
          model: "deepseek-chat",
          messages: [{ role: "system", content: systemPrompt }, { role: "user", content: userMsg }],
          stream: true, max_tokens: maxTokens, temperature: 0.9,
        }),
        signal,
      });
      if (res.ok && res.body) {
        return wrapStream(
          res,
          (p: unknown) => (p as { choices?: { delta?: { content?: string } }[] })?.choices?.[0]?.delta?.content ?? null,
          () => false
        );
      }
    } catch { /* fallback */ }
  }

  // ── Fallback: Anthropic claude-sonnet-4-6 ─────────────────────────────
  const anKey = (process.env.ANTHROPIC_API_KEY ?? "").replace(/^﻿/, "").trim();
  if (!anKey) return null;
  const res = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": anKey, "anthropic-version": "2023-06-01", "Content-Type": "application/json" },
    body: JSON.stringify({
      model: "claude-sonnet-4-6", max_tokens: maxTokens,
      system: systemPrompt, messages: [{ role: "user", content: userMsg }], stream: true,
    }),
    signal,
  });
  if (!res.ok || !res.body) return null;
  return wrapStream(
    res,
    (p: unknown) => {
      const parsed = p as { type?: string; delta?: { type?: string; text?: string } };
      return parsed.type === "content_block_delta" && parsed.delta?.type === "text_delta"
        ? (parsed.delta.text ?? null) : null;
    },
    (p: unknown) => (p as { type?: string }).type === "message_stop"
  );
}

// ── POST ──────────────────────────────────────────────────────────────────
export async function POST(req: NextRequest) {
  const ip = getIP(req);
  if (isRateLimited(ip)) {
    return NextResponse.json({ error: "Rate limit" }, { status: 429, headers: { "Retry-After": "3600" } });
  }

  let body: Record<string, unknown>;
  try { body = await req.json(); }
  catch { return NextResponse.json({ error: "JSON inválido" }, { status: 400 }); }

  const home = String(body.home ?? "").trim();
  const away = String(body.away ?? "").trim();
  const lang = String(body.lang ?? "bogotano");
  if (!home || !away) return NextResponse.json({ error: "home y away requeridos" }, { status: 400 });

  const isFullMode = Array.isArray(body.agent_summary);

  // Build cache key
  const key = isFullMode
    ? cacheKey([home, away, lang, "full"])
    : cacheKey([home, away, lang, String(body.scenario ?? "")]);

  // ── Pre-computed narration (FULL mode only, keyed by home|away|lang) ──────
  if (isFullMode) {
    const narrations = loadNarrations();
    const narKey = `${home}|${away}|${lang}`;
    const precomputed = narrations[narKey];
    if (precomputed) {
      return new Response(streamCached(precomputed), {
        headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Source": "precomputed" },
      });
    }
  }

  const cached = cacheGet(key);
  if (cached) {
    return new Response(streamCached(cached), {
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store", "X-Source": "cache" },
    });
  }

  const hasLLM = (process.env.DEEPSEEK_API_KEY ?? "").replace(/^﻿/, "").trim() ||
                 (process.env.ANTHROPIC_API_KEY ?? "").replace(/^﻿/, "").trim();
  if (!hasLLM) {
    return NextResponse.json({ error: "Sin proveedor LLM configurado" }, { status: 503 });
  }

  let systemPrompt: string;
  let userMsg: string;
  let maxTokens: number;

  if (isFullMode) {
    // ── FULL mode: user's complete JSON ──
    systemPrompt = FULL_SYSTEM;
    userMsg = JSON.stringify(body, null, 0);
    maxTokens = 1400;
  } else {
    // ── SIMPLE mode: short narrator ──
    const scenario = String(body.scenario ?? "equilibrio");
    systemPrompt = PERSONA[lang] ?? PERSONA.bogotano;
    userMsg = `Partido: ${home} vs ${away}
Probs: ${home} ${body.homeWin}% · Empate ${body.draw}% · ${away} ${body.awayWin}%
ELO: ${home} ${body.homeElo} (#${body.homeRank}) — ${away} ${body.awayElo} (#${body.awayRank})
Exp. mundialista: ${home} ${body.homeWcMatches} — ${away} ${body.awayWcMatches} partidos
Goles/partido: ${home} ${body.homeGoals} — ${away} ${body.awayGoals}
Contexto: ${SCENARIO_CTX[scenario] ?? scenario}
Narra este partido.`;
    maxTokens = 300;
  }

  try {
    const upstream = await callLLM(systemPrompt, userMsg, maxTokens, req.signal);
    if (!upstream) return NextResponse.json({ error: "Sin proveedor LLM disponible (DeepSeek o Anthropic)" }, { status: 503 });

    // Save pending cache key after stream
    _cache.delete("__pending__");
    setTimeout(() => {
      const text = cacheGet("__pending__");
      if (text) { _cache.delete("__pending__"); cacheSet(key, text); }
    }, 8000);

    return new Response(upstream, {
      headers: { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" },
    });
  } catch (err) {
    if ((err as Error).name === "AbortError") return new Response(null, { status: 499 });
    return NextResponse.json({ error: String(err) }, { status: 503 });
  }
}
