"use client";

import { useContext } from "react";
import { LangContext } from "@/lib/i18n";

// Walk-forward results — updated after each full pipeline run
const WF_ROWS = [
  { year: 2006, elo: 0.1609, poisson: 0.1787, xgb: 0.1614, ensemble: 0.1626, best: "elo" },
  { year: 2010, elo: 0.2022, poisson: 0.2072, xgb: 0.2052, ensemble: 0.1995, best: "ensemble" },
  { year: 2014, elo: 0.1925, poisson: 0.2185, xgb: 0.1973, ensemble: 0.1984, best: "elo" },
  { year: 2018, elo: 0.2050, poisson: 0.2099, xgb: 0.2141, ensemble: 0.2043, best: "ensemble" },
  { year: 2022, elo: 0.2222, poisson: 0.2181, xgb: 0.2152, ensemble: 0.2142, best: "ensemble" },
];
const WF_OVERALL = { elo: 0.1966, poisson: 0.2065, xgb: 0.1986, ensemble: 0.1958 };

const FEATURES = [
  { key: "elo_diff",                  es: "Diferencia ELO (local − visitante)",      en: "ELO difference (home − away)",         pt: "Diferença ELO (casa − visitante)" },
  { key: "elo_home / elo_away",       es: "ELO absoluto de cada equipo",             en: "Absolute ELO of each team",             pt: "ELO absoluto de cada equipe" },
  { key: "home_goals_scored_avg5",    es: "Goles marcados (promedio últimos 5)",     en: "Goals scored (rolling avg 5 matches)",  pt: "Gols marcados (média últimos 5)" },
  { key: "home_goals_conceded_avg5",  es: "Goles recibidos (promedio últimos 5)",    en: "Goals conceded (rolling avg 5 matches)", pt: "Gols sofridos (média últimos 5)" },
  { key: "h2h_home_win_pct",          es: "% victorias del local en enfrentamientos", en: "Head-to-head home win rate",           pt: "% vitórias em confrontos diretos" },
  { key: "is_neutral",                es: "Sede neutral / ventaja de anfitrión",     en: "Neutral venue / host advantage",        pt: "Sede neutra / vantagem do anfitrião" },
  { key: "wc_experience_diff",        es: "Diferencia de apariciones en Mundiales", en: "Difference in WC appearances",          pt: "Diferença de participações em Copas" },
];

const LIMITATIONS = {
  es: [
    "El modelo refleja patrones históricos. Equipos debutantes o con pocos datos tienen priors menos informados.",
    "No incorpora datos de lesiones en tiempo real. Los agentes LLM son opcionales y requieren contexto manual.",
    "La calibración se entrenó en WC 2018. Deriva posible ante cambios estructurales del fútbol moderno.",
    "Los empates son el outcome más difícil: ningún modelo reduce sustancialmente su error en esta clase.",
    "No es una herramienta de apuestas. Las probabilidades están calibradas para forecasting, no para valor esperado vs. casas.",
  ],
  en: [
    "The model reflects historical patterns. Debutant teams or those with few records have less informative priors.",
    "No real-time injury data. LLM agents are optional and require manual context injection.",
    "Calibration was fitted on WC 2018. Drift is possible as modern football evolves structurally.",
    "Draws are the hardest outcome: no model tested significantly reduces draw prediction error.",
    "Not a betting tool. Probabilities are calibrated for forecasting, not for expected value against bookmakers.",
  ],
  pt: [
    "O modelo reflete padrões históricos. Equipes estreantes ou com poucos dados têm priors menos informativos.",
    "Sem dados de lesões em tempo real. Agentes LLM são opcionais e requerem contexto manual.",
    "A calibração foi treinada no WC 2018. Deriva possível com mudanças estruturais no futebol moderno.",
    "Empates são o resultado mais difícil: nenhum modelo reduz significativamente o erro nessa classe.",
    "Não é uma ferramenta de apostas. Probabilidades calibradas para previsão, não para valor esperado.",
  ],
};

const T = {
  es: {
    title:       "Metodología del Modelo",
    subtitle:    "Walk-forward validation en 5 Mundiales · 320 partidos sin leakage",
    wfTitle:     "Validación Walk-Forward (RPS — menor es mejor)",
    wfNote:      "Cada fold entrena con datos anteriores al torneo de prueba. El Ensemble (ELO 35% + Poisson 35% + XGB 30%) gana en 3 de 5 torneos y tiene el mejor RPS global.",
    wfYear:      "Mundial",
    wfBest:      "Mejor",
    ensTitle:    "Arquitectura del Ensemble",
    ensNote:     "Tres señales independientes calibradas y promediadas. Pesos optimizados por grid search en walk-forward.",
    eloDesc:     "ELO mejorado: K por torneo, multiplicador por margen, home advantage +100",
    poissonDesc: "Dixon-Robinson: ataque/defensa por iteración, matrices de scoreline 8×8",
    xgbDesc:     "XGBoost softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)",
    featTitle:   "Features del Modelo (10)",
    featNote:    "Todas las features se computan estrictamente antes del partido (sin leakage). El rolling usa shift(1) sobre el timeline completo de internacionales.",
    limTitle:    "Limitaciones",
    limNote:     "El modelo es honesto sobre sus límites. Lea esto antes de interpretar las probabilidades.",
    testTitle:   "Qatar 2022 — Test Set",
    testNote:    "64 partidos nunca vistos durante el entrenamiento.",
  },
  en: {
    title:       "Model Methodology",
    subtitle:    "Walk-forward validation on 5 World Cups · 320 matches, no leakage",
    wfTitle:     "Walk-Forward Validation (RPS — lower is better)",
    wfNote:      "Each fold trains on data before the test tournament. The Ensemble (ELO 35% + Poisson 35% + XGB 30%) wins in 3 of 5 tournaments and achieves the best overall RPS.",
    wfYear:      "World Cup",
    wfBest:      "Best",
    ensTitle:    "Ensemble Architecture",
    ensNote:     "Three independent signals blended and calibrated. Weights optimised by grid search on walk-forward data.",
    eloDesc:     "Improved ELO: K by tournament, goal-margin multiplier, +100 home advantage",
    poissonDesc: "Dixon-Robinson: attack/defense via iteration, 8×8 scoreline matrices",
    xgbDesc:     "XGBoost softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)",
    featTitle:   "Model Features (10)",
    featNote:    "All features are computed strictly before the match (no leakage). Rolling stats use shift(1) over the full international timeline.",
    limTitle:    "Limitations",
    limNote:     "The model is honest about its limits. Read this before interpreting probabilities.",
    testTitle:   "Qatar 2022 — Test Set",
    testNote:    "64 matches never seen during training.",
  },
  pt: {
    title:       "Metodologia do Modelo",
    subtitle:    "Validação walk-forward em 5 Copas · 320 jogos sem vazamento de dados",
    wfTitle:     "Validação Walk-Forward (RPS — menor é melhor)",
    wfNote:      "Cada fold treina com dados anteriores ao torneio de teste. O Ensemble (ELO 35% + Poisson 35% + XGB 30%) vence em 3 de 5 torneios e tem o melhor RPS global.",
    wfYear:      "Copa",
    wfBest:      "Melhor",
    ensTitle:    "Arquitetura do Ensemble",
    ensNote:     "Três sinais independentes calibrados e ponderados. Pesos otimizados por grid search no walk-forward.",
    eloDesc:     "ELO aprimorado: K por torneio, multiplicador de margem, vantagem em casa +100",
    poissonDesc: "Dixon-Robinson: ataque/defesa por iteração, matrizes de scoreline 8×8",
    xgbDesc:     "XGBoost softmax + CalibratedClassifierCV (TimeSeriesSplit n=3, sigmoid)",
    featTitle:   "Features do Modelo (10)",
    featNote:    "Todas as features são calculadas estritamente antes do jogo (sem leakage). Rolling usa shift(1) sobre o histórico completo.",
    limTitle:    "Limitações",
    limNote:     "O modelo é honesto sobre seus limites. Leia isso antes de interpretar as probabilidades.",
    testTitle:   "Qatar 2022 — Conjunto de Teste",
    testNote:    "64 jogos nunca vistos durante o treinamento.",
  },
};

function RpsCell({ value, isBest }: { value: number; isBest: boolean }) {
  return (
    <td className={`py-2 px-3 text-right font-mono text-xs tabular-nums ${
      isBest
        ? "text-[var(--color-wc-gold)] font-bold"
        : "text-[var(--color-ink-muted)]"
    }`}>
      {value.toFixed(4)}
      {isBest && <span className="ml-1 text-[0.6rem]">▲</span>}
    </td>
  );
}

export default function ModelTab() {
  const lang = useContext(LangContext);
  const S = T[lang] ?? T.es;
  const lims = LIMITATIONS[lang] ?? LIMITATIONS.es;

  const card = "rounded-xl p-5 space-y-3" as const;
  const cardBg = { background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.06)" };

  return (
    <div className="space-y-6 max-w-3xl mx-auto">

      {/* Header */}
      <div>
        <h2 style={{ fontFamily: "var(--font-display)", fontSize: "clamp(1.1rem, 3vw, 1.5rem)", letterSpacing: "0.08em", color: "var(--color-ink)" }}>
          {S.title}
        </h2>
        <p className="text-xs mt-1" style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", letterSpacing: "0.05em" }}>
          {S.subtitle}
        </p>
      </div>

      {/* Walk-forward table */}
      <div className={card} style={cardBg}>
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-wc-red)" }}>
          {S.wfTitle}
        </h3>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b" style={{ borderColor: "rgba(255,255,255,0.08)" }}>
                <th className="py-2 px-3 text-left font-mono text-[var(--color-ink-muted)]">{S.wfYear}</th>
                <th className="py-2 px-3 text-right font-mono text-[var(--color-ink-muted)]">ELO</th>
                <th className="py-2 px-3 text-right font-mono text-[var(--color-ink-muted)]">Poisson</th>
                <th className="py-2 px-3 text-right font-mono text-[var(--color-ink-muted)]">XGB</th>
                <th className="py-2 px-3 text-right font-mono" style={{ color: "var(--color-wc-gold)" }}>Ensemble</th>
              </tr>
            </thead>
            <tbody>
              {WF_ROWS.map((r) => (
                <tr key={r.year} className="border-b" style={{ borderColor: "rgba(255,255,255,0.04)" }}>
                  <td className="py-2 px-3 font-mono text-xs" style={{ color: "var(--color-ink)" }}>{r.year}</td>
                  <RpsCell value={r.elo} isBest={r.best === "elo"} />
                  <RpsCell value={r.poisson} isBest={r.best === "poisson"} />
                  <RpsCell value={r.xgb} isBest={r.best === "xgb"} />
                  <RpsCell value={r.ensemble} isBest={r.best === "ensemble"} />
                </tr>
              ))}
              {/* Overall row */}
              <tr style={{ background: "rgba(212,168,67,0.06)" }}>
                <td className="py-2 px-3 font-mono text-xs font-bold" style={{ color: "var(--color-ink)" }}>
                  {S.wfBest}
                </td>
                <RpsCell value={WF_OVERALL.elo} isBest={false} />
                <RpsCell value={WF_OVERALL.poisson} isBest={false} />
                <RpsCell value={WF_OVERALL.xgb} isBest={false} />
                <RpsCell value={WF_OVERALL.ensemble} isBest={true} />
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-[0.65rem] leading-relaxed" style={{ color: "var(--color-ink-muted)" }}>
          {S.wfNote}
        </p>
      </div>

      {/* Ensemble architecture */}
      <div className={card} style={cardBg}>
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-wc-red)" }}>
          {S.ensTitle}
        </h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {[
            { label: "ELO", weight: "35%", color: "var(--color-wc-gold)", desc: S.eloDesc },
            { label: "Poisson", weight: "35%", color: "#60a5fa", desc: S.poissonDesc },
            { label: "XGBoost", weight: "30%", color: "#34d399", desc: S.xgbDesc },
          ].map(({ label, weight, color, desc }) => (
            <div key={label} className="rounded-lg p-3 space-y-1"
              style={{ background: "rgba(255,255,255,0.03)", border: `1px solid ${color}33` }}>
              <div className="flex items-baseline gap-2">
                <span className="font-mono text-sm font-bold" style={{ color }}>{label}</span>
                <span className="font-mono text-xs" style={{ color: "var(--color-ink-muted)" }}>{weight}</span>
              </div>
              <p className="text-[0.62rem] leading-snug" style={{ color: "var(--color-ink-muted)" }}>{desc}</p>
            </div>
          ))}
        </div>
        <p className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>{S.ensNote}</p>
      </div>

      {/* Qatar 2022 test set */}
      <div className={card} style={cardBg}>
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-wc-red)" }}>
          {S.testTitle}
        </h3>
        <p className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>{S.testNote}</p>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-1">
          {[
            { metric: "Accuracy", value: "48.4%" },
            { metric: "Log-loss", value: "1.025" },
            { metric: "Brier",    value: "0.203" },
            { metric: "RPS",      value: "0.217" },
          ].map(({ metric, value }) => (
            <div key={metric} className="rounded-lg p-3 text-center"
              style={{ background: "rgba(255,255,255,0.03)" }}>
              <div className="font-mono text-base font-bold" style={{ color: "var(--color-ink)" }}>{value}</div>
              <div className="font-mono text-[0.6rem] mt-0.5" style={{ color: "var(--color-ink-muted)" }}>{metric}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Features */}
      <div className={card} style={cardBg}>
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-wc-red)" }}>
          {S.featTitle}
        </h3>
        <p className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>{S.featNote}</p>
        <ul className="space-y-1.5 mt-1">
          {FEATURES.map((f) => (
            <li key={f.key} className="flex gap-3 items-start">
              <code className="text-[0.6rem] font-mono shrink-0 mt-0.5 px-1.5 py-0.5 rounded"
                style={{ background: "rgba(212,168,67,0.12)", color: "var(--color-wc-gold)" }}>
                {f.key}
              </code>
              <span className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>
                {(f as Record<string, string>)[lang] ?? f.es}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {/* Limitations */}
      <div className={card} style={{ ...cardBg, borderColor: "rgba(207,10,44,0.18)" }}>
        <h3 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--color-wc-red)" }}>
          {S.limTitle}
        </h3>
        <p className="text-[0.65rem]" style={{ color: "var(--color-ink-muted)" }}>{S.limNote}</p>
        <ul className="space-y-2 mt-1">
          {lims.map((lim, i) => (
            <li key={i} className="flex gap-2 items-start">
              <span className="shrink-0 mt-0.5 text-[0.7rem]" style={{ color: "var(--color-wc-red)" }}>›</span>
              <span className="text-[0.65rem] leading-snug" style={{ color: "var(--color-ink-muted)" }}>{lim}</span>
            </li>
          ))}
        </ul>
      </div>

    </div>
  );
}
