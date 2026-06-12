import { NextResponse } from "next/server";

/**
 * Proxy a football-data.org (Mundial 2026) con caché de 2 minutos.
 * El token vive en el servidor (FOOTBALL_DATA_TOKEN) — nunca llega al navegador.
 * Sin token o con error upstream responde 5xx y el cliente cae al
 * fallback de openfootball (ver src/lib/live.ts).
 */

const UPSTREAM = "https://api.football-data.org/v4/competitions/WC/matches";

interface FdTeam {
  name: string | null;
}

interface FdMatch {
  status: string; // SCHEDULED | TIMED | IN_PLAY | PAUSED | FINISHED | ...
  stage: string | null; // GROUP_STAGE | LAST_32 | LAST_16 | ...
  group: string | null; // "GROUP_A"
  utcDate: string | null;
  homeTeam: FdTeam | null;
  awayTeam: FdTeam | null;
  score: { fullTime: { home: number | null; away: number | null } } | null;
}

/** "GROUP_A" → "Group A" (formato que ya usa el resto de la app) */
function formatGroup(group: string | null): string | undefined {
  if (!group) return undefined;
  return group.startsWith("GROUP_") ? `Group ${group.slice(6)}` : group;
}

export async function GET() {
  const token = process.env.FOOTBALL_DATA_TOKEN;
  if (!token) {
    return NextResponse.json({ error: "FOOTBALL_DATA_TOKEN not set" }, { status: 503 });
  }

  const res = await fetch(UPSTREAM, {
    headers: { "X-Auth-Token": token },
    next: { revalidate: 120 }, // 1 llamada upstream cada 2 min, sin importar el tráfico
  });
  if (!res.ok) {
    return NextResponse.json({ error: `upstream ${res.status}` }, { status: 502 });
  }

  const data = await res.json();
  const matches = ((data?.matches ?? []) as FdMatch[]).map((m) => {
    // Solo se fijan marcadores de partidos TERMINADOS: la app trata
    // un score no-nulo como resultado final (veredictos, simulador).
    const finished = m.status === "FINISHED";
    return {
      team1: m.homeTeam?.name ?? "",
      team2: m.awayTeam?.name ?? "",
      score1: finished ? (m.score?.fullTime?.home ?? null) : null,
      score2: finished ? (m.score?.fullTime?.away ?? null) : null,
      group: formatGroup(m.group),
      round: m.stage ?? undefined,
      utcDate: m.utcDate ?? null,
      status: m.status,
    };
  });

  return NextResponse.json(
    { source: "football-data.org", matches },
    { headers: { "Cache-Control": "s-maxage=120, stale-while-revalidate=300" } }
  );
}
