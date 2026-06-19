import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

// Cache en memoria para no releer constantemente
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

    // Cargar desde la carpeta pública (exportado por export_frontend_data.py)
    const response = await fetch(
      new URL('../../public/data/agent_debate_results.json', import.meta.url)
    );

    if (!response.ok) {
      console.warn('Agent debate results file not found');
      return NextResponse.json([], 200); // Retornar array vacío si no existe
    }

    const results = await response.json();

    // Filtrar solo resultados válidos (sin errores)
    const validResults = Array.isArray(results)
      ? results.filter((r: any) => !r.error)
      : [];

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
    return NextResponse.json([], 200); // Retornar array vacío en caso de error
  }
}
