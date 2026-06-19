import { readFileSync } from 'fs';
import { join } from 'path';
import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

// Cache en memoria para no releer archivo constantemente
let cachedResults: any = null;
let cacheTime = 0;
const CACHE_TTL = 60000; // 1 minuto

export async function GET(request: Request) {
  try {
    // Validar cache
    const now = Date.now();
    if (cachedResults && now - cacheTime < CACHE_TTL) {
      return NextResponse.json(cachedResults);
    }

    // Leer resultados del Agent Debate
    const resultsPath = join(
      process.cwd(),
      '..',
      'data',
      'processed',
      'agent_debate_results.json'
    );

    const fileContent = readFileSync(resultsPath, 'utf-8');
    const results = JSON.parse(fileContent);

    // Filtrar solo resultados válidos (sin errores)
    const validResults = results.filter((r: any) => !r.error);

    // Transformar formato para el frontend
    const formattedResults = validResults.map((result: any) => {
      const match = result.match || '';
      const [home, away] = match.split(' vs ').map((t: string) => t.trim());

      return {
        match,
        home,
        away,
        context: result.context,
        consensus: result.consensus,
        round1: result.round_1,
        round2: result.round_2,
      };
    });

    // Actualizar cache
    cachedResults = formattedResults;
    cacheTime = now;

    return NextResponse.json(formattedResults);
  } catch (error) {
    console.error('Error reading agent debate results:', error);
    return NextResponse.json(
      { error: 'Failed to load agent debate predictions' },
      { status: 500 }
    );
  }
}
