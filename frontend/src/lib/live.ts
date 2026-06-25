import type { FixedResults, GroupMatch, LiveMatch, Prediction } from "@/types";

/**
 * Resultados reales del Mundial 2026.
 * Fuente primaria: /api/live (proxy cacheado a football-data.org).
 * Fallback: openfootball (GitHub raw, sin API key) si la API no responde
 * o no hay token configurado. Si ambos fallan, la app sigue funcionando
 * solo con predicciones.
 */

const API_URL = "/api/live";
const OPENFOOTBALL_URL =
  "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json";

/** Nombres de las fuentes externas → nombres del dataset del modelo */
const NAME_MAP: Record<string, string> = {
  // openfootball
  "Bosnia & Herzegovina": "Bosnia and Herzegovina",
  USA: "United States",
  "Curaçao": "Curacao",
  // football-data.org
  "Bosnia-Herzegovina": "Bosnia and Herzegovina",
  "Korea Republic": "South Korea",
  Czechia: "Czech Republic",
  "Côte d'Ivoire": "Ivory Coast",
  "Congo DR": "DR Congo",
  "Cape Verde Islands": "Cape Verde",
  "Cabo Verde": "Cape Verde",
  "IR Iran": "Iran",
};

function normalizeName(raw: unknown): string {
  const name =
    typeof raw === "string"
      ? raw
      : ((raw as { name?: string })?.name ?? "");
  return NAME_MAP[name] ?? name;
}

interface ApiMatch {
  team1: string;
  team2: string;
  score1: number | null;
  score2: number | null;
  group?: string;
  round?: string;
  utcDate?: string | null;
  status?: string;
}

/** Causa identificada de un fetch fallido, para el log de errores y el aviso en UI. */
export type FetchFailureReason =
  | "timeout"
  | "http_error"
  | "empty_data"
  | "parse_error"
  | "network_error";

export interface FetchFailure {
  reason: FetchFailureReason;
  detail: string;
}

function classifyError(err: unknown): FetchFailure {
  if (err instanceof DOMException && err.name === "TimeoutError") {
    return { reason: "timeout", detail: "La fuente no respondió en 8s" };
  }
  if (err instanceof SyntaxError) {
    return { reason: "parse_error", detail: `JSON inválido: ${err.message}` };
  }
  if (err instanceof TypeError) {
    return { reason: "network_error", detail: err.message || "Fallo de red (sin conexión o CORS)" };
  }
  return { reason: "network_error", detail: err instanceof Error ? err.message : String(err) };
}

/** Fuente primaria: football-data.org vía nuestro route handler. */
async function fetchFromApi(): Promise<{ matches: LiveMatch[] | null; failure?: FetchFailure }> {
  try {
    const res = await fetch(API_URL, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) {
      return { matches: null, failure: { reason: "http_error", detail: `/api/live respondió ${res.status} ${res.statusText}` } };
    }
    const data = await res.json();
    const raw: ApiMatch[] = data?.matches ?? [];
    if (raw.length === 0) {
      return { matches: null, failure: { reason: "empty_data", detail: "/api/live respondió 200 pero sin partidos (token vencido o sin fixtures hoy)" } };
    }
    return {
      matches: raw.map((m) => ({
        team1: normalizeName(m.team1),
        team2: normalizeName(m.team2),
        score1: typeof m.score1 === "number" ? m.score1 : null,
        score2: typeof m.score2 === "number" ? m.score2 : null,
        group: m.group,
        round: m.round,
        // día calendario del usuario: "partidos de hoy" según su zona horaria
        date: m.utcDate ? new Date(m.utcDate).toLocaleDateString("en-CA") : undefined,
        status: m.status,
        utc: m.utcDate ?? undefined,
      })),
    };
  } catch (err) {
    return { matches: null, failure: classifyError(err) };
  }
}

/** Fallback: dataset de openfootball en GitHub. Devuelve null si no se pudo consumir. */
async function fetchFromOpenfootball(): Promise<{ matches: LiveMatch[] | null; failure?: FetchFailure }> {
  try {
    const res = await fetch(OPENFOOTBALL_URL, { signal: AbortSignal.timeout(8000) });
    if (!res.ok) {
      return { matches: null, failure: { reason: "http_error", detail: `openfootball respondió ${res.status} ${res.statusText}` } };
    }
    const data = await res.json();
    const matches: unknown[] = data?.matches ?? [];
    if (matches.length === 0) {
      return { matches: null, failure: { reason: "empty_data", detail: "openfootball respondió 200 pero sin partidos" } };
    }
    return {
      matches: matches.map((m) => {
        const match = m as Record<string, unknown>;
        return {
          team1: normalizeName(match.team1),
          team2: normalizeName(match.team2),
          score1: typeof match.score1 === "number" ? match.score1 : null,
          score2: typeof match.score2 === "number" ? match.score2 : null,
          group: typeof match.group === "string" ? match.group : undefined,
          round: typeof match.round === "string" ? match.round : undefined,
          date: typeof match.date === "string" ? match.date : undefined,
        };
      }),
    };
  } catch (err) {
    return { matches: null, failure: classifyError(err) };
  }
}

/* ── Log de errores de fetch en vivo (persistido en localStorage, máx 30 entradas) ──
   Cada falla queda identificada con causa (reason) + detalle + fuente + timestamp,
   para diagnosticar por qué la tabla/marcadores no se actualizaron sin abrir la consola. */
export interface LiveErrorLogEntry {
  ts: string;
  source: "api" | "openfootball";
  reason: FetchFailureReason;
  detail: string;
}

const ERROR_LOG_KEY = "wc26_live_error_log";
const ERROR_LOG_MAX = 30;

function logLiveError(entry: LiveErrorLogEntry) {
  console.error(`[live] ${entry.source} falló (${entry.reason}): ${entry.detail}`);
  if (typeof window === "undefined") return;
  try {
    const raw = window.localStorage.getItem(ERROR_LOG_KEY);
    const log: LiveErrorLogEntry[] = raw ? JSON.parse(raw) : [];
    log.push(entry);
    while (log.length > ERROR_LOG_MAX) log.shift();
    window.localStorage.setItem(ERROR_LOG_KEY, JSON.stringify(log));
  } catch {
    // localStorage no disponible (modo privado, cuota llena, etc.) — el console.error ya quedó.
  }
}

/** Lee el log de errores guardado (más reciente al final). */
export function getLiveErrorLog(): LiveErrorLogEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(ERROR_LOG_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

export function clearLiveErrorLog() {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(ERROR_LOG_KEY);
  } catch {
    // no-op
  }
}

/**
 * Origen de los datos en vivo de la última lectura:
 *  - "api":         fuente primaria (football-data.org) respondió bien.
 *  - "openfootball": la primaria falló, se usó el respaldo (degradado).
 *  - "none":        ninguna fuente se pudo consumir (error duro).
 */
export type LiveSource = "api" | "openfootball" | "none";

export interface LiveFetchResult {
  matches: LiveMatch[];
  source: LiveSource;
  /** Causa de la falla más reciente (solo si source !== "api"). Para mostrar/loguear el motivo exacto. */
  lastFailure?: FetchFailure;
}

/** Lee resultados en vivo reportando de qué fuente vinieron (o si ninguna respondió, con la causa). */
export async function fetchLiveStatus(): Promise<LiveFetchResult> {
  const api = await fetchFromApi();
  if (api.matches) return { matches: api.matches, source: "api" };
  if (api.failure) logLiveError({ ts: new Date().toISOString(), source: "api", ...api.failure });

  const off = await fetchFromOpenfootball();
  if (off.matches && off.matches.length > 0) {
    return { matches: off.matches, source: "openfootball", lastFailure: api.failure };
  }
  if (off.failure) logLiveError({ ts: new Date().toISOString(), source: "openfootball", ...off.failure });

  return { matches: [], source: "none", lastFailure: off.failure ?? api.failure };
}

export async function fetchLiveMatches(): Promise<LiveMatch[]> {
  return (await fetchLiveStatus()).matches;
}

export function pairKey(t1: string, t2: string): string {
  return [t1, t2].sort().join("|");
}

/** Solo fase de grupos: el knockout real define los cruces, no se simula. */
export function buildFixedResults(matches: LiveMatch[]): FixedResults {
  const fixed: FixedResults = new Map();
  for (const m of matches) {
    if (m.score1 === null || m.score2 === null) continue;
    if (!m.group?.startsWith("Group")) continue;
    const winner = m.score1 > m.score2 ? m.team1 : m.score2 > m.score1 ? m.team2 : null;
    fixed.set(pairKey(m.team1, m.team2), winner);
  }
  return fixed;
}

/** Marcadores reales por par de equipos, para mostrarlos en la UI de grupos. */
export type ScoreMap = Map<string, { s1: number; s2: number; team1: string }>;

export function buildScoreMap(matches: LiveMatch[]): ScoreMap {
  const scores: ScoreMap = new Map();
  for (const m of matches) {
    if (m.score1 === null || m.score2 === null) continue;
    if (!m.group?.startsWith("Group")) continue;
    scores.set(pairKey(m.team1, m.team2), { s1: m.score1, s2: m.score2, team1: m.team1 });
  }
  return scores;
}

/* ── Stats agregadas del torneo en curso (todas las fases) ── */
export interface LiveStats {
  played: number;
  goals: number;
  avg: number;
  last: LiveMatch | null;
}

export function buildLiveStats(matches: LiveMatch[]): LiveStats {
  let played = 0, goals = 0, last: LiveMatch | null = null;
  for (const m of matches) {
    if (m.score1 === null || m.score2 === null) continue;
    played++;
    goals += m.score1 + m.score2;
    if ((m.date ?? "") >= (last?.date ?? "")) last = m;
  }
  return { played, goals, avg: played ? goals / played : 0, last };
}

/* ── Partidos del día ──
   Los de hoy (fecha local del usuario); si hoy no hay jornada,
   el próximo día con partidos pendientes. */
export function fixturesOfTheDay(
  matches: LiveMatch[],
  today: string
): { date: string; fixtures: LiveMatch[] } {
  const dated = matches.filter((m) => m.date);
  const todays = dated.filter((m) => m.date === today);
  if (todays.length > 0) return { date: today, fixtures: todays };
  const nextDate = dated
    .filter((m) => m.date! > today && m.score1 === null)
    .map((m) => m.date!)
    .sort()[0];
  if (!nextDate) return { date: today, fixtures: [] };
  return { date: nextDate, fixtures: dated.filter((m) => m.date === nextDate) };
}

/* ── Modelo vs Realidad: veredicto por cada partido terminado ──
   Usa predictions.json (todas las parejas posibles), así también
   cubre el knockout cuando se definan los cruces. */
export interface MatchVerdict {
  m: LiveMatch;
  predicted: "t1" | "draw" | "t2";
  prob: number;
  probs: { t1: number; draw: number; t2: number };
  hit: boolean;
}

export function buildVerdicts(
  matches: LiveMatch[],
  predictions: Record<string, Prediction>
): MatchVerdict[] {
  const out: MatchVerdict[] = [];
  for (const m of matches) {
    if (m.score1 === null || m.score2 === null) continue;
    let probs: { t1: number; draw: number; t2: number } | null = null;
    const direct = predictions[`${m.team1}|${m.team2}`];
    const reverse = predictions[`${m.team2}|${m.team1}`];
    if (direct) probs = { t1: direct.home_win, draw: direct.draw, t2: direct.away_win };
    else if (reverse) probs = { t1: reverse.away_win, draw: reverse.draw, t2: reverse.home_win };
    if (!probs) continue;
    const actual = m.score1 > m.score2 ? "t1" : m.score1 < m.score2 ? "t2" : "draw";
    const predicted = (Object.entries(probs)
      .sort((a, b) => b[1] - a[1])[0][0]) as MatchVerdict["predicted"];
    out.push({ m, predicted, prob: probs[predicted], probs, hit: predicted === actual });
  }
  return out;
}

/* ── Posiciones reales por grupo, calculadas con los resultados oficiales ── */
export interface StandingRow {
  team: string;
  played: number;
  won: number;
  drawn: number;
  lost: number;
  gf: number;
  ga: number;
  gd: number;
  points: number;
}

export function computeGroupStandings(
  matches: LiveMatch[],
  groups: Record<string, string[]>
): Record<string, StandingRow[]> {
  const rowByTeam = new Map<string, StandingRow>();
  const out: Record<string, StandingRow[]> = {};
  for (const [g, gteams] of Object.entries(groups)) {
    out[g] = gteams.map((team) => {
      const row: StandingRow = {
        team, played: 0, won: 0, drawn: 0, lost: 0, gf: 0, ga: 0, gd: 0, points: 0,
      };
      rowByTeam.set(team, row);
      return row;
    });
  }
  for (const m of matches) {
    if (m.score1 === null || m.score2 === null) continue;
    if (!m.group?.startsWith("Group")) continue;
    const r1 = rowByTeam.get(m.team1);
    const r2 = rowByTeam.get(m.team2);
    if (!r1 || !r2) continue;
    r1.played++; r2.played++;
    r1.gf += m.score1; r1.ga += m.score2;
    r2.gf += m.score2; r2.ga += m.score1;
    if (m.score1 > m.score2)      { r1.won++; r2.lost++; r1.points += 3; }
    else if (m.score1 < m.score2) { r2.won++; r1.lost++; r2.points += 3; }
    else                          { r1.drawn++; r2.drawn++; r1.points++; r2.points++; }
  }
  for (const g of Object.keys(out)) {
    for (const r of out[g]) r.gd = r.gf - r.ga;
    out[g].sort(
      (a, b) => b.points - a.points || b.gd - a.gd || b.gf - a.gf || a.team.localeCompare(b.team)
    );
  }
  return out;
}

/* ── Mejores terceros: ranking cruzado entre los 3°s de cada grupo ──
   Mismo criterio FIFA usado para desempate intra-grupo (pts → GD → GF →
   alfabético como proxy del sorteo, sin datos de fair play). Se recalcula
   en cada refresh de datos en vivo — "oficial" solo cuando los 12 grupos
   completaron sus 3 partidos; antes de eso es una foto provisional, ya
   que no todos los grupos juegan la misma cantidad de partidos el mismo día. */
export interface ThirdPlaceRow extends StandingRow {
  group: string;
}

export function rankBestThirds(
  standingsByGroup: [string, StandingRow[]][]
): { ranked: ThirdPlaceRow[]; allComplete: boolean } {
  const ranked: ThirdPlaceRow[] = standingsByGroup
    .filter(([, rows]) => rows.length >= 3)
    .map(([group, rows]) => ({ ...rows[2], group }))
    .sort(
      (a, b) => b.points - a.points || b.gd - a.gd || b.gf - a.gf || a.team.localeCompare(b.team)
    );
  const allComplete =
    standingsByGroup.length === 12 &&
    standingsByGroup.every(([, rows]) => rows.every((r) => r.played === 3));
  return { ranked, allComplete };
}

/* ── Veredicto del modelo vs resultado real ── */
export type Verdict = { hit: boolean; predicted: "t1" | "draw" | "t2"; prob: number };

/** Compara el resultado más probable según el modelo con el resultado real. */
export function modelVerdict(m: GroupMatch, s: { s1: number; s2: number }): Verdict {
  const actual = s.s1 > s.s2 ? "t1" : s.s1 < s.s2 ? "t2" : "draw";
  const probs = { t1: m.t1_win, draw: m.draw, t2: m.t2_win } as const;
  const predicted = (Object.entries(probs)
    .sort((a, b) => b[1] - a[1])[0][0]) as Verdict["predicted"];
  return { hit: predicted === actual, predicted, prob: probs[predicted] };
}

/** Orienta el marcador live al orden team1/team2 del fixture local. */
export function orientScore(
  m: GroupMatch,
  liveScores?: ScoreMap
): { s1: number; s2: number } | null {
  const live = liveScores?.get(pairKey(m.team1, m.team2));
  if (!live) return null;
  return live.team1 === m.team1 ? { s1: live.s1, s2: live.s2 } : { s1: live.s2, s2: live.s1 };
}

/** Récord global del modelo sobre los partidos de grupos ya jugados. */
export function modelRecord(
  groupMatches: Record<string, GroupMatch[]>,
  liveScores: ScoreMap
): { played: number; hits: number } {
  let played = 0, hits = 0;
  for (const m of Object.values(groupMatches).flat()) {
    const score = orientScore(m, liveScores);
    if (!score) continue;
    played++;
    if (modelVerdict(m, score).hit) hits++;
  }
  return { played, hits };
}
