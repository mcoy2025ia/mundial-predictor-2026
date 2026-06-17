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
  // Strip BOM (U+FEFF) that PowerShell injects when piping values to CLIs
  const raw = process.env.FOOTBALL_DATA_TOKEN ?? "";
  const token = raw.charCodeAt(0) === 0xFEFF ? raw.slice(1).trim() : raw.trim();
  if (!token) {
    return NextResponse.json({ error: "FOOTBALL_DATA_TOKEN not set" }, { status: 503 });
  }

  let rawText = "";
  try {
    const res = await fetch(UPSTREAM, {
      headers: { "X-Auth-Token": token },
      cache: "no-store",
    });

    rawText = await res.text();

    if (!res.ok) {
      return NextResponse.json({ error: `upstream ${res.status}`, body: rawText.slice(0, 200) }, { status: 502 });
    }

    const data = JSON.parse(rawText) as { matches?: FdMatch[] };
    const matches = (data?.matches ?? []).map((m) => {
      const finished = m.status === "FINISHED";
      return {
        team1: m.homeTeam?.name ?? "",
        team2: m.awayTeam?.name ?? "",
        score1: finished ? (m.score?.fullTime?.home ?? null) : null,
        score2: finished ? (m.score?.fullTime?.away ?? null) : null,
        group: formatGroup(m.group),
        round: m.stage ?? null,
        utcDate: m.utcDate ?? null,
        status: m.status ?? null,
      };
    });

    return NextResponse.json(
      { source: "football-data.org", matches },
      { headers: { "Cache-Control": "s-maxage=120, stale-while-revalidate=300" } }
    );
  } catch (err) {
    return NextResponse.json(
      { error: String(err), raw: rawText.slice(0, 500) },
      { status: 500 }
    );
  }
}
