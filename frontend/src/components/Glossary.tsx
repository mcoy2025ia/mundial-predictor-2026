"use client";

import { useLang } from "@/lib/i18n";

interface Term {
  term: string;
  icon: string;
  definition: string;
  detail?: string;
}

const TERMS: Term[] = [
  {
    term: "Rating ELO",
    icon: "📈",
    definition:
      "Sistema de puntuación que mide la fuerza relativa de los equipos basándose únicamente en resultados. Inventado por Arpad Elo para el ajedrez, adaptado al fútbol.",
    detail:
      "Rating inicial: 1 500 puntos. K-factor: 32 (estándar FIFA). Calculado cronológicamente sobre 49 000+ partidos internacionales desde 1872. Fórmula: E = 1 / (1 + 10^((rival − propio) / 400)). Nuevo rating = viejo + 32 × (resultado − esperado).",
  },
  {
    term: "XGBoost calibrado",
    icon: "🤖",
    definition:
      "El modelo de predicción. XGBoost es un algoritmo de árboles de decisión con gradient boosting. 'Calibrado' significa que las probabilidades producidas reflejan frecuencias reales.",
    detail:
      "Entrenado con 964 partidos de fase final del Mundial (1930–2022). Split temporal: entrenado hasta 2018, evaluado en Qatar 2022. Calibración con CalibratedClassifierCV (método isotónico). Accuracy en Qatar 2022: 50% (línea base: ~40%).",
  },
  {
    term: "Monte Carlo",
    icon: "🎲",
    definition:
      "Técnica de simulación que repite el torneo completo miles de veces con resultados aleatorios ponderados por las probabilidades del modelo para estimar la probabilidad de cada resultado posible.",
    detail:
      "Cada simulación: simula los 72 partidos de grupos, clasifica top-2 + 8 mejores terceros, luego simula R32 → R16 → QF → SF → Final. Con 5 000 simulaciones, el error estándar es < 0.7% por equipo.",
  },
  {
    term: "Log-loss",
    icon: "📉",
    definition:
      "Métrica principal de evaluación del modelo. Mide qué tan seguros y correctos son los pronósticos. Menor es mejor. Un modelo perfecto tiene log-loss = 0.",
    detail:
      "XGBoost en Qatar 2022: log-loss = 1.077. Regresión logística baseline: 1.098. Ambos son razonables para un torneo tan impredecible (log-loss de adivinar siempre 1/3 sería 1.099).",
  },
  {
    term: "Brier Score",
    icon: "🎯",
    definition:
      "Error cuadrático medio de las probabilidades. Mide qué tan cerca están las probabilidades predichas de los resultados reales (0 = perfecto, 1 = terrible).",
    detail:
      "Nuestro modelo: Brier = 0.214. Equivale a un error promedio de ±21 puntos porcentuales por predicción.",
  },
  {
    term: "H2H (Head-to-Head)",
    icon: "⚔️",
    definition:
      "Historial de enfrentamientos directos entre dos selecciones en fase final del Mundial. Si no se han enfrentado antes, se usa 50% como valor neutro.",
    detail:
      "Feature del modelo: h2h_home_win_pct = victorias del equipo 1 / total partidos H2H. Tiene la correlación más baja de todas las features (0.08) porque la mayoría de dúos nunca se ha enfrentado en un Mundial.",
  },
  {
    term: "elo_diff",
    icon: "⚡",
    definition:
      "Diferencia de ELO entre los dos equipos (equipo 1 − equipo 2). Es la feature más predictiva del modelo, con una correlación de 0.40 con el resultado.",
    detail:
      "Una diferencia de +100 ELO implica aproximadamente un 64% de probabilidad de ganar. España (2064) vs Francia (2018) → elo_diff = +46, lo que da a España una ventaja moderada.",
  },
  {
    term: "wc_experience_diff",
    icon: "🏆",
    definition:
      "Diferencia en número de partidos de Mundial jugados previamente (hasta ese momento). Es la segunda feature más predictiva, con correlación 0.32.",
    detail:
      "Captura el efecto de 'veteranía en Mundiales'. Equipos con más experiencia histórica tienden a rendir mejor. Supera a features más intuitivas como el historial de goles.",
  },
  {
    term: "Formato Mundial 2026",
    icon: "📋",
    definition:
      "48 equipos en 12 grupos de 4. Los 2 primeros de cada grupo + los 8 mejores terceros clasifican a la Ronda de 32 (R32). Luego knockout puro hasta la final.",
    detail:
      "Total: 72 partidos de grupos + 32 de R32 + 16 de octavos (R16) + 8 de cuartos (QF) + 4 de semis (SF) + 2 de tercer lugar + 1 final = 104 partidos totales en 3 países.",
  },
  {
    term: "Split temporal",
    icon: "📅",
    definition:
      "Técnica anti-leakage para series temporales: el modelo se entrena solo con datos del pasado (hasta 2018) y se evalúa en el futuro (Qatar 2022). Nunca usamos datos del futuro para entrenar.",
    detail:
      "En datos ordenados por tiempo, un k-fold aleatorio contaminaría el modelo (usaría información del futuro para predecir el pasado). El split temporal garantiza que las métricas son realistas.",
  },
  {
    term: "Calibración de probabilidades",
    icon: "🔧",
    definition:
      "XGBoost tiende a dar probabilidades extremas aunque el resultado sea incierto. La calibración isotónica corrige esto para que un 60% predicho corresponda a ~60% de victorias reales.",
    detail:
      "Usamos CalibratedClassifierCV con método isotónico y validación cruzada de 5 folds. La diferencia entre probabilidad media predicha y tasa real observada es < 2% para las 3 clases.",
  },
];

export default function Glossary() {
  const T = useLang();
  return (
    <div className="space-y-4 max-w-3xl mx-auto">
      <div className="text-center mb-8">
        <h2 className="text-2xl font-black mb-2">{T.glossaryTitle}</h2>
        <p className="text-[var(--text-muted)] text-sm">{T.glossarySubtitle}</p>
      </div>

      {TERMS.map(({ term, icon, definition, detail }) => (
        <details key={term} className="stat-card group cursor-pointer text-left">
          <summary className="flex items-center gap-3 list-none cursor-pointer select-none">
            <span className="text-2xl">{icon}</span>
            <span className="font-bold text-base flex-1">{term}</span>
            <span className="text-[var(--text-muted)] text-sm transition-transform group-open:rotate-180">▼</span>
          </summary>
          <div className="mt-3 pt-3 border-t border-[var(--border-subtle)] space-y-2">
            <p className="text-sm text-[var(--text)]">{definition}</p>
            {detail && (
              <p className="text-xs text-[var(--text-muted)] leading-relaxed">{detail}</p>
            )}
          </div>
        </details>
      ))}

      <div className="stat-card text-center text-xs text-[var(--text-muted)] mt-6">
        <p>{T.glossaryFooter}</p>
      </div>
    </div>
  );
}
