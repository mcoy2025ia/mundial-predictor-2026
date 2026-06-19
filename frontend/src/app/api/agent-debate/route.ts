import { NextResponse } from 'next/server';
import { readFile } from 'fs/promises';
import path from 'path';

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
    // process.cwd() en runtime serverless apunta a la raíz del proyecto Next.js
    const filePath = path.join(process.cwd(), 'public', 'data', 'agent_debate_results.json');

    let results: any;
    try {
      const fileContent = await readFile(filePath, 'utf-8');
      results = JSON.parse(fileContent);
    } catch (readErr) {
      console.warn('Agent debate results file not found:', readErr);
      return NextResponse.json([] as any[]); // Retornar array vacío si no existe
    }

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
    return NextResponse.json([] as any[]); // Retornar array vacío en caso de error
  }
}
