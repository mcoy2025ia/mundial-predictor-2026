"use client";

import { useState, useMemo, useRef, useEffect, useContext } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  RadialBarChart, RadialBar, PolarAngleAxis,
  ResponsiveContainer, Tooltip,
} from "recharts";
import type { TeamInfo, Prediction, HistoricalMatch, LiveMatch } from "@/types";
import VsOrb from "@/components/ui/VsOrb";
import ProbBar from "@/components/ui/ProbBar";
import { staggerContainer, fadeUp, popIn } from "@/lib/animations";
import { fixturesOfTheDay } from "@/lib/live";
import { useLang, LangContext, type Lang } from "@/lib/i18n";
import AgentDebatePanel from "@/components/AgentDebatePanel";

/* ── WC 2026 Stadiums ── */
type Stadium = { name: string; city: string; capacity: number; country: string; flag: string };

const WC_STADIUMS: Record<string, Stadium> = {
  "Mexico City":                           { name: "Estadio Azteca",            city: "Ciudad de México", capacity: 87523, country: "México",  flag: "🇲🇽" },
  "Guadalajara (Zapopan)":                 { name: "Estadio Akron",             city: "Guadalajara",      capacity: 49850, country: "México",  flag: "🇲🇽" },
  "Monterrey (Guadalupe)":                 { name: "Estadio BBVA",              city: "Monterrey",        capacity: 53500, country: "México",  flag: "🇲🇽" },
  "New York/New Jersey (East Rutherford)": { name: "MetLife Stadium",           city: "New York / NJ",    capacity: 82500, country: "EE.UU.", flag: "🇺🇸" },
  "Dallas (Arlington)":                    { name: "AT&T Stadium",              city: "Dallas",           capacity: 80000, country: "EE.UU.", flag: "🇺🇸" },
  "Los Angeles (Inglewood)":               { name: "SoFi Stadium",              city: "Los Ángeles",      capacity: 70240, country: "EE.UU.", flag: "🇺🇸" },
  "San Francisco Bay Area (Santa Clara)":  { name: "Levi's Stadium",            city: "San Francisco",    capacity: 68500, country: "EE.UU.", flag: "🇺🇸" },
  "Kansas City":                           { name: "Arrowhead Stadium",         city: "Kansas City",      capacity: 76416, country: "EE.UU.", flag: "🇺🇸" },
  "Seattle":                               { name: "Lumen Field",               city: "Seattle",          capacity: 69000, country: "EE.UU.", flag: "🇺🇸" },
  "Philadelphia":                          { name: "Lincoln Financial Field",   city: "Filadelfia",       capacity: 69596, country: "EE.UU.", flag: "🇺🇸" },
  "Miami (Miami Gardens)":                 { name: "Hard Rock Stadium",         city: "Miami",            capacity: 65326, country: "EE.UU.", flag: "🇺🇸" },
  "Boston (Foxborough)":                   { name: "Gillette Stadium",          city: "Boston",           capacity: 65878, country: "EE.UU.", flag: "🇺🇸" },
  "Atlanta":                               { name: "Mercedes-Benz Stadium",     city: "Atlanta",          capacity: 71000, country: "EE.UU.", flag: "🇺🇸" },
  "Houston":                               { name: "NRG Stadium",               city: "Houston",          capacity: 72220, country: "EE.UU.", flag: "🇺🇸" },
  "Vancouver":                             { name: "BC Place",                  city: "Vancouver",        capacity: 54500, country: "Canadá", flag: "🇨🇦" },
  "Toronto":                               { name: "BMO Field",                 city: "Toronto",          capacity: 45736, country: "Canadá", flag: "🇨🇦" },
};

/* Sorted pair key → ground (from wc2026_fixture.json, names normalized to app dataset) */
const TEAM_PAIR_GROUND: Record<string, string> = {
  "Mexico|South Africa":                        "Mexico City",
  "Czech Republic|South Korea":                 "Guadalajara (Zapopan)",
  "Czech Republic|South Africa":               "Atlanta",
  "Mexico|South Korea":                         "Guadalajara (Zapopan)",
  "Czech Republic|Mexico":                      "Mexico City",
  "South Africa|South Korea":                  "Monterrey (Guadalupe)",
  "Bosnia and Herzegovina|Canada":             "Toronto",
  "Qatar|Switzerland":                          "San Francisco Bay Area (Santa Clara)",
  "Bosnia and Herzegovina|Switzerland":        "Los Angeles (Inglewood)",
  "Canada|Qatar":                               "Vancouver",
  "Canada|Switzerland":                         "Vancouver",
  "Bosnia and Herzegovina|Qatar":              "Seattle",
  "Brazil|Morocco":                             "New York/New Jersey (East Rutherford)",
  "Haiti|Scotland":                             "Boston (Foxborough)",
  "Morocco|Scotland":                           "Boston (Foxborough)",
  "Brazil|Haiti":                               "Philadelphia",
  "Brazil|Scotland":                            "Miami (Miami Gardens)",
  "Haiti|Morocco":                              "Atlanta",
  "Paraguay|United States":                    "Los Angeles (Inglewood)",
  "Australia|Turkey":                           "Vancouver",
  "Australia|United States":                   "Seattle",
  "Paraguay|Turkey":                            "San Francisco Bay Area (Santa Clara)",
  "Turkey|United States":                      "Los Angeles (Inglewood)",
  "Australia|Paraguay":                         "San Francisco Bay Area (Santa Clara)",
  "Curacao|Germany":                            "Houston",
  "Ecuador|Ivory Coast":                        "Philadelphia",
  "Germany|Ivory Coast":                        "Toronto",
  "Curacao|Ecuador":                            "Kansas City",
  "Curacao|Ivory Coast":                        "Philadelphia",
  "Ecuador|Germany":                            "New York/New Jersey (East Rutherford)",
  "Japan|Netherlands":                          "Dallas (Arlington)",
  "Sweden|Tunisia":                             "Monterrey (Guadalupe)",
  "Netherlands|Sweden":                         "Houston",
  "Japan|Tunisia":                              "Monterrey (Guadalupe)",
  "Japan|Sweden":                               "Dallas (Arlington)",
  "Netherlands|Tunisia":                        "Kansas City",
  "Belgium|Egypt":                              "Seattle",
  "Iran|New Zealand":                           "Los Angeles (Inglewood)",
  "Belgium|Iran":                               "Los Angeles (Inglewood)",
  "Egypt|New Zealand":                          "Vancouver",
  "Egypt|Iran":                                 "Seattle",
  "Belgium|New Zealand":                        "Vancouver",
  "Cape Verde|Spain":                           "Atlanta",
  "Saudi Arabia|Uruguay":                       "Miami (Miami Gardens)",
  "Saudi Arabia|Spain":                         "Atlanta",
  "Cape Verde|Uruguay":                         "Miami (Miami Gardens)",
  "Cape Verde|Saudi Arabia":                    "Houston",
  "Spain|Uruguay":                              "Guadalajara (Zapopan)",
  "France|Senegal":                             "New York/New Jersey (East Rutherford)",
  "Iraq|Norway":                                "Boston (Foxborough)",
  "France|Iraq":                                "Philadelphia",
  "Norway|Senegal":                             "New York/New Jersey (East Rutherford)",
  "France|Norway":                              "Boston (Foxborough)",
  "Iraq|Senegal":                               "Toronto",
  "Algeria|Argentina":                          "Kansas City",
  "Austria|Jordan":                             "San Francisco Bay Area (Santa Clara)",
  "Argentina|Austria":                          "Dallas (Arlington)",
  "Algeria|Jordan":                             "San Francisco Bay Area (Santa Clara)",
  "Algeria|Austria":                            "Kansas City",
  "Argentina|Jordan":                           "Dallas (Arlington)",
  "Colombia|Portugal":                          "Miami (Miami Gardens)",
  "DR Congo|Uzbekistan":                        "Atlanta",
  "Croatia|England":                            "Dallas (Arlington)",
  "Ghana|Panama":                               "Toronto",
  "England|Ghana":                              "Boston (Foxborough)",
  "Croatia|Panama":                             "Toronto",
  "England|Panama":                             "New York/New Jersey (East Rutherford)",
  "Croatia|Ghana":                              "Philadelphia",
  "Cameroon|Nigeria":                           "Dallas (Arlington)",
  "Honduras|Venezuela":                         "Houston",
  "Cameroon|Honduras":                          "Houston",
  "Nigeria|Venezuela":                          "Kansas City",
  "Cameroon|Venezuela":                         "Kansas City",
  "Honduras|Nigeria":                           "Dallas (Arlington)",
};

function getStadium(home: string, away: string): Stadium | null {
  const key = [home, away].sort().join("|");
  const ground = TEAM_PAIR_GROUND[key];
  return ground ? (WC_STADIUMS[ground] ?? null) : null;
}

/* ── Flag-accurate dual colors: [primary, secondary] ── */
const TEAM_FLAG: Record<string, [string, string]> = {
  // South America
  Argentina:              ["#54A0D1", "#FFFFFF"],  // albiceleste sky + white
  Brazil:                 ["#009C3B", "#FEDF00"],  // verde + amarelo
  Colombia:               ["#FCD116", "#003893"],  // amarillo + azul
  Uruguay:                ["#1A7FBF", "#FFFFFF"],  // celeste + white
  Ecuador:                ["#FFD100", "#009A44"],  // amarillo + verde
  Venezuela:              ["#CF142B", "#003893"],  // rojo + azul
  Chile:                  ["#D52B1E", "#FFFFFF"],  // rojo + blanco
  Peru:                   ["#D91023", "#FFFFFF"],  // rojo + blanco
  Paraguay:               ["#D52B1E", "#002B7F"],  // rojo + azul
  Bolivia:                ["#F4E400", "#009A44"],  // amarillo + verde
  // Europe
  France:                 ["#002395", "#ED2939"],  // bleu + rouge
  Spain:                  ["#C60B1E", "#FFC400"],  // rojo + oro
  England:                ["#CF0A2C", "#FFFFFF"],  // St George red + white
  Portugal:               ["#AF0C00", "#006600"],  // vermelho + verde
  Germany:                ["#222222", "#FFCE00"],  // schwarz + gold
  Netherlands:            ["#E77C00", "#FFFFFF"],  // oranje + wit
  Belgium:                ["#000000", "#FDDA24"],  // zwart + geel
  Croatia:                ["#CC0000", "#003399"],  // crvena + plava
  Italy:                  ["#003399", "#009246"],  // azzurro + verde
  Switzerland:            ["#D0021B", "#FFFFFF"],  // rot + weiss
  Sweden:                 ["#006AA7", "#FECC02"],  // blå + gul
  Norway:                 ["#EF2B2D", "#003087"],  // rød + blå
  Austria:                ["#ED2939", "#FFFFFF"],  // rot + weiss
  Denmark:                ["#C60C30", "#FFFFFF"],  // rød + hvid
  Poland:                 ["#DC143C", "#FFFFFF"],  // czerwony + biały
  Serbia:                 ["#C6363C", "#003B8E"],  // crvena + plava
  Scotland:               ["#003F87", "#FFFFFF"],  // bleu + blanc
  "Czech Republic":       ["#D7141A", "#003893"],  // červená + modrá
  Turkey:                 ["#E30A17", "#FFFFFF"],  // kırmızı + beyaz
  "Bosnia and Herzegovina": ["#003893", "#FFCB00"],
  // CONCACAF
  "United States":        ["#002868", "#BF0A30"],  // navy + red
  Mexico:                 ["#006847", "#CE1126"],  // verde + rojo
  Canada:                 ["#FF0000", "#FFFFFF"],  // red + white
  Panama:                 ["#D21034", "#002B7F"],  // rojo + azul
  "Costa Rica":           ["#002B7F", "#CE1126"],  // azul + rojo
  Honduras:               ["#0073CF", "#FFFFFF"],  // azul + blanco
  Jamaica:                ["#000000", "#FED100"],  // negro + dorado
  Haiti:                  ["#00209F", "#D21034"],  // bleu + rouge
  Curacao:                ["#002B7F", "#F9E814"],  // blauw + geel
  // Africa
  Morocco:                ["#C1272D", "#006233"],  // rouge + vert
  Senegal:                ["#00853F", "#FDEF42"],  // vert + jaune
  Nigeria:                ["#008751", "#FFFFFF"],  // vert + blanc
  Ghana:                  ["#006B3F", "#FCD116"],  // vert + jaune
  "Ivory Coast":          ["#F77F00", "#009A44"],  // orange + vert
  Cameroon:               ["#009A44", "#CE1126"],  // vert + rouge
  Egypt:                  ["#CE1126", "#FFFFFF"],  // rouge + blanc
  Algeria:                ["#006233", "#FFFFFF"],  // vert + blanc
  Tunisia:                ["#E70013", "#FFFFFF"],  // rouge + blanc
  "South Africa":         ["#007A4D", "#FFB612"],  // vert + or
  "DR Congo":             ["#007FFF", "#F7D618"],  // bleu + jaune
  "Cape Verde":           ["#003893", "#CF2027"],  // azul + vermelho
  // Asia
  Japan:                  ["#BC002D", "#FFFFFF"],  // hinomaru red + white
  "South Korea":          ["#003478", "#C60C30"],  // navy + red
  Australia:              ["#00843D", "#FFCD00"],  // green + gold
  Iran:                   ["#239F40", "#DA0000"],  // sabz + sorkh
  "Saudi Arabia":         ["#006C35", "#FFFFFF"],  // green + white
  Iraq:                   ["#CE1126", "#007A3D"],  // red + green
  Qatar:                  ["#8D1B3D", "#FFFFFF"],  // maroon + white
  Uzbekistan:             ["#1EB53A", "#1EBFFF"],  // green + blue
  Jordan:                 ["#007A3D", "#CE1126"],  // green + red
  "New Zealand":          ["#00247D", "#CC142B"],  // navy + red
};

function getTeamColor(name: string): string {
  return TEAM_FLAG[name]?.[0] ?? "#6666AA";
}

function getTeamDual(name: string): [string, string] {
  return TEAM_FLAG[name] ?? ["#6666AA", "#444466"];
}

function getPrediction(
  predictions: Record<string, Prediction>,
  home: string,
  away: string
): Prediction {
  if (predictions[`${home}|${away}`]) return predictions[`${home}|${away}`];
  const rev = predictions[`${away}|${home}`];
  if (rev) return { home_win: rev.away_win, draw: rev.draw, away_win: rev.home_win };
  return { home_win: 0.34, draw: 0.32, away_win: 0.34 };
}

function getWinnerKey(pred: Prediction): "home" | "draw" | "away" {
  if (pred.home_win >= pred.draw && pred.home_win >= pred.away_win) return "home";
  if (pred.away_win >= pred.draw && pred.away_win >= pred.home_win) return "away";
  return "draw";
}

interface Props {
  teams: Record<string, TeamInfo>;
  predictions: Record<string, Prediction>;
  matches: HistoricalMatch[];
  liveMatches?: LiveMatch[];
  narrations?: Record<string, string>;
  agentNotes?: Record<string, string>;
  onSelectDialect?: (lang: Lang) => void;
}

const DIALECT_OPTIONS: Array<{ key: Lang; label: string; flag: string }> = [
  { key: "bogotano", label: "Bogotano", flag: "🇨🇴" },
  { key: "paisa",    label: "Paisa",    flag: "🇨🇴" },
  { key: "boyaco",   label: "Boyaco",   flag: "🇨🇴" },
  { key: "costeño",  label: "Costeño",  flag: "🇨🇴" },
  { key: "en",       label: "English",  flag: "🇺🇸" },
];

// ── Pressure badges ────────────────────────────────────────────────────────────

interface PressureInfo {
  level: "must_win" | "comfortable";
  pts: number;
}

function parseFifaNote(note: string): {
  home: PressureInfo | null;
  away: PressureInfo | null;
  altitude: number | null;
} {
  const hm = note.match(/home_pressure=(\w+)\((\d+)pts\)/);
  const am = note.match(/away_pressure=(\w+)\((\d+)pts\)/);
  const alt = note.match(/altitude=(\d+)m/);
  return {
    home: hm ? { level: hm[1] as PressureInfo["level"], pts: parseInt(hm[2]) } : null,
    away: am ? { level: am[1] as PressureInfo["level"], pts: parseInt(am[2]) } : null,
    altitude: alt ? parseInt(alt[1]) : null,
  };
}

function PressureBadges({
  note, home, away,
}: { note: string; home: string; away: string }) {
  const { home: hp, away: ap, altitude } = parseFifaNote(note);
  const hasPressure = hp?.level === "must_win" || ap?.level === "must_win";
  const hasAltitude = altitude !== null && altitude >= 1500;
  if (!hasPressure && !hasAltitude) return null;

  function Badge({ label, color, bg, border }: {
    label: string; color: string; bg: string; border: string;
  }) {
    return (
      <span
        className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 font-mono"
        style={{ fontSize: "0.62rem", letterSpacing: "0.04em", color, background: bg, border: `1px solid ${border}` }}
      >
        {label}
      </span>
    );
  }

  function pressureLabel(info: PressureInfo, name: string) {
    if (info.level !== "must_win") return null;
    const flag = info.pts === 0 ? "🔴" : "🟠";
    const text = info.pts === 0
      ? `${name} · ELIMINACIÓN SI PIERDE · ${info.pts} pts`
      : `${name} · NECESITA GANAR · ${info.pts} pts`;
    const isRed = info.pts === 0;
    return (
      <Badge
        key={name}
        label={`${flag} ${text}`}
        color={isRed ? "#ff6b6b" : "#ffb347"}
        bg={isRed ? "rgba(207,10,44,0.12)" : "rgba(255,140,0,0.12)"}
        border={isRed ? "rgba(207,10,44,0.25)" : "rgba(255,140,0,0.25)"}
      />
    );
  }

  function comfortLabel(info: PressureInfo, name: string, rivalIsMustWin: boolean) {
    if (info.level !== "comfortable" || !rivalIsMustWin) return null;
    return (
      <Badge
        key={name}
        label={`🟢 ${name} · CÓMODO · ${info.pts} pts`}
        color="#6bcb77"
        bg="rgba(107,203,119,0.10)"
        border="rgba(107,203,119,0.22)"
      />
    );
  }

  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {hp && pressureLabel(hp, home)}
      {ap && pressureLabel(ap, away)}
      {hp && ap && comfortLabel(hp, home, ap.level === "must_win")}
      {hp && ap && comfortLabel(ap, away, hp.level === "must_win")}
      {hasAltitude && (
        <Badge
          label={`🔵 ALTITUD · ${altitude}m`}
          color="#7ec8e3"
          bg="rgba(126,200,227,0.10)"
          border="rgba(126,200,227,0.22)"
        />
      )}
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   PREDICTOR PRINCIPAL
══════════════════════════════════════════════════════ */
function poissonPmf(k: number, lam: number): number {
  let f = 1;
  for (let i = 2; i <= k; i++) f *= i;
  return (Math.exp(-lam) * Math.pow(lam, k)) / f;
}

/**
 * Marcador más probable vía Poisson independiente (λ = promedio goles
 * anotados vs recibidos), condicionado al resultado que predijo el modelo.
 */
function mostLikelyScore(
  homeInfo: TeamInfo | undefined,
  awayInfo: TeamInfo | undefined,
  pred: Prediction
): { s1: number; s2: number } {
  const l1 = Math.max(0.2, ((homeInfo?.goals_scored ?? 1.3) + (awayInfo?.goals_conceded ?? 1.2)) / 2);
  const l2 = Math.max(0.2, ((awayInfo?.goals_scored ?? 1.3) + (homeInfo?.goals_conceded ?? 1.2)) / 2);
  const outcome =
    pred.home_win >= pred.draw && pred.home_win >= pred.away_win ? "home"
    : pred.away_win >= pred.draw ? "away" : "draw";

  let best = { s1: 1, s2: 1, p: -1 };
  for (let i = 0; i <= 5; i++) {
    for (let j = 0; j <= 5; j++) {
      const consistent = outcome === "home" ? i > j : outcome === "away" ? i < j : i === j;
      if (!consistent) continue;
      const p = poissonPmf(i, l1) * poissonPmf(j, l2);
      if (p > best.p) best = { s1: i, s2: j, p };
    }
  }
  return best;
}

export default function Predictor({ teams, predictions, matches, liveMatches, narrations, agentNotes, onSelectDialect }: Props) {
  const T = useLang();
  const teamList = useMemo(
    () => Object.entries(teams).sort((a, b) => a[0].localeCompare(b[0])),
    [teams]
  );

  const [home, setHome]             = useState("Colombia");
  const [away, setAway]             = useState("Portugal");
  const [predicted, setPredicted]   = useState(false);
  const [loading, setLoading]       = useState(false);
  const [justPredicted, setJustPredicted] = useState(false);
  const [showMatchOverlay, setShowMatchOverlay] = useState(false);

  /* Partidos del día (fecha local). Solo fixtures con ambos equipos
     definidos en el modelo — descarta placeholders del knockout. */
  const todayStr = new Date().toLocaleDateString("en-CA"); // YYYY-MM-DD
  const day = useMemo(() => {
    const { date, fixtures } = fixturesOfTheDay(liveMatches ?? [], todayStr);
    return { date, fixtures: fixtures.filter((f) => teams[f.team1] && teams[f.team2]) };
  }, [liveMatches, teams, todayStr]);

  /* Agrupa los partidos de hoy por grupo (J3: hasta 3 grupos/6 partidos el
     mismo día) para que cada grupo tenga su propia fila en vez de un único
     scroll horizontal donde se pierden los partidos de los otros grupos. */
  const dayFixturesByGroup = useMemo(() => {
    const groups = new Map<string, typeof day.fixtures>();
    for (const f of day.fixtures) {
      const key = f.group ?? "";
      const arr = groups.get(key);
      if (arr) arr.push(f);
      else groups.set(key, [f]);
    }
    // Ordena por HORA de juego (kickoff UTC), no alfabéticamente por grupo.
    // En J3 los grupos juegan a horas distintas (p.ej. I a las 19:00, G a las 03:00):
    // el grupo que arranca primero debe ir primero. Fallback alfabético si no hay hora.
    const earliest = (fs: typeof day.fixtures) =>
      Math.min(...fs.map((f) => (f.utc ? Date.parse(f.utc) : Number.POSITIVE_INFINITY)));
    return [...groups.entries()].sort(([ga, fa], [gb, fb]) => {
      const ta = earliest(fa);
      const tb = earliest(fb);
      const fta = Number.isFinite(ta);
      const ftb = Number.isFinite(tb);
      if (fta && ftb && ta !== tb) return ta - tb;
      if (fta !== ftb) return fta ? -1 : 1; // el que tiene hora conocida va primero
      return ga.localeCompare(gb);           // misma hora o sin datos → alfabético estable
    });
  }, [day.fixtures]);

  /* Carga por defecto el primer partido pendiente del día: solo queda dar Predecir */
  const autoloaded = useRef(false);
  useEffect(() => {
    if (autoloaded.current || day.fixtures.length === 0) return;
    autoloaded.current = true;
    const next = day.fixtures.find((f) => f.score1 === null) ?? day.fixtures[0];
    setHome(next.team1);
    setAway(next.team2);
  }, [day]);

  const homeInfo   = teams[home];
  const awayInfo   = teams[away];
  const pred       = getPrediction(predictions, home, away);
  const [homeColor, homeColor2] = getTeamDual(home);
  const [awayColor, awayColor2] = getTeamDual(away);
  const winnerKey  = getWinnerKey(pred);

  const donutData = [
    { name: `${homeInfo?.flag ?? ""} ${home}`, value: +(pred.home_win * 100).toFixed(1), fill: homeColor },
    { name: T.draw,                             value: +(pred.draw     * 100).toFixed(1), fill: "#666688" },
    { name: `${awayInfo?.flag ?? ""} ${away}`, value: +(pred.away_win * 100).toFixed(1), fill: awayColor },
  ];

  const h2h = useMemo(
    () =>
      matches
        .filter(
          (m) =>
            (m.home_team === home && m.away_team === away) ||
            (m.home_team === away && m.away_team === home)
        )
        .sort((a, b) => b.year - a.year)
        .slice(0, 6),
    [matches, home, away]
  );

  const [showDialectPicker, setShowDialectPicker] = useState(false);

  function requestPredict() {
    if (home === away) return;
    setShowDialectPicker(true);
  }

  function pickDialectAndPredict(dialect: Lang) {
    setShowDialectPicker(false);
    onSelectDialect?.(dialect);
    handlePredict();
  }

  function handlePredict() {
    if (home === away) return;

    const isSpecialMatch =
      (home === "Colombia" && away === "Portugal") ||
      (home === "Portugal" && away === "Colombia");

    setLoading(true);
    setPredicted(false);
    setJustPredicted(false);

    if (isSpecialMatch) {
      setShowMatchOverlay(true);
      // Resultados calculados en background a los 1.4s, overlay desaparece a los 5s
      setTimeout(() => {
        setLoading(false);
        setPredicted(true);
      }, 1400);
      setTimeout(() => {
        setShowMatchOverlay(false);
        setJustPredicted(true);
        setTimeout(() => setJustPredicted(false), 2400);
      }, 5000);
    } else {
      setTimeout(() => {
        setLoading(false);
        setPredicted(true);
        setJustPredicted(true);
        setTimeout(() => setJustPredicted(false), 2400);
      }, 1400);
    }
  }

  function handleSwap() {
    setHome(away);
    setAway(home);
    setPredicted(false);
  }

  return (
    <motion.div variants={staggerContainer} initial="hidden" animate="visible" className="space-y-5">
      {/* ── Partidos del día: clic para cargarlos en el predictor ── */}
      {day.fixtures.length > 0 && (
        <motion.div
          variants={fadeUp}
          className="rounded-2xl p-4"
          style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <span className="live-dot" />
            <span
              className="text-[10px] uppercase tracking-widest"
              style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
            >
              {day.date === todayStr ? T.todayTitle : T.nextMatchesTitle} ·{" "}
              {new Date(day.date + "T12:00:00").toLocaleDateString(T.locale, {
                weekday: "short", day: "numeric", month: "short",
              })}
            </span>
          </div>
          <div className="space-y-2">
            {dayFixturesByGroup.map(([group, fixtures]) => (
              <div key={group || "sin-grupo"} className="flex items-center gap-2">
                {group && (
                  <span
                    className="shrink-0 text-[10px] uppercase tracking-wider w-5 text-center"
                    style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
                  >
                    {group.replace("Group ", "")}
                  </span>
                )}
                <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-hide flex-1">
                  {fixtures.map((f) => {
                    const isSel =
                      (home === f.team1 && away === f.team2) ||
                      (home === f.team2 && away === f.team1);
                    const done = f.score1 !== null && f.score2 !== null;
                    return (
                      <button
                        key={`${f.team1}|${f.team2}`}
                        onClick={() => { setHome(f.team1); setAway(f.team2); setPredicted(false); }}
                        className="shrink-0 flex items-center gap-2 px-3 py-2 rounded-xl text-sm transition-all"
                        style={{
                          background: isSel ? "rgba(212,168,67,0.12)" : "var(--color-arena-elevated)",
                          border: `1px solid ${isSel ? "rgba(212,168,67,0.45)" : "rgba(255,255,255,0.07)"}`,
                          color: "var(--color-ink-primary)",
                          fontFamily: "var(--font-body)",
                          cursor: "pointer",
                        }}
                      >
                        <span>{teams[f.team1]?.flag} {f.team1}</span>
                        <span
                          className="tabular-nums"
                          style={{
                            fontFamily: "var(--font-mono)", fontSize: "0.7rem",
                            color: done ? "var(--color-wc-gold)" : "var(--color-ink-muted)",
                          }}
                        >
                          {done ? `${f.score1}–${f.score2}` : "vs"}
                        </span>
                        <span>{f.team2} {teams[f.team2]?.flag}</span>
                      </button>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        </motion.div>
      )}


      {/* ── Overlay especial Colombia vs Portugal ── */}
      <ColombiaPortugalOverlay active={showMatchOverlay} />

      {/* ── Tarjeta principal ── */}
      <motion.div variants={fadeUp} className="relative">
        <div className="absolute inset-0 rounded-2xl overflow-hidden pointer-events-none" aria-hidden>
          <motion.div
            className="absolute inset-0"
            animate={{ background: `radial-gradient(ellipse 50% 80% at 5% 50%, ${homeColor}28 0%, transparent 65%)` }}
            transition={{ duration: 1.0, ease: "easeInOut" }}
          />
          <motion.div
            className="absolute inset-0"
            animate={{ background: `radial-gradient(ellipse 50% 80% at 95% 50%, ${awayColor}28 0%, transparent 65%)` }}
            transition={{ duration: 1.0, ease: "easeInOut" }}
          />
        </div>

        <div
          className="relative rounded-2xl overflow-hidden"
          style={{
            background: "var(--color-arena-card)",
            border: "1px solid rgba(255,255,255,0.07)",
            boxShadow: "0 2px 8px rgba(0,0,0,0.5), 0 16px 48px rgba(0,0,0,0.4)",
          }}
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 sm:px-6 pt-4 sm:pt-6 pb-3 sm:pb-4">
            <div className="flex items-center gap-3">
              <div className="w-0.5 h-5 rounded-full" style={{ background: "var(--color-wc-gold)" }} />
              <span
                className="text-[11px] tracking-widest uppercase"
                style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
              >
                {T.matchPredictor}
              </span>
            </div>
            <span
              className="text-[10px] tracking-wider hidden sm:block"
              style={{ fontFamily: "var(--font-mono)", color: "rgba(212,168,67,0.50)" }}
            >
              {T.wcTag}
            </span>
          </div>

          <div
            className="h-px mx-6 mb-5"
            style={{ background: "linear-gradient(90deg, transparent, rgba(212,168,67,0.20), transparent)" }}
          />

          {/* Selectores */}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 sm:gap-3 px-3 sm:px-6 pb-4 sm:pb-6">
            <TeamPicker
              label={T.home}
              selected={home}
              teamList={teamList}
              info={homeInfo}
              onChange={(v) => { setHome(v); setPredicted(false); }}
              side="left"
            />
            <VsOrb isPredicted={predicted} onSwap={handleSwap} />
            <TeamPicker
              label={T.away}
              selected={away}
              teamList={teamList}
              info={awayInfo}
              onChange={(v) => { setAway(v); setPredicted(false); }}
              side="right"
            />
          </div>

          <div style={{ height: 1, background: "rgba(255,255,255,0.05)" }} />

          {/* Zona de resultados */}
          <div className="px-3 sm:px-6 py-4 sm:py-5 relative" style={{ minHeight: 120 }}>
            <AnimatePresence mode="wait">
              {loading ? (
                <ScannerLoader key="loading" homeFlag={homeInfo?.flag} awayFlag={awayInfo?.flag} />
              ) : predicted ? (
                <ResultsZone
                  key="results"
                  pred={pred}
                  home={home}
                  away={away}
                  homeInfo={homeInfo}
                  awayInfo={awayInfo}
                  homeColor={homeColor}
                  homeColor2={homeColor2}
                  awayColor={awayColor}
                  awayColor2={awayColor2}
                  winnerKey={winnerKey}
                  donutData={donutData}
                  justPredicted={justPredicted}
                />
              ) : (
                <IdleHint key="idle" />
              )}
            </AnimatePresence>
            <CelebrationBurst active={justPredicted} winnerColor={winnerKey === "home" ? homeColor : winnerKey === "away" ? awayColor : "#C9981F"} />
          </div>

          <div className="px-3 sm:px-6 pb-4 sm:pb-6">
            <PredictCTA onClick={requestPredict} disabled={loading || home === away} loading={loading} />
          </div>
        </div>
      </motion.div>

      {/* ── Selector de dialecto: obligatorio antes de narrar la predicción ── */}
      <AnimatePresence>
        {showDialectPicker && (
          <motion.div
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
            onClick={() => setShowDialectPicker(false)}
            style={{
              position: "fixed", inset: 0, zIndex: 200,
              background: "rgba(8,6,10,0.72)", backdropFilter: "blur(3px)",
              display: "flex", alignItems: "center", justifyContent: "center", padding: "1rem",
            }}
          >
            <motion.div
              initial={{ opacity: 0, y: 16, scale: 0.97 }} animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 10, scale: 0.97 }} transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
              onClick={(e) => e.stopPropagation()}
              style={{
                maxWidth: 380, width: "100%",
                background: "var(--color-arena-card)", border: "1px solid rgba(212,168,67,0.25)",
                borderRadius: 18, padding: "1.4rem",
                boxShadow: "0 20px 60px rgba(0,0,0,0.5)",
              }}
            >
              <p style={{
                fontFamily: "var(--font-mono)", fontSize: "0.62rem", letterSpacing: "0.12em",
                textTransform: "uppercase", color: "var(--color-wc-gold)", fontWeight: 700,
                marginBottom: "0.4rem",
              }}>
                🎙️ Antes de narrar…
              </p>
              <p style={{
                fontFamily: "var(--font-body)", fontSize: "0.85rem", color: "var(--color-ink-primary)",
                marginBottom: "1.1rem", lineHeight: 1.5,
              }}>
                ¿En qué dialecto quieres que el narrador cuente esta predicción?
              </p>
              <div className="grid grid-cols-2 gap-2">
                {DIALECT_OPTIONS.map((opt) => (
                  <button
                    key={opt.key}
                    onClick={() => pickDialectAndPredict(opt.key)}
                    style={{
                      padding: "0.6rem 0.5rem", borderRadius: 10, cursor: "pointer",
                      border: "1px solid rgba(212,168,67,0.25)", background: "rgba(212,168,67,0.06)",
                      color: "var(--color-ink-primary)", fontFamily: "var(--font-body)",
                      fontWeight: 600, fontSize: "0.8rem",
                      display: "flex", alignItems: "center", justifyContent: "center", gap: "0.4rem",
                    }}
                  >
                    <span>{opt.flag}</span>
                    <span>{opt.label}</span>
                  </button>
                ))}
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Marcador más probable (Poisson) ── */}
      <AnimatePresence>
        {predicted && (() => {
          const score = mostLikelyScore(homeInfo, awayInfo, pred);
          const fifaNote = agentNotes?.[`${home}|${away}`] ?? agentNotes?.[`${away}|${home}`] ?? "";
          return (
            <motion.div
              variants={fadeUp} initial="hidden" animate="visible" exit="exit"
              className="rounded-2xl p-4"
              style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
            >
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-xs uppercase tracking-widest font-mono" style={{ color: "var(--color-ink-muted)" }}>
                  {T.likelyScore}
                </span>
                <span className="score-final">
                  {homeInfo?.flag} {score.s1}–{score.s2} {awayInfo?.flag}
                </span>
                <span className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
                  {T.likelyScoreNote}
                </span>
              </div>
              {fifaNote && <PressureBadges note={fifaNote} home={home} away={away} />}
            </motion.div>
          );
        })()}
      </AnimatePresence>

      {/* ── Agent Debate (consenso de 3 agentes) ── */}
      {predicted && <AgentDebatePanel homeTeam={home} awayTeam={away} variant="compact" />}

      {/* ── H2H ── */}
      <AnimatePresence>
        {predicted && (
          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="visible"
            exit="exit"
            className="rounded-2xl p-5"
            style={{ background: "var(--color-arena-card)", border: "1px solid rgba(255,255,255,0.07)" }}
          >
            <h3
              className="text-sm mb-4 flex items-center gap-2 uppercase tracking-wider"
              style={{ fontFamily: "var(--font-heading)", fontWeight: 700, color: "var(--color-ink-secondary)" }}
            >
              <span>⚔️</span>
              <span>{T.h2hTitle}</span>
              <span
                className="font-normal text-[11px]"
                style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
              >
                ({h2h.length} {T.h2hMatches})
              </span>
            </h3>

            {h2h.length === 0 ? (
              <p className="text-sm" style={{ color: "var(--color-ink-muted)" }}>
                {T.noH2H}
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table>
                  <thead>
                    <tr>
                      {[T.year, T.home, T.scoreCol, T.away, T.winnerCol].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {h2h.map((m, i) => {
                      const winner =
                        m.outcome === "home_win" ? m.home_team
                        : m.outcome === "away_win" ? m.away_team
                        : null;
                      const isHomeWin = winner === home;
                      const wColor = isHomeWin ? homeColor : awayColor;
                      return (
                        <tr key={i}>
                          <td style={{ color: "var(--color-ink-muted)" }}>{m.year}</td>
                          <td>{teams[m.home_team]?.flag} {m.home_team}</td>
                          <td
                            className="tabular-nums"
                            style={{ fontFamily: "var(--font-mono)", fontWeight: 700 }}
                          >
                            {m.home_score}–{m.away_score}
                          </td>
                          <td>{teams[m.away_team]?.flag} {m.away_team}</td>
                          <td>
                            {winner ? (
                              <span
                                className="text-xs font-bold px-2 py-0.5 rounded-full"
                                style={{ background: `${wColor}20`, color: wColor }}
                              >
                                {teams[winner]?.flag} {winner}
                              </span>
                            ) : (
                              <span className="text-xs" style={{ color: "var(--color-ink-muted)" }}>
                                {T.draw}
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Narración unificada IA ── */}
      <AnimatePresence>
        {predicted && (
          <UnifiedNarration
            key={`narr-${home}-${away}`}
            home={home} away={away}
            homeInfo={homeInfo} awayInfo={awayInfo}
            pred={pred}
            stadium={getStadium(home, away)}
            narrations={narrations}
          />
        )}
      </AnimatePresence>

      {predicted && (
        <motion.p
          variants={fadeUp}
          initial="hidden"
          animate="visible"
          className="text-center text-xs"
          style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
        >
          ℹ️ {T.modelNote}
        </motion.p>
      )}
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   UNIFIED NARRATION — JSON → DeepSeek → Markdown
   Reemplaza NarratorBanner + AgentAnalysisPanel
══════════════════════════════════════════════════════ */

function buildNarratorPayload(
  home: string, away: string,
  hi: TeamInfo, ai: TeamInfo,
  pred: Prediction,
  lang: Lang,
  stadium: Stadium | null,
  agents: AgentResult[]
) {
  const dialectMap: Record<Lang, string> = {
    bogotano: "bogotano", paisa: "paisa",
    boyaco: "boyacense", costeño: "costeño", en: "en",
  };

  const homeVotes = agents.filter(a => a.verdict === "home").length;
  const awayVotes = agents.filter(a => a.verdict === "away").length;
  const drawVotes = agents.filter(a => a.verdict === "draw").length;
  const cv = homeVotes > awayVotes && homeVotes > drawVotes ? "home"
    : awayVotes > homeVotes && awayVotes > drawVotes ? "away" : "draw";

  const spread = Math.abs(pred.home_win - pred.away_win) * 100;
  const favTeam = cv === "home" ? home : cv === "away" ? away : null;

  const agentNames: Record<string, string> = {
    intmatch: "IntMatch", roster: "Roster", media: "Media",
    travel: "Travel", finops: "FinOps", fifareg: "FIFARegs",
  };
  const agentCats: Record<string, string> = {
    intmatch: "Táctica", roster: "Plantel", media: "Prensa",
    travel: "Fatiga", finops: "Cuotas", fifareg: "Reglamento",
  };
  const shortReasons: Record<string, string> = {
    intmatch: `ELO Δ${Math.round(hi.elo - ai.elo) > 0 ? "+" : ""}${Math.round(hi.elo - ai.elo)} (${Math.round(hi.elo)} vs ${Math.round(ai.elo)}).`,
    roster:   `Mundiales: ${hi.wc_matches} vs ${ai.wc_matches} partidos.`,
    media:    `Rankings #${hi.rank} vs #${ai.rank}.`,
    travel:   `${hi.confederation} vs ${ai.confederation}.`,
    finops:   `Cuotas ${(1/pred.home_win).toFixed(2)} / ${(1/pred.draw).toFixed(2)} / ${(1/pred.away_win).toFixed(2)}.`,
    fifareg:  `${hi.wc_matches} vs ${ai.wc_matches} juegos de Copa.`,
  };

  const homeExpG = Math.max(0, Math.round(hi.goals_scored * 0.88));
  const awayExpG = Math.max(0, Math.round(ai.goals_scored * 0.88));

  return {
    dialecto: dialectMap[lang],
    fase: "grupo",
    match: {
      home, away,
      home_emoji: hi.flag ?? "🏳️",
      away_emoji: ai.flag ?? "🏳️",
      venue:    stadium?.name ?? "—",
      city:     stadium?.city ?? "—",
      capacity: stadium?.capacity ?? 0,
      elo_home: Math.round(hi.elo), elo_away: Math.round(ai.elo),
      rank_home: hi.rank,           rank_away: ai.rank,
      prob_home: Math.round(pred.home_win * 100),
      prob_draw: Math.round(pred.draw     * 100),
      prob_away: Math.round(pred.away_win * 100),
      score_prediction: `${homeExpG}-${awayExpG}`,
    },
    competition_context: {
      group_difficulty: Math.min(hi.rank, ai.rank) <= 8 ? "alta" : Math.min(hi.rank, ai.rank) <= 20 ? "media" : "baja",
      home_need: pred.home_win > 0.52 ? "favorable para ganar" : pred.home_win < 0.28 ? "necesita un resultado positivo" : "cualquier resultado puede servir",
      away_need: pred.away_win > 0.52 ? "favorable para ganar" : pred.away_win < 0.28 ? "necesita un resultado positivo" : "cualquier resultado puede servir",
      elimination_risk: spread < 10 ? "ambos en riesgo" : spread < 22 ? "el más débil en riesgo" : "el favorito puede cerrarlo",
      next_rival: "por definir",
    },
    agent_summary: agents.map(a => ({
      agent:      agentNames[a.id]    ?? a.id,
      category:   agentCats[a.id]     ?? a.id,
      verdict:    a.verdict === "home" ? home : a.verdict === "away" ? away : "Empate",
      confidence: Math.round(a.confidence * 100),
      delta:      parseFloat((a.delta * 100).toFixed(1)),
      reason:     shortReasons[a.id] ?? a.keyMetric,
    })),
    final_model: {
      favorite:        favTeam ?? "Empate técnico",
      risk_level:      spread < 10 ? "alto" : spread < 22 ? "medio" : "bajo",
      consensus:       Math.max(homeVotes, awayVotes) >= 4 ? "claro" : homeVotes === awayVotes ? "dividido" : "leve",
      main_risk_home:  hi.rank > ai.rank + 8 ? "diferencia de nivel en contra" : "puede sufrir contragolpe",
      main_risk_away:  ai.wc_matches < hi.wc_matches ? "menor experiencia mundialista" : "debe aguantar la presión",
      final_pick:      `${favTeam ?? home} ${homeExpG}-${awayExpG}`,
    },
  };
}

/* Renderiza el markdown devuelto por DeepSeek */
function inlineBold(text: string): React.ReactNode {
  const parts = text.split(/\*\*(.*?)\*\*/);
  if (parts.length === 1) return text;
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1
          ? <strong key={i} style={{ color: "var(--color-ink-primary)", fontWeight: 700 }}>{p}</strong>
          : p
      )}
    </>
  );
}

function NarratorMarkdown({ text, isStreaming }: { text: string; isStreaming: boolean }) {
  const lines = text.split("\n");
  return (
    <div style={{ fontFamily: "var(--font-body)", fontSize: "0.85rem", lineHeight: 1.72, color: "var(--color-ink-secondary)" }}>
      {lines.map((line, i) => {
        if (/^#{1,3} /.test(line)) {
          const content = line.replace(/^#{1,3} /, "");
          return (
            <p key={i} style={{
              fontFamily: "var(--font-mono)", fontSize: "0.6rem", letterSpacing: "0.16em",
              textTransform: "uppercase", color: "var(--color-wc-gold)",
              margin: "1rem 0 0.3rem", fontWeight: 700,
            }}>
              {inlineBold(content)}
            </p>
          );
        }
        if (line.startsWith("- ")) {
          return (
            <div key={i} style={{ display: "flex", gap: "0.5rem", margin: "0.22rem 0" }}>
              <span style={{ color: "var(--color-wc-gold)", flexShrink: 0, marginTop: "0.05rem" }}>·</span>
              <span>{inlineBold(line.slice(2))}</span>
            </div>
          );
        }
        if (line.trim() === "") return <div key={i} style={{ height: "0.45rem" }} />;
        return <p key={i} style={{ margin: "0.18rem 0" }}>{inlineBold(line)}</p>;
      })}
      {isStreaming && (
        <motion.span
          animate={{ opacity: [1, 0] }}
          transition={{ duration: 0.5, repeat: Infinity }}
          style={{ display: "inline-block", width: 2, height: "0.9em", background: "var(--color-wc-gold)", marginLeft: 2, verticalAlign: "text-bottom", borderRadius: 1 }}
        />
      )}
    </div>
  );
}

const DIALECT_LABELS: { key: Lang; label: string }[] = [
  { key: "bogotano", label: "Bog." },
  { key: "paisa",    label: "Pai." },
  { key: "boyaco",   label: "Boy." },
  { key: "costeño",  label: "Cos." },
  { key: "en",       label: "EN"   },
];

function UnifiedNarration({
  home, away, homeInfo, awayInfo, pred, stadium, narrations,
}: {
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  pred: Prediction;
  stadium: Stadium | null;
  narrations?: Record<string, string>;
}) {
  const globalLang = useContext(LangContext);
  const [localLang, setLocalLang] = useState<Lang>(globalLang);
  const [aiText,   setAiText]   = useState("");
  const [aiStatus, setAiStatus] = useState<"loading" | "streaming" | "done" | "error">("loading");
  const abortRef = useRef<AbortController | null>(null);

  // Sync local lang when global changes (first selection)
  useEffect(() => { setLocalLang(globalLang); }, [globalLang]);

  const agents = useMemo(
    () => computeAgents(home, away, homeInfo, awayInfo, pred),
    [home, away, homeInfo, awayInfo, pred]
  );

  useEffect(() => {
    if (!homeInfo || !awayInfo || agents.length === 0) return;

    abortRef.current?.abort();
    setAiText("");
    setAiStatus("loading");

    // Si hay narración pre-computada, usarla directamente sin llamar a la API
    const narKey = `${home}|${away}|${localLang}`;
    const precomputed = narrations?.[narKey];
    if (precomputed) {
      setAiText(precomputed);
      setAiStatus("done");
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    const payload = buildNarratorPayload(home, away, homeInfo, awayInfo, pred, localLang, stadium, agents);

    (async () => {
      try {
        const res = await fetch("/api/narrator", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
          signal: ctrl.signal,
        });
        if (!res.ok || !res.body) { setAiStatus("error"); return; }

        const reader  = res.body.getReader();
        const decoder = new TextDecoder();
        let   full    = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          full += decoder.decode(value, { stream: true });
          setAiText(full);
          setAiStatus("streaming");
        }
        setAiStatus("done");
      } catch (err) {
        if ((err as Error).name !== "AbortError") setAiStatus("error");
      }
    })();

    return () => abortRef.current?.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [home, away, localLang, narrations]);

  if (!homeInfo || !awayInfo) return null;

  const isLoading   = aiStatus === "loading";
  const isStreaming = aiStatus === "streaming";
  const isError     = aiStatus === "error";

  return (
    <motion.div
      variants={fadeUp} initial="hidden" animate="visible" exit="exit"
      className="rounded-2xl overflow-hidden"
      style={{
        background: "var(--color-arena-card)",
        border: "1px solid rgba(255,255,255,0.07)",
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      }}
    >
      {/* Header */}
      <div style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="flex items-center justify-between px-5 py-3">
          <div className="flex items-center gap-3">
            <div style={{ width: 3, height: 18, background: "linear-gradient(180deg, var(--color-wc-gold) 0%, var(--color-wc-red) 100%)", borderRadius: 2 }} />
            <span style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "0.88rem", color: "var(--color-ink-primary)" }}>
              Análisis IA
            </span>
          </div>
          <motion.span
            animate={isLoading || isStreaming ? { opacity: [0.5, 1, 0.5] } : { opacity: 1 }}
            transition={isLoading || isStreaming ? { duration: 1.2, repeat: Infinity } : {}}
            style={{
              fontFamily: "var(--font-mono)", fontSize: "0.46rem", letterSpacing: "0.1em",
              padding: "0.12rem 0.5rem", borderRadius: 4,
              background: "rgba(201,152,31,0.08)", border: "1px solid rgba(201,152,31,0.2)",
              color: "var(--color-wc-gold)", textTransform: "uppercase",
            }}
          >
            {isLoading ? "⚙ Generando..." : isStreaming ? "⚙ IA ▍" : "⚙ Narrator AI"}
          </motion.span>
        </div>
        {/* Dialect selector */}
        <div className="flex gap-1 px-5 pb-2.5">
          {DIALECT_LABELS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => setLocalLang(key)}
              style={{
                fontFamily: "var(--font-mono)", fontSize: "0.58rem", letterSpacing: "0.06em",
                padding: "0.18rem 0.55rem", borderRadius: 4, cursor: "pointer",
                border: localLang === key ? "1px solid var(--color-wc-gold)" : "1px solid rgba(255,255,255,0.1)",
                background: localLang === key ? "rgba(201,152,31,0.15)" : "transparent",
                color: localLang === key ? "var(--color-wc-gold)" : "var(--color-ink-muted)",
                transition: "all 0.15s",
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="px-5 py-4" style={{ minHeight: 120 }}>
        {isLoading ? (
          <div className="flex items-center gap-2.5" style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", fontSize: "0.72rem" }}>
            <span>Analizando el partido</span>
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                animate={{ opacity: [0.15, 1, 0.15] }}
                transition={{ duration: 1.0, repeat: Infinity, delay: i * 0.22 }}
                style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: "var(--color-wc-gold)" }}
              />
            ))}
          </div>
        ) : isError ? (
          /* Fallback silencioso: muestra texto estático del escenario */
          <p style={{ fontFamily: "var(--font-body)", fontSize: "0.82rem", lineHeight: 1.65, color: "var(--color-ink-secondary)", margin: 0 }}>
            {homeInfo.flag} {home} vs {awayInfo.flag} {away} — {Math.round(pred.home_win * 100)}% / {Math.round(pred.draw * 100)}% / {Math.round(pred.away_win * 100)}%
          </p>
        ) : (
          <NarratorMarkdown text={aiText} isStreaming={isStreaming} />
        )}
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   NARRATOR BANNER — Agente Redactor de Jornada
   Genera narrativas vividas de periodismo deportivo
══════════════════════════════════════════════════════ */
type NarrativeScenario = "titan_clash" | "continental_war" | "redemption" | "perfect_storm" | "executioner" | "equilibrio";

/* Mapea el dialecto completo a la base "es"|"en"|"pt" usada en los records internos */
function toLangBase(lang: Lang): "es" | "en" | "pt" {
  return lang === "en" ? "en" : "es";
}

/* Badges por dialecto y escenario (solo los que difieren del español estándar) */
const DIALECT_BADGES: Partial<Record<NarrativeScenario, Partial<Record<Lang, string>>>> = {
  titan_clash:     { paisa: "Clásico berraconísimo", boyaco: "Partido histórico, sumercé", costeño: "Partidazo caliente, mano" },
  continental_war: { paisa: "Rivalidad berraca",     boyaco: "Rivalidad histórica",        costeño: "Pelea que quema, mano" },
  redemption:      { paisa: "¡La sorpresota!",        boyaco: "La hazaña posible",          costeño: "¡La sorpresa, epa!" },
  perfect_storm:   { paisa: "Sin favorito, berraco",  boyaco: "Muy parejo, sumercé",        costeño: "Pelao pelao, mano" },
  executioner:     { paisa: "Sale a vencer, parcero", boyaco: "Sale con ventaja, sumercé",  costeño: "Llegó mandando, mano" },
  equilibrio:      { paisa: "Bien parejo, parcero",   boyaco: "Bien parejo, sumercé",       costeño: "Pelao, epa mano" },
};

/* Títulos del narrador por dialecto */
const DIALECT_TITLES: Partial<Record<NarrativeScenario, Partial<Record<Lang, string>>>> = {
  titan_clash:     { paisa: "DUELO BERRACONÍSIMO",             boyaco: "DUELO DE TITANES, SUMERCÉ",    costeño: "DUELO QUE QUEMA, MANO" },
  continental_war: { paisa: "GUERRA DE PARCEROS",              boyaco: "GUERRA CONTINENTAL, SUMERCÉ",  costeño: "GUERRA DE VECINOS, MANO" },
  redemption:      { paisa: "¡HAZAÑA PA' LA HISTORIA!",        boyaco: "¡HAZAÑA EN JUEGO, SUMERCÉ!",   costeño: "¡LA SORPRESA, MANO!" },
  perfect_storm:   { paisa: "¡TODO PELAO, PARCERO!",           boyaco: "MUY REÑIDO, SUMERCÉ",          costeño: "TODO PELAO, MANO" },
  executioner:     { paisa: "EL QUE MANDA VS. EL QUE SUEÑA",  boyaco: "FAVORITO VS. CENICIENTA",      costeño: "EL DURO VS. EL QUE SUEÑA" },
  equilibrio:      { paisa: "PARTIDO MUY PAREJO, PARCERO",     boyaco: "PARTIDO BIEN PAREJO, SUMERCÉ", costeño: "PARTIDO PELAO, MANO" },
};

/* Sufijo dialectal al final del texto narrativo */
const DIALECT_SUFFIX: Partial<Record<Lang, string>> = {
  bogotano: " No le dé papaya.",
  paisa:    " ¡Ese partido va a ser berraconísimo, parcero!",
  boyaco:   " Sumercé, ese partido vale la pena verlo con juicio.",
  costeño:  " ¡Eso va a estar caliente, mano, epa!",
};

function buildNarrative(
  scenario: NarrativeScenario,
  home: string, away: string,
  hi: TeamInfo, ai: TeamInfo,
  pred: Prediction,
  lang: Lang
): { emoji: string; title: string; badge: string; text: string; intensity: "critical" | "moderate" | "clear" } {
  const langBase = toLangBase(lang);
  const eloDiff = Math.abs(hi.elo - ai.elo);
  const favored = pred.home_win >= pred.away_win ? home : away;
  const underdog = pred.home_win >= pred.away_win ? away : home;
  const favInfo  = pred.home_win >= pred.away_win ? hi : ai;
  const undInfo  = pred.home_win >= pred.away_win ? ai : hi;
  const favPct   = Math.round(Math.max(pred.home_win, pred.away_win) * 100);
  const undPct   = Math.round(Math.min(pred.home_win, pred.away_win) * 100);
  const hp       = Math.round(pred.home_win * 100);
  const dp       = Math.round(pred.draw * 100);
  const ap       = Math.round(pred.away_win * 100);

  const T: Record<NarrativeScenario, { emoji: string; title: Record<"es"|"en"|"pt", string>; badge: Record<"es"|"en"|"pt", string>; text: Record<"es"|"en"|"pt", string>; intensity: "critical"|"moderate"|"clear" }> = {
    titan_clash: {
      emoji: "👑",
      title: { es: "DUELO DE TITANES", en: "CLASH OF TITANS", pt: "DUELO DE TITÃS" },
      badge: { es: "Partido del Siglo", en: "Match of the Century", pt: "Jogo do Século" },
      text: {
        es: `Dos colosos en la misma cancha. ${home} (#${hi.rank}, ELO ${hi.elo.toFixed(0)}) y ${away} (#${ai.rank}, ${ai.elo.toFixed(0)}) se miden en un duelo que puede definir la memoria de este Mundial. Solo ${eloDiff.toFixed(0)} puntos de ELO los separan — la diferencia entre el cielo y el infierno del fútbol. El que abra el marcador tendrá al rival contra las cuerdas. Aquí no hay segunda oportunidad.`,
        en: `Two colossi on the same pitch. ${home} (#${hi.rank}, ELO ${hi.elo.toFixed(0)}) versus ${away} (#${ai.rank}, ${ai.elo.toFixed(0)}) — a clash that will define the memory of this World Cup. Just ${eloDiff.toFixed(0)} ELO points between them. Whoever scores first has the other team against the ropes. There are no second chances here.`,
        pt: `Dois colossos no mesmo campo. ${home} (#${hi.rank}, ELO ${hi.elo.toFixed(0)}) contra ${away} (#${ai.rank}, ${ai.elo.toFixed(0)}) — um duelo que pode definir a memória desta Copa. Apenas ${eloDiff.toFixed(0)} pts de ELO os separam. Quem marcar primeiro encosta o rival na parede. Aqui não há segunda chance.`,
      },
      intensity: "critical",
    },
    continental_war: {
      emoji: "🔥",
      title: { es: "GUERRA CONTINENTAL", en: "CONTINENTAL SHOWDOWN", pt: "GUERRA CONTINENTAL" },
      badge: { es: "Rivalidad Total", en: "Total Rivalry", pt: "Rivalidade Total" },
      text: {
        es: `Vecinos, rivales, adversarios de siempre. ${home} y ${away} comparten confederación y se conocen de memoria. ${home} promedia ${hi.goals_scored.toFixed(1)} goles por partido — ${away} responde con ${ai.goals_conceded.toFixed(1)} en contra. El modelo calcula ${hp}–${dp}–${ap}, pero los clásicos continentales no respetan estadísticas: un gol en el momento equivocado puede incendiar todo.`,
        en: `Neighbors, rivals, lifelong enemies. ${home} and ${away} share a confederation and know each other inside out. ${home} averages ${hi.goals_scored.toFixed(1)} goals/match — ${away} concedes ${ai.goals_conceded.toFixed(1)}. The model says ${hp}–${dp}–${ap}, but continental derbies never respect statistics: one goal at the wrong moment can set everything on fire.`,
        pt: `Vizinhos, rivais, inimigos de sempre. ${home} e ${away} compartilham confederação e se conhecem de cor. ${home} médias ${hi.goals_scored.toFixed(1)} gols/jogo — ${away} sofre ${ai.goals_conceded.toFixed(1)}. O modelo projeta ${hp}–${dp}–${ap}, mas clássicos continentais não respeitam estatísticas: um gol no momento errado pode incendiar tudo.`,
      },
      intensity: "critical",
    },
    redemption: {
      emoji: "⚔️",
      title: { es: "GESTA HISTÓRICA EN JUEGO", en: "GIANT-KILLING IN SIGHT", pt: "ZEBRA À VISTA" },
      badge: { es: "Imperdible", en: "Must Watch", pt: "Imperdível" },
      text: {
        es: `${underdog} lleva ${undInfo.wc_matches} partidos de Copa en sus botas — veteranía que ningún modelo cuantifica del todo. Frente a ${favored} (${favPct}% de victoria, ELO ${favInfo.elo.toFixed(0)}), el papel no les da opciones. Pero el papel no juega. Con ${undInfo.goals_scored.toFixed(1)} goles anotados por partido, la Cenicienta está lista para bailar. Una jugada puede cambiar este partido — y este Mundial.`,
        en: `${underdog} carries ${undInfo.wc_matches} World Cup matches in its boots — experience no model fully quantifies. Against ${favored} (${favPct}% win probability, ELO ${favInfo.elo.toFixed(0)}), the data gives them no shot. But the data doesn't play. With ${undInfo.goals_scored.toFixed(1)} goals scored per match, the underdog is ready to dance. One moment can change this match — and this World Cup.`,
        pt: `${underdog} carrega ${undInfo.wc_matches} jogos de Copa nas chuteiras — experiência que nenhum modelo quantifica por completo. Contra ${favored} (${favPct}% de vitória, ELO ${favInfo.elo.toFixed(0)}), o papel não dá chances. Mas o papel não joga. Com ${undInfo.goals_scored.toFixed(1)} gols por jogo, a zebra está pronta para dançar. Um momento pode mudar este jogo — e esta Copa.`,
      },
      intensity: "moderate",
    },
    perfect_storm: {
      emoji: "⚡",
      title: { es: "TORMENTA PERFECTA", en: "PERFECT STORM", pt: "TEMPESTADE PERFEITA" },
      badge: { es: "Sin Favorito", en: "No Clear Favorite", pt: "Sem Favorito" },
      text: {
        es: `El modelo no puede decidir — y eso ya lo dice todo. ${home} (${hi.elo.toFixed(0)}) vs ${away} (${ai.elo.toFixed(0)}): solo ${eloDiff.toFixed(0)} puntos de ELO los separan. Las probabilidades rondan ${hp}–${dp}–${ap}. No hay favorito claro. No hay lógica que valga. Solo hay noventa minutos de fútbol puro, presión sin límite, y quien aguante mejor ese peso ganará esta tarde.`,
        en: `The model can't decide — and that says everything. ${home} (${hi.elo.toFixed(0)}) vs ${away} (${ai.elo.toFixed(0)}): just ${eloDiff.toFixed(0)} ELO points apart. Probabilities: ${hp}–${dp}–${ap}. No clear favorite. No logic holds here. Just ninety minutes of pure football, relentless pressure, and whoever handles that weight better will win today.`,
        pt: `O modelo não consegue decidir — e isso já diz tudo. ${home} (${hi.elo.toFixed(0)}) vs ${away} (${ai.elo.toFixed(0)}): apenas ${eloDiff.toFixed(0)} pts de ELO de diferença. Probabilidades: ${hp}–${dp}–${ap}. Sem favorito claro. Noventa minutos de futebol puro, pressão máxima, e quem aguentar melhor esse peso vencerá esta tarde.`,
      },
      intensity: "critical",
    },
    executioner: {
      emoji: "🎯",
      title: { es: "VERDUGO VS. CENICIENTA", en: "EXECUTIONER VS. UNDERDOG", pt: "CARRASCO VS. ZEBRA" },
      badge: { es: "Favorito Claro", en: "Clear Favorite", pt: "Favorito Claro" },
      text: {
        es: `${favored} llega en modo verdugo: ELO ${favInfo.elo.toFixed(0)}, ranking #${favInfo.rank} mundial, y ${favPct}% de probabilidades según el modelo ML+ELO. ${underdog} (ELO ${undInfo.elo.toFixed(0)}) no vino a mirar — con ${undInfo.goals_scored.toFixed(1)} goles por partido y ${undInfo.wc_matches} partidos de Copa, saben que en 90 minutos puede escribirse historia. El ${undPct}% que les da el modelo no es poco cuando juegas sin presión.`,
        en: `${favored} arrives with an executioner's mindset: ELO ${favInfo.elo.toFixed(0)}, ranked #${favInfo.rank} globally, ${favPct}% win probability from the ML+ELO model. ${underdog} (ELO ${undInfo.elo.toFixed(0)}) didn't come to watch — with ${undInfo.goals_scored.toFixed(1)} goals/match and ${undInfo.wc_matches} WC caps, they know history can be written in 90 minutes. That ${undPct}% is enough to try.`,
        pt: `${favored} chega como carrasco: ELO ${favInfo.elo.toFixed(0)}, ranking #${favInfo.rank} mundial, ${favPct}% de probabilidade pelo modelo ML+ELO. ${underdog} (ELO ${undInfo.elo.toFixed(0)}) não veio para assistir — com ${undInfo.goals_scored.toFixed(1)} gols/jogo e ${undInfo.wc_matches} jogos de Copa, sabe que a história pode ser escrita em 90 minutos. Esses ${undPct}% bastam para tentar.`,
      },
      intensity: "clear",
    },
    equilibrio: {
      emoji: "⚽",
      title: { es: "PARTIDO ABIERTO", en: "OPEN MATCH", pt: "JOGO ABERTO" },
      badge: { es: "Reñido", en: "Contested", pt: "Disputado" },
      text: {
        es: `${home} (#${hi.rank}) y ${away} (#${ai.rank}) se presentan casi igualados: ${eloDiff.toFixed(0)} puntos de ELO de diferencia, formas recientes similares (${hi.goals_scored.toFixed(1)} vs ${ai.goals_scored.toFixed(1)} goles por partido). La ventaja marginal de ${favored} (${favPct}%) es demasiado pequeña para ser concluyente. Una tarde de fútbol de las que piden concentración máxima, nervio, y el gol en el momento justo.`,
        en: `${home} (#${hi.rank}) and ${away} (#${ai.rank}) are almost even: ${eloDiff.toFixed(0)} ELO points apart, similar recent form (${hi.goals_scored.toFixed(1)} vs ${ai.goals_scored.toFixed(1)} goals/match). ${favored}'s marginal edge (${favPct}%) is too thin to be conclusive. An afternoon of football that demands maximum focus, nerves, and the right goal at the right moment.`,
        pt: `${home} (#${hi.rank}) e ${away} (#${ai.rank}) chegam quase empatados: ${eloDiff.toFixed(0)} pts de ELO de diferença, forma recente similar (${hi.goals_scored.toFixed(1)} vs ${ai.goals_scored.toFixed(1)} gols/jogo). A vantagem marginal de ${favored} (${favPct}%) é pequena demais. Uma tarde de futebol que exige concentração máxima e o gol no momento certo.`,
      },
      intensity: "moderate",
    },
  };

  const s = T[scenario];
  const dialectBadge = DIALECT_BADGES[scenario]?.[lang];
  const dialectTitle = DIALECT_TITLES[scenario]?.[lang];
  const suffix = DIALECT_SUFFIX[lang] ?? "";
  return {
    emoji: s.emoji,
    title: dialectTitle ?? s.title[langBase],
    badge: dialectBadge ?? s.badge[langBase],
    text:  s.text[langBase] + suffix,
    intensity: s.intensity,
  };
}

function detectScenario(hi: TeamInfo, ai: TeamInfo, pred: Prediction): NarrativeScenario {
  const eloDiff = Math.abs(hi.elo - ai.elo);
  const spread  = Math.max(pred.home_win, pred.away_win) - Math.min(pred.home_win, pred.away_win);
  const bothElite = hi.rank <= 12 && ai.rank <= 12;
  const sameConf  = hi.confederation === ai.confederation;
  const favWC     = pred.home_win >= pred.away_win ? hi.wc_matches : ai.wc_matches;
  const undWC     = pred.home_win >= pred.away_win ? ai.wc_matches : hi.wc_matches;
  const undMoreExp = undWC > favWC + 12;

  if (bothElite) return "titan_clash";
  if (sameConf && spread < 0.28) return "continental_war";
  if (spread > 0.30 && undMoreExp) return "redemption";
  if (spread < 0.13 && eloDiff < 70) return "perfect_storm";
  if (spread > 0.30) return "executioner";
  return "equilibrio";
}

/* Componente de palabra animada */
function NarratorWords({ text, narrative }: { text: string; narrative: string }) {
  const words = text.split(" ");
  return (
    <span key={narrative}>
      {words.map((w, i) => (
        <motion.span
          key={i}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: i * 0.028, duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
          style={{ display: "inline" }}
        >
          {w}{" "}
        </motion.span>
      ))}
    </span>
  );
}

function NarratorBanner({
  home, away, homeInfo, awayInfo, pred, homeColor, awayColor, stadium,
}: {
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  pred: Prediction; homeColor: string; awayColor: string;
  stadium: Stadium | null;
  T: ReturnType<typeof import("@/lib/i18n").useLang>;
}) {
  // ── All hooks unconditionally (Rules of React) ──────────────────────────
  const lang = useContext(LangContext);
  const [aiText,   setAiText]   = useState("");
  const [aiStatus, setAiStatus] = useState<"loading" | "streaming" | "done" | "error">("loading");
  const abortRef = useRef<AbortController | null>(null);

  const scenario: NarrativeScenario = (homeInfo && awayInfo)
    ? detectScenario(homeInfo, awayInfo, pred)
    : "equilibrio";
  const staticData = (homeInfo && awayInfo)
    ? buildNarrative(scenario, home, away, homeInfo, awayInfo, pred, lang)
    : null;

  useEffect(() => {
    if (!homeInfo || !awayInfo) return;

    setAiText("");
    setAiStatus("loading");

    // Debounce: skip API call if user changes teams fast
    const tid = setTimeout(() => {
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      (async () => {
        try {
          const res = await fetch("/api/narrator", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              home, away,
              homeWin:      Math.round(pred.home_win * 100),
              draw:         Math.round(pred.draw * 100),
              awayWin:      Math.round(pred.away_win * 100),
              homeElo:      homeInfo.elo.toFixed(0),
              awayElo:      awayInfo.elo.toFixed(0),
              homeRank:     homeInfo.rank,
              awayRank:     awayInfo.rank,
              homeWcMatches: homeInfo.wc_matches,
              awayWcMatches: awayInfo.wc_matches,
              homeGoals:    homeInfo.goals_scored.toFixed(1),
              awayGoals:    awayInfo.goals_scored.toFixed(1),
              scenario,
              lang,
            }),
            signal: ctrl.signal,
          });

          if (!res.ok || !res.body) { setAiStatus("error"); return; }

          const reader  = res.body.getReader();
          const decoder = new TextDecoder();
          let   full    = "";

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            const chunk = decoder.decode(value, { stream: true });
            full += chunk;
            setAiText(full);
            setAiStatus("streaming");
          }
          setAiStatus("done");
        } catch (err) {
          if ((err as Error).name !== "AbortError") setAiStatus("error");
        }
      })();
    }, 350);

    return () => {
      clearTimeout(tid);
      abortRef.current?.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [home, away, lang]);

  // ── Early return AFTER all hooks ────────────────────────────────────────
  if (!homeInfo || !awayInfo || !staticData) return null;

  const { emoji, title, badge, intensity } = staticData;
  const isLoading     = aiStatus === "loading";
  const isStreaming   = aiStatus === "streaming";
  const displayText   = aiStatus === "error" ? staticData.text : (aiText || null);

  const accentColor = intensity === "critical" ? "#E5002D"
    : intensity === "moderate" ? "#C9981F"
    : "#30D158";
  const bgGrad = intensity === "critical"
    ? "linear-gradient(135deg, rgba(229,0,45,0.08) 0%, rgba(6,6,16,0) 60%)"
    : intensity === "moderate"
    ? "linear-gradient(135deg, rgba(201,152,31,0.08) 0%, rgba(6,6,16,0) 60%)"
    : "linear-gradient(135deg, rgba(48,209,88,0.07) 0%, rgba(6,6,16,0) 60%)";

  return (
    <motion.div
      variants={fadeUp}
      key={home + away}
      className="rounded-2xl px-5 py-4 relative overflow-hidden"
      style={{
        background: "var(--color-arena-card)",
        border: `1px solid ${accentColor}28`,
        boxShadow: `0 0 0 1px ${accentColor}10, inset 0 1px 0 rgba(255,255,255,0.03)`,
      }}
    >
      {/* Accent gradient bg */}
      <div style={{ position: "absolute", inset: 0, background: bgGrad, pointerEvents: "none" }} aria-hidden />

      {/* Header row */}
      <div className="flex items-center gap-3 mb-3 relative">
        <motion.span
          initial={{ scale: 0.6, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 300, damping: 18 }}
          style={{ fontSize: "1.6rem", lineHeight: 1, flexShrink: 0 }}
        >
          {emoji}
        </motion.span>
        <div className="flex-1 min-w-0 flex items-center gap-2 flex-wrap">
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.56rem", letterSpacing: "0.2em",
            color: accentColor, textTransform: "uppercase", fontWeight: 800,
          }}>{title}</span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.46rem", letterSpacing: "0.1em",
            padding: "0.12rem 0.45rem", borderRadius: 4,
            background: `${accentColor}14`, border: `1px solid ${accentColor}30`,
            color: accentColor, textTransform: "uppercase", flexShrink: 0,
          }}>{badge}</span>
        </div>
        {/* AI badge — pulsa mientras carga */}
        <motion.span
          animate={isLoading || isStreaming ? { opacity: [0.5, 1, 0.5] } : { opacity: 1 }}
          transition={isLoading || isStreaming ? { duration: 1.2, repeat: Infinity } : {}}
          style={{
            fontFamily: "var(--font-mono)", fontSize: "0.44rem", letterSpacing: "0.1em",
            padding: "0.1rem 0.4rem", borderRadius: 3,
            background: "rgba(201,152,31,0.08)", border: "1px solid rgba(201,152,31,0.18)",
            color: "var(--color-wc-gold)", textTransform: "uppercase", flexShrink: 0,
          }}
        >
          {isLoading ? "⚙ IA..." : isStreaming ? "⚙ IA ▍" : "⚙ Narrator AI"}
        </motion.span>
      </div>

      {/* Narrative text */}
      <p style={{ fontFamily: "var(--font-body)", fontSize: "0.84rem", lineHeight: 1.62, color: "var(--color-ink-secondary)", margin: "0 0 0.9rem", position: "relative", minHeight: "3.6rem" }}>
        {isLoading ? (
          /* Thinking dots mientras llega la primera palabra */
          <span className="flex items-center gap-2" style={{ color: "var(--color-ink-muted)", fontFamily: "var(--font-mono)", fontSize: "0.72rem" }}>
            <span>Analizando</span>
            {[0, 1, 2].map((i) => (
              <motion.span
                key={i}
                animate={{ opacity: [0.2, 1, 0.2] }}
                transition={{ duration: 1.0, repeat: Infinity, delay: i * 0.2 }}
                style={{ display: "inline-block", width: 5, height: 5, borderRadius: "50%", background: accentColor }}
              />
            ))}
          </span>
        ) : displayText ? (
          /* Texto streaming con cursor parpadeante o fallback estático */
          isStreaming ? (
            <span style={{ whiteSpace: "pre-wrap" }}>
              {displayText}
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                style={{ display: "inline-block", width: 2, height: "0.9em", background: accentColor, marginLeft: 2, verticalAlign: "text-bottom", borderRadius: 1 }}
              />
            </span>
          ) : (
            /* Texto final con animación palabra-por-palabra */
            <NarratorWords text={displayText} narrative={home + away + lang + aiStatus} />
          )
        ) : null}
      </p>

      {/* Stadium row */}
      {stadium && (
        <div className="flex items-center gap-2 relative mb-3"
          style={{ borderTop: "1px solid rgba(255,255,255,0.06)", paddingTop: "0.65rem" }}>
          <span style={{ fontSize: "0.9rem", lineHeight: 1 }}>🏟️</span>
          <div className="flex flex-col">
            <span style={{
              fontFamily: "var(--font-mono)", fontSize: "0.58rem", fontWeight: 700,
              color: "var(--color-ink-primary)", letterSpacing: "0.04em",
            }}>
              {stadium.name}
              <span style={{ marginLeft: "0.4rem", opacity: 0.55, fontWeight: 400 }}>
                · {stadium.city}
              </span>
            </span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--color-ink-muted)", letterSpacing: "0.06em", marginTop: "0.1rem" }}>
              {stadium.flag} {stadium.country} · {stadium.capacity.toLocaleString()} espectadores
            </span>
          </div>
        </div>
      )}

      {/* Probability tri-bar */}
      <div className="flex items-center gap-2 relative">
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", color: homeColor, minWidth: 28, textAlign: "right" }}>
          {Math.round(pred.home_win * 100)}%
        </span>
        <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ background: "rgba(255,255,255,0.05)" }}>
          <div style={{
            height: "100%",
            background: `linear-gradient(90deg,
              ${homeColor} 0%,
              ${homeColor} ${pred.home_win * 100}%,
              rgba(100,100,130,0.6) ${pred.home_win * 100}%,
              rgba(100,100,130,0.6) ${(pred.home_win + pred.draw) * 100}%,
              ${awayColor} ${(pred.home_win + pred.draw) * 100}%,
              ${awayColor} 100%)`,
          }} />
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", color: awayColor, minWidth: 28 }}>
          {Math.round(pred.away_win * 100)}%
        </span>
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   AGENT ANALYSIS ENGINE
══════════════════════════════════════════════════════ */
type Lang3 = "es" | "en" | "pt";
type Verdict = "home" | "away" | "draw";

interface AgentResult {
  id: string;
  icon: string;
  name: string;
  domain: Record<Lang3, string>;
  type: "llm" | "det";
  verdict: Verdict;
  confidence: number;   // 0–1
  delta: number;        // –0.12 to +0.12 (positive = favors home)
  analysis: Record<Lang3, string>;
  keyMetric: string;
}

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)); }
function pct(v: number, dec = 1) { return `${(v * 100).toFixed(dec)}%`; }

function computeAgents(
  home: string,
  away: string,
  hi: TeamInfo | undefined,
  ai: TeamInfo | undefined,
  pred: Prediction
): AgentResult[] {
  if (!hi || !ai) return [];

  const eloDiff   = hi.elo - ai.elo;            // positive = home better
  const rankDiff  = ai.rank - hi.rank;          // positive = home better ranked
  const wcExpDiff = hi.wc_matches - ai.wc_matches;
  const homeNet   = hi.goals_scored - hi.goals_conceded;
  const awayNet   = ai.goals_scored - ai.goals_conceded;
  const netDiff   = homeNet - awayNet;

  function verdictFrom(val: number, lo = 40, hi2 = 60): Verdict {
    if (val > hi2) return "home";
    if (val < lo)  return "away";
    return "draw";
  }

  /* ── 1. IntMatch — Tactical ── */
  const intmatchScore = 50 + clamp(eloDiff / 14, -18, 18)
    + clamp((hi.goals_scored - ai.goals_scored) * 4, -7, 7)
    + clamp((ai.goals_conceded - hi.goals_conceded) * 4, -7, 7);
  const intmatchVerdict: Verdict = verdictFrom(intmatchScore, 42, 58);
  const intmatchConf = 0.44 + clamp(Math.abs(eloDiff) / 800, 0, 0.40);
  const intmatchDelta = clamp(eloDiff / 1600 + netDiff * 0.025, -0.10, 0.10);
  const favored = intmatchVerdict === "home" ? home : intmatchVerdict === "away" ? away : null;

  const intmatchAnalysis: Record<Lang3, string> = {
    es: `${home} ${eloDiff > 0 ? "supera" : "está por debajo de"} a ${away} en ELO por ${Math.abs(eloDiff).toFixed(0)} pts (${hi.elo.toFixed(0)} vs ${ai.elo.toFixed(0)}). El balance goleador reciente (${hi.goals_scored.toFixed(2)} anotados / ${hi.goals_conceded.toFixed(2)} recibidos vs ${ai.goals_scored.toFixed(2)} / ${ai.goals_conceded.toFixed(2)}) ${favored ? `apoya a ${favored} como favorito táctico` : "indica un partido equilibrado"}.`,
    en: `${home} ${eloDiff > 0 ? "edges" : "trails"} ${away} by ${Math.abs(eloDiff).toFixed(0)} ELO pts (${hi.elo.toFixed(0)} vs ${ai.elo.toFixed(0)}). Recent goal balance (${hi.goals_scored.toFixed(2)} scored / ${hi.goals_conceded.toFixed(2)} conceded vs ${ai.goals_scored.toFixed(2)} / ${ai.goals_conceded.toFixed(2)}) ${favored ? `backs ${favored} as tactical favorite` : "suggests a balanced contest"}.`,
    pt: `${home} ${eloDiff > 0 ? "supera" : "está abaixo de"} ${away} em ${Math.abs(eloDiff).toFixed(0)} pts de ELO (${hi.elo.toFixed(0)} vs ${ai.elo.toFixed(0)}). O balanço de gols recente (${hi.goals_scored.toFixed(2)} marcados / ${hi.goals_conceded.toFixed(2)} sofridos vs ${ai.goals_scored.toFixed(2)} / ${ai.goals_conceded.toFixed(2)}) ${favored ? `favorece ${favored} taticamente` : "aponta para um jogo equilibrado"}.`,
  };

  /* ── 2. Roster — Squad & Experience ── */
  const rosterScore = 50 + clamp(wcExpDiff * 1.2, -18, 18) + clamp(netDiff * 8, -10, 10);
  const rosterVerdict: Verdict = verdictFrom(rosterScore, 42, 58);
  const rosterConf = 0.40 + clamp(Math.abs(wcExpDiff) * 0.018 + Math.abs(netDiff) * 0.06, 0, 0.40);
  const rosterDelta = clamp(wcExpDiff * 0.0035 + netDiff * 0.022, -0.09, 0.09);
  const rExp = rosterVerdict === "home" ? home : rosterVerdict === "away" ? away : null;

  const rosterAnalysis: Record<Lang3, string> = {
    es: `Diferencia de experiencia mundialista: ${home} acumula ${hi.wc_matches} partidos en Mundiales vs ${ai.wc_matches} de ${away} (Δ${wcExpDiff > 0 ? "+" : ""}${wcExpDiff}). ${rExp ? `${rExp} tiene ventaja psicológica en momentos de presión.` : "Ambos planteles tienen experiencia similar."} Promedio neto de goles: ${homeNet.toFixed(2)} vs ${awayNet.toFixed(2)}.`,
    en: `World Cup experience gap: ${home} has ${hi.wc_matches} WC matches vs ${away}'s ${ai.wc_matches} (Δ${wcExpDiff > 0 ? "+" : ""}${wcExpDiff}). ${rExp ? `${rExp} holds a psychological edge under pressure.` : "Both squads carry similar tournament experience."} Net goal averages: ${homeNet.toFixed(2)} vs ${awayNet.toFixed(2)}.`,
    pt: `Experiência mundialista: ${home} tem ${hi.wc_matches} jogos na Copa vs ${ai.wc_matches} de ${away} (Δ${wcExpDiff > 0 ? "+" : ""}${wcExpDiff}). ${rExp ? `${rExp} tem vantagem psicológica sob pressão.` : "Ambos os elencos têm experiência similar."} Média líquida de gols: ${homeNet.toFixed(2)} vs ${awayNet.toFixed(2)}.`,
  };

  /* ── 3. Media — Sentiment ── */
  const mediaScore = 50 + clamp(rankDiff * 0.9, -16, 16) + clamp((hi.goals_scored - ai.goals_scored) * 5, -8, 8);
  const mediaVerdict: Verdict = verdictFrom(mediaScore, 43, 57);
  const mediaConf = 0.36 + clamp(Math.abs(rankDiff) * 0.013, 0, 0.32);
  const mediaDelta = clamp(rankDiff * 0.0018 + (hi.goals_scored - ai.goals_scored) * 0.015, -0.07, 0.07);
  const mFav = mediaVerdict === "home" ? home : mediaVerdict === "away" ? away : null;
  const pressure = hi.rank <= 12 ? (ai.rank <= 12 ? "ambos" : home) : (ai.rank <= 12 ? away : null);

  const mediaAnalysis: Record<Lang3, string> = {
    es: `${home} ocupa el ranking ${hi.rank} vs ${away} en el ${ai.rank}. ${pressure ? `${pressure} lleva la narrativa mediática dominante, lo que genera tanto confianza como expectativa de resultado.` : "Ambos equipos tienen exposición mediática moderada."} ${mFav ? `El ciclo de prensa favorece a ${mFav} (${hi.goals_scored.toFixed(2)} goles anotados/partido vs ${ai.goals_scored.toFixed(2)}).` : "El sentimiento mediático apunta a un empate técnico."}`,
    en: `${home} is ranked #${hi.rank} vs ${away} at #${ai.rank}. ${pressure ? `${pressure} carries the dominant media narrative, generating both confidence and expectation.` : "Both teams carry moderate media exposure."} ${mFav ? `Press sentiment favors ${mFav} (${hi.goals_scored.toFixed(2)} goals/match vs ${ai.goals_scored.toFixed(2)}).` : "Media sentiment points to a technical draw."}`,
    pt: `${home} é o ${hi.rank}º no ranking vs ${away} em ${ai.rank}º. ${pressure ? `${pressure} domina a narrativa da imprensa, gerando confiança e expectativa de resultado.` : "Ambos os times têm exposição midiática moderada."} ${mFav ? `O sentimento da mídia favorece ${mFav} (${hi.goals_scored.toFixed(2)} gols/jogo vs ${ai.goals_scored.toFixed(2)}).` : "O sentimento midiático aponta para empate técnico."}`,
  };

  /* ── 4. Travel — Fatigue & Altitude ── */
  const confMap: Record<string, number> = {
    CONCACAF: 5, CONMEBOL: 3, UEFA: -2, CAF: -3, AFC: -4, OFC: -5,
  };
  const homeAdv = confMap[hi.confederation] ?? 0;
  const awayAdv = confMap[ai.confederation] ?? 0;
  const travelAdv = homeAdv - awayAdv;
  const travelScore = 50 + clamp(travelAdv * 2.8, -18, 18);
  const travelVerdict: Verdict = verdictFrom(travelScore, 44, 56);
  const travelConf = 0.38 + clamp(Math.abs(travelAdv) * 0.03, 0, 0.28);
  const travelDelta = clamp(travelAdv * 0.007, -0.08, 0.08);
  const tFav = travelVerdict === "home" ? home : travelVerdict === "away" ? away : null;

  const travelAnalysis: Record<Lang3, string> = {
    es: `${home} (${hi.confederation}) vs ${away} (${ai.confederation}): coeficiente logístico ${homeAdv > 0 ? "+" : ""}${homeAdv} vs ${awayAdv > 0 ? "+" : ""}${awayAdv}. ${hi.confederation === "CONCACAF" || hi.confederation === "CONMEBOL" ? `${home} juega en su continente, con ventaja de aclimatación y familiaridad con condiciones climáticas.` : hi.confederation === "UEFA" ? `${home} viaja desde Europa; posible impacto de jet-lag y adaptación a altitud/clima.` : "Factor logístico neutro."} ${tFav ? `Proyección: ventaja de ${tFav}.` : "Sin ventaja logística clara."}`,
    en: `${home} (${hi.confederation}) vs ${away} (${ai.confederation}): logistics score ${homeAdv > 0 ? "+" : ""}${homeAdv} vs ${awayAdv > 0 ? "+" : ""}${awayAdv}. ${hi.confederation === "CONCACAF" || hi.confederation === "CONMEBOL" ? `${home} plays on home continent with acclimatization and climate familiarity advantage.` : hi.confederation === "UEFA" ? `${home} travels from Europe; jet-lag and altitude adaptation may factor in.` : "Logistics factor is neutral."} ${tFav ? `Projection: ${tFav} gains edge.` : "No clear logistics advantage."}`,
    pt: `${home} (${hi.confederation}) vs ${away} (${ai.confederation}): coeficiente logístico ${homeAdv > 0 ? "+" : ""}${homeAdv} vs ${awayAdv > 0 ? "+" : ""}${awayAdv}. ${hi.confederation === "CONCACAF" || hi.confederation === "CONMEBOL" ? `${home} joga no continente natal com vantagem de aclimatação e familiaridade com o clima.` : hi.confederation === "UEFA" ? `${home} viaja da Europa; jet-lag e adaptação à altitude podem ser fatores.` : "Fator logístico neutro."} ${tFav ? `Projeção: vantagem para ${tFav}.` : "Sem vantagem logística clara."}`,
  };

  /* ── 5. FinOps — Market Odds ── */
  const modelFav = pred.home_win >= pred.draw && pred.home_win >= pred.away_win ? "home"
    : pred.away_win >= pred.draw ? "away" : "draw";
  const eloProb = 1 / (1 + Math.pow(10, -eloDiff / 400));
  const marketDelta = clamp((pred.home_win - eloProb) * 0.18, -0.08, 0.08);
  const finopsVerdict: Verdict = marketDelta > 0.015 ? "home" : marketDelta < -0.015 ? "away" : modelFav;
  const finopsConf = Math.max(pred.home_win, pred.draw, pred.away_win) * 0.88;
  const finopsDelta = marketDelta;
  const homeOdds = (1 / pred.home_win).toFixed(2);
  const drawOdds = (1 / pred.draw).toFixed(2);
  const awayOdds = (1 / pred.away_win).toFixed(2);

  const finopsAnalysis: Record<Lang3, string> = {
    es: `Cuotas implícitas del modelo: ${home} ${homeOdds} · Empate ${drawOdds} · ${away} ${awayOdds}. La probabilidad ELO base proyecta ${pct(eloProb)} para ${home}; el modelo ajustado la sitúa en ${pct(pred.home_win)}. ${Math.abs(pred.home_win - eloProb) > 0.04 ? `Divergencia de ${pct(Math.abs(pred.home_win - eloProb))} entre ELO y modelo ML — señal de sobreajuste o factor contextual capturado.` : "Modelo y ELO convergen — señal de mercado limpio."}`,
    en: `Model-implied odds: ${home} ${homeOdds} · Draw ${drawOdds} · ${away} ${awayOdds}. Base ELO probability for ${home}: ${pct(eloProb)}; adjusted model: ${pct(pred.home_win)}. ${Math.abs(pred.home_win - eloProb) > 0.04 ? `${pct(Math.abs(pred.home_win - eloProb))} divergence between ELO and ML model — indicates captured contextual factor.` : "Model and ELO converge — clean market signal."}`,
    pt: `Odds implícitas do modelo: ${home} ${homeOdds} · Empate ${drawOdds} · ${away} ${awayOdds}. Probabilidade ELO base para ${home}: ${pct(eloProb)}; modelo ajustado: ${pct(pred.home_win)}. ${Math.abs(pred.home_win - eloProb) > 0.04 ? `Divergência de ${pct(Math.abs(pred.home_win - eloProb))} entre ELO e ML — indica fator contextual capturado.` : "Modelo e ELO convergem — sinal de mercado limpo."}`,
  };

  /* ── 6. FIFA-Regs — Venue & Regulations ── */
  const fifaScore = 50 + clamp(wcExpDiff * 1.0, -14, 14) + clamp(rankDiff * 0.5, -8, 8);
  const fifaVerdict: Verdict = verdictFrom(fifaScore, 44, 56);
  const fifaConf = 0.40 + clamp(Math.abs(wcExpDiff) * 0.02, 0, 0.28);
  const fifaDelta = clamp(wcExpDiff * 0.003 + (hi.rank < 16 ? 0.02 : 0), -0.08, 0.08);
  const fFav = fifaVerdict === "home" ? home : fifaVerdict === "away" ? away : null;
  const elite = hi.rank <= 8 || ai.rank <= 8;

  const fifaAnalysis: Record<Lang3, string> = {
    es: `Experiencia en reglamento de torneos (partidos WC): ${home} ${hi.wc_matches} vs ${away} ${ai.wc_matches}. ${elite ? `Con equipos de élite (top-8 mundial), el conocimiento de dinámica knockout es determinante.` : "Ambos equipos tienen experiencia comparable en torneos oficiales FIFA."} ${fFav ? `Ventaja reglamentaria y de sede proyecta a ${fFav} (ranking #${fFav === home ? hi.rank : ai.rank}).` : "Sin ventaja regulatoria significativa entre equipos."}`,
    en: `Tournament regulation experience (WC matches): ${home} ${hi.wc_matches} vs ${away} ${ai.wc_matches}. ${elite ? `With elite teams (top-8 ranked), knockout dynamics knowledge is decisive.` : "Both sides carry comparable experience in official FIFA competition."} ${fFav ? `Venue and regulatory edge projects ${fFav} (rank #${fFav === home ? hi.rank : ai.rank}).` : "No significant regulatory advantage between these teams."}`,
    pt: `Experiência em regulamento de torneio (jogos WC): ${home} ${hi.wc_matches} vs ${away} ${ai.wc_matches}. ${elite ? `Com equipes de elite (top-8 mundial), o conhecimento da dinâmica do knockout é determinante.` : "Ambas as equipes têm experiência comparável em competições FIFA oficiais."} ${fFav ? `Vantagem de sede e regulatória projeta ${fFav} (ranking #${fFav === home ? hi.rank : ai.rank}).` : "Sem vantagem regulatória significativa."}`,
  };

  return [
    {
      id: "intmatch", icon: "🎯", name: "IntMatch-Analytics-Pro",
      domain: { es: "Análisis Táctico", en: "Tactical Analysis", pt: "Análise Tática" },
      type: "llm",
      verdict: intmatchVerdict, confidence: intmatchConf, delta: intmatchDelta,
      analysis: intmatchAnalysis,
      keyMetric: `ELO Δ${eloDiff > 0 ? "+" : ""}${eloDiff.toFixed(0)}`,
    },
    {
      id: "roster", icon: "🩺", name: "Roster-Data-Scout",
      domain: { es: "Plantel & Experiencia", en: "Squad & Experience", pt: "Elenco & Experiência" },
      type: "llm",
      verdict: rosterVerdict, confidence: rosterConf, delta: rosterDelta,
      analysis: rosterAnalysis,
      keyMetric: `WC Δ${wcExpDiff > 0 ? "+" : ""}${wcExpDiff} partidos`,
    },
    {
      id: "media", icon: "📰", name: "Media-Sentiment-Parser",
      domain: { es: "Prensa & Moral", en: "Press & Morale", pt: "Imprensa & Moral" },
      type: "llm",
      verdict: mediaVerdict, confidence: mediaConf, delta: mediaDelta,
      analysis: mediaAnalysis,
      keyMetric: `Rank #${hi.rank} vs #${ai.rank}`,
    },
    {
      id: "travel", icon: "✈️", name: "Travel-Logistics-Quant",
      domain: { es: "Fatiga & Altitud", en: "Fatigue & Altitude", pt: "Fadiga & Altitude" },
      type: "llm",
      verdict: travelVerdict, confidence: travelConf, delta: travelDelta,
      analysis: travelAnalysis,
      keyMetric: `${hi.confederation} vs ${ai.confederation}`,
    },
    {
      id: "finops", icon: "📊", name: "FinOps-Bookmaker-Alpha",
      domain: { es: "Cuotas de Mercado", en: "Market Odds", pt: "Odds de Mercado" },
      type: "det",
      verdict: finopsVerdict, confidence: finopsConf, delta: finopsDelta,
      analysis: finopsAnalysis,
      keyMetric: `${pct(pred.home_win)} / ${pct(pred.draw)} / ${pct(pred.away_win)}`,
    },
    {
      id: "fifareg", icon: "📐", name: "FIFA-Regs-Strategist",
      domain: { es: "Sede & Reglamento", en: "Venue & Regulations", pt: "Sede & Regulamento" },
      type: "det",
      verdict: fifaVerdict, confidence: fifaConf, delta: fifaDelta,
      analysis: fifaAnalysis,
      keyMetric: `${hi.wc_matches} vs ${ai.wc_matches} WC matches`,
    },
  ];
}

/* ══════════════════════════════════════════════════════
   AGENT ANALYSIS PANEL
══════════════════════════════════════════════════════ */
function AgentAnalysisPanel({
  home, away, homeInfo, awayInfo, pred, homeColor, awayColor, T,
}: {
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  pred: Prediction; homeColor: string; awayColor: string;
  T: ReturnType<typeof import("@/lib/i18n").useLang>;
}) {
  const lang = useContext(LangContext);
  const langBase = toLangBase(lang);

  const agents = useMemo(
    () => computeAgents(home, away, homeInfo, awayInfo, pred),
    [home, away, homeInfo, awayInfo, pred]
  );

  if (agents.length === 0) return null;

  const homeCount = agents.filter((a) => a.verdict === "home").length;
  const awayCount = agents.filter((a) => a.verdict === "away").length;
  const drawCount = agents.filter((a) => a.verdict === "draw").length;
  const totalDelta = clamp(agents.reduce((s, a) => s + a.delta, 0), -0.12, 0.12);
  const consensusVerdict: Verdict = homeCount > awayCount && homeCount > drawCount ? "home"
    : awayCount > homeCount && awayCount > drawCount ? "away" : "draw";
  const consensusTeam = consensusVerdict === "home" ? home : consensusVerdict === "away" ? away : null;
  const adjustedHome = clamp(pred.home_win + totalDelta, 0.05, 0.92);
  const adjustedAway = clamp(pred.away_win - totalDelta * 0.6, 0.05, 0.92);
  const adjustedDraw = clamp(1 - adjustedHome - adjustedAway, 0.04, 0.55);

  return (
    <motion.div
      variants={fadeUp} initial="hidden" animate="visible" exit="exit"
      className="rounded-2xl overflow-hidden"
      style={{
        background: "var(--color-arena-card)",
        border: "1px solid rgba(255,255,255,0.065)",
        boxShadow: "0 2px 8px rgba(0,0,0,0.4)",
      }}
    >
      {/* ── Panel header ── */}
      <div
        className="flex items-center justify-between px-5 py-4"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.055)" }}
      >
        <div className="flex items-center gap-3">
          <div style={{ width: 3, height: 20, background: "linear-gradient(180deg, var(--color-wc-gold) 0%, var(--color-wc-red) 100%)", borderRadius: 2 }} />
          <div>
            <p style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "0.88rem", color: "var(--color-ink-primary)", margin: 0 }}>
              {T.agentsTitle}
            </p>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", letterSpacing: "0.12em", color: "var(--color-ink-muted)", textTransform: "uppercase", margin: 0 }}>
              {T.agentsBadge}
            </p>
          </div>
        </div>
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-xl"
          style={{ background: "var(--color-arena-elevated)", border: "1px solid rgba(255,255,255,0.06)" }}
        >
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.62rem", color: "var(--color-ink-secondary)" }}>Δ neto</span>
          <span style={{
            fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "0.76rem",
            color: totalDelta > 0.01 ? "#30D158" : totalDelta < -0.01 ? "#FF453A" : "var(--color-ink-muted)",
          }}>
            {totalDelta > 0 ? "+" : ""}{(totalDelta * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* ── Consensus summary ── */}
      <div
        className="mx-5 mt-4 mb-3 rounded-xl p-4"
        style={{
          background: "var(--color-arena-elevated)",
          border: "1px solid rgba(255,255,255,0.055)",
        }}
      >
        <div className="flex items-center justify-between gap-4 flex-wrap mb-3">
          <div>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--color-ink-muted)", margin: 0 }}>
              Consenso · {agents.length} agentes
            </p>
            <p style={{ fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "1.05rem", color: "var(--color-ink-primary)", margin: "0.2rem 0 0" }}>
              {consensusTeam
                ? `${consensusVerdict === "home" ? homeInfo?.flag : awayInfo?.flag} ${consensusTeam}`
                : `${homeInfo?.flag} Empate / Draw`}
            </p>
          </div>
          <div className="flex gap-2">
            {[
              { label: `${homeInfo?.flag ?? ""} ${home}`, count: homeCount, color: homeColor },
              { label: "Draw", count: drawCount, color: "#666688" },
              { label: `${awayInfo?.flag ?? ""} ${away}`, count: awayCount, color: awayColor },
            ].map((item) => (
              <div key={item.label} className="flex flex-col items-center gap-0.5">
                <span style={{
                  fontFamily: "var(--font-display)", fontSize: "1.5rem", lineHeight: 1,
                  color: item.count > 0 ? item.color : "var(--color-ink-muted)",
                }}>{item.count}</span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.48rem", color: "var(--color-ink-muted)", letterSpacing: "0.06em", whiteSpace: "nowrap" }}>{item.label}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Adjusted probabilities bar */}
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--color-ink-muted)", width: 16, textAlign: "right" }}>H</span>
            <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
              <motion.div
                className="h-full rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${adjustedHome * 100}%` }}
                transition={{ duration: 0.7, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
                style={{ background: homeColor }}
              />
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--color-ink-primary)", minWidth: 32, textAlign: "right" }}>{pct(adjustedHome)}</span>
          </div>
          <div className="flex items-center gap-2">
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--color-ink-muted)", width: 16, textAlign: "right" }}>D</span>
            <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
              <motion.div
                className="h-full rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${adjustedDraw * 100}%` }}
                transition={{ duration: 0.7, delay: 0.3, ease: [0.16, 1, 0.3, 1] }}
                style={{ background: "#666688" }}
              />
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--color-ink-primary)", minWidth: 32, textAlign: "right" }}>{pct(adjustedDraw)}</span>
          </div>
          <div className="flex items-center gap-2">
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", color: "var(--color-ink-muted)", width: 16, textAlign: "right" }}>A</span>
            <div className="flex-1 h-1.5 rounded-full" style={{ background: "rgba(255,255,255,0.07)" }}>
              <motion.div
                className="h-full rounded-full"
                initial={{ width: 0 }}
                animate={{ width: `${adjustedAway * 100}%` }}
                transition={{ duration: 0.7, delay: 0.4, ease: [0.16, 1, 0.3, 1] }}
                style={{ background: awayColor }}
              />
            </div>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.55rem", color: "var(--color-ink-primary)", minWidth: 32, textAlign: "right" }}>{pct(adjustedAway)}</span>
          </div>
        </div>
      </div>

      {/* ── Agent cards ── */}
      <div className="px-5 pb-5 space-y-3">
        {agents.map((agent, i) => (
          <motion.div
            key={agent.id}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.06 + 0.1, duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
          >
            <AgentAnalysisCard
              agent={agent}
              lang={langBase}
              home={home}
              away={away}
              homeInfo={homeInfo}
              awayInfo={awayInfo}
              homeColor={homeColor}
              awayColor={awayColor}
              T={T}
            />
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

function AgentAnalysisCard({
  agent, lang, home, away, homeInfo, awayInfo, homeColor, awayColor, T,
}: {
  agent: AgentResult;
  lang: Lang3;
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  homeColor: string; awayColor: string;
  T: ReturnType<typeof import("@/lib/i18n").useLang>;
}) {
  const isLlm = agent.type === "llm";
  const verdictColor = agent.verdict === "home" ? homeColor : agent.verdict === "away" ? awayColor : "#666688";
  const verdictTeam  = agent.verdict === "home" ? home : agent.verdict === "away" ? away : null;
  const verdictFlag  = agent.verdict === "home" ? homeInfo?.flag : agent.verdict === "away" ? awayInfo?.flag : null;
  const confPct      = Math.round(agent.confidence * 100);
  const signalStrength = agent.confidence > 0.68 ? "strong" : agent.confidence > 0.50 ? "moderate" : "weak";

  return (
    <div
      className="rounded-xl overflow-hidden"
      style={{
        background: "var(--color-arena-elevated)",
        border: `1px solid ${isLlm ? "rgba(201,152,31,0.12)" : "rgba(48,209,88,0.10)"}`,
      }}
    >
      {/* Card header */}
      <div
        className="flex items-center justify-between gap-3 px-4 py-2.5"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.05)" }}
      >
        <div className="flex items-center gap-2.5 min-w-0">
          <span className="text-lg leading-none shrink-0">{agent.icon}</span>
          <div className="min-w-0">
            <p style={{ fontFamily: "var(--font-body)", fontWeight: 600, fontSize: "0.78rem", color: "var(--color-ink-primary)", margin: 0, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
              {agent.domain[lang]}
            </p>
            <p style={{ fontFamily: "var(--font-mono)", fontSize: "0.48rem", letterSpacing: "0.1em", color: "var(--color-ink-muted)", textTransform: "uppercase", margin: 0 }}>
              {agent.name}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Type badge */}
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.5rem", letterSpacing: "0.08em",
            padding: "0.15rem 0.4rem", borderRadius: 4,
            background: isLlm ? "rgba(201,152,31,0.10)" : "rgba(48,209,88,0.08)",
            color: isLlm ? "var(--color-wc-gold)" : "#30D158",
            border: `1px solid ${isLlm ? "rgba(201,152,31,0.25)" : "rgba(48,209,88,0.2)"}`,
          }}>
            {isLlm ? T.agentLlm : T.agentDet}
          </span>
          {/* Delta */}
          <span style={{
            fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "0.65rem",
            color: agent.delta > 0.01 ? "#30D158" : agent.delta < -0.01 ? "#FF453A" : "var(--color-ink-muted)",
          }}>
            {agent.delta > 0 ? "+" : ""}{(agent.delta * 100).toFixed(1)}%
          </span>
        </div>
      </div>

      {/* Analysis text */}
      <div className="px-4 py-3">
        <p style={{ fontFamily: "var(--font-body)", fontSize: "0.78rem", lineHeight: 1.6, color: "var(--color-ink-secondary)", margin: 0 }}>
          {agent.analysis[lang]}
        </p>
      </div>

      {/* Verdict + confidence footer */}
      <div
        className="flex items-center justify-between gap-4 px-4 py-2.5"
        style={{ borderTop: "1px solid rgba(255,255,255,0.04)" }}
      >
        {/* Verdict */}
        <div className="flex items-center gap-2">
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", letterSpacing: "0.1em", textTransform: "uppercase", color: "var(--color-ink-muted)" }}>
            Veredicto
          </span>
          <span style={{
            fontFamily: "var(--font-body)", fontWeight: 700, fontSize: "0.78rem",
            color: verdictColor,
          }}>
            {verdictFlag} {verdictTeam ?? (lang === "en" ? "Draw" : "Empate")}
          </span>
        </div>

        {/* Confidence dots + % */}
        <div className="flex items-center gap-2">
          <div className="flex gap-0.5">
            {[0, 1, 2, 3, 4].map((i) => {
              const filled = i < Math.round(agent.confidence * 5);
              return (
                <div
                  key={i}
                  className="rounded-full"
                  style={{
                    width: 5, height: 5,
                    background: filled ? verdictColor : "rgba(255,255,255,0.1)",
                    transition: "background 0.2s",
                  }}
                />
              );
            })}
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: "0.58rem", color: "var(--color-ink-secondary)" }}>
            {confPct}%
          </span>
          <span style={{
            fontFamily: "var(--font-mono)", fontSize: "0.46rem", letterSpacing: "0.08em",
            textTransform: "uppercase", padding: "0.1rem 0.3rem", borderRadius: 3,
            background: signalStrength === "strong" ? "rgba(48,209,88,0.1)"
              : signalStrength === "moderate" ? "rgba(201,152,31,0.1)"
              : "rgba(255,255,255,0.05)",
            color: signalStrength === "strong" ? "#30D158"
              : signalStrength === "moderate" ? "var(--color-wc-gold)"
              : "var(--color-ink-muted)",
            border: `1px solid ${signalStrength === "strong" ? "rgba(48,209,88,0.2)"
              : signalStrength === "moderate" ? "rgba(201,152,31,0.2)"
              : "rgba(255,255,255,0.06)"}`,
          }}>
            {signalStrength === "strong" ? (lang === "en" ? "Strong" : "Fuerte")
              : signalStrength === "moderate" ? (lang === "en" ? "Moderate" : "Moderada")
              : (lang === "en" ? "Weak" : "Débil")}
          </span>
        </div>
      </div>
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   STADIUM OVERLAY — campo de fútbol en miniatura
══════════════════════════════════════════════════════ */
function StadiumOverlay({ color }: { color: string }) {
  return (
    <svg
      aria-hidden
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%", pointerEvents: "none" }}
      viewBox="0 0 200 200"
      xmlns="http://www.w3.org/2000/svg"
      preserveAspectRatio="xMidYMid slice"
    >
      {/* Stadium floodlight cone from top */}
      <defs>
        <radialGradient id={`light-${color.replace("#","")}`} cx="50%" cy="0%" r="80%">
          <stop offset="0%" stopColor="white" stopOpacity="0.09"/>
          <stop offset="100%" stopColor="white" stopOpacity="0"/>
        </radialGradient>
      </defs>
      <rect width="200" height="200" fill={`url(#light-${color.replace("#","")})`}/>
      {/* Pitch border */}
      <rect x="12" y="18" width="176" height="164" fill="none" stroke="white" strokeWidth="0.8" opacity="0.07"/>
      {/* Center circle */}
      <circle cx="100" cy="100" r="36" fill="none" stroke="white" strokeWidth="0.8" opacity="0.08"/>
      {/* Center spot */}
      <circle cx="100" cy="100" r="2.5" fill="white" opacity="0.07"/>
      {/* Halfway line */}
      <line x1="12" y1="100" x2="188" y2="100" stroke="white" strokeWidth="0.7" opacity="0.06"/>
      {/* Penalty area top */}
      <rect x="62" y="18" width="76" height="38" fill="none" stroke="white" strokeWidth="0.7" opacity="0.06"/>
      {/* Penalty area bottom */}
      <rect x="62" y="144" width="76" height="38" fill="none" stroke="white" strokeWidth="0.7" opacity="0.06"/>
      {/* Goal area top */}
      <rect x="82" y="18" width="36" height="18" fill="none" stroke="white" strokeWidth="0.6" opacity="0.05"/>
      {/* Goal area bottom */}
      <rect x="82" y="164" width="36" height="18" fill="none" stroke="white" strokeWidth="0.6" opacity="0.05"/>
      {/* Penalty arcs */}
      <path d="M 76 56 A 24 24 0 0 1 124 56" fill="none" stroke="white" strokeWidth="0.7" opacity="0.05"/>
      <path d="M 76 144 A 24 24 0 0 0 124 144" fill="none" stroke="white" strokeWidth="0.7" opacity="0.05"/>
    </svg>
  );
}

/* ══════════════════════════════════════════════════════
   TEAM PICKER
══════════════════════════════════════════════════════ */
function TeamPicker({
  label, selected, teamList, info, onChange, side,
}: {
  label: string;
  selected: string;
  teamList: [string, TeamInfo][];
  info: TeamInfo | undefined;
  onChange: (v: string) => void;
  side: "left" | "right";
}) {
  const T               = useLang();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref             = useRef<HTMLDivElement>(null);
  const [color, color2] = getTeamDual(selected);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filtered = teamList.filter(([name]) =>
    name.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div ref={ref} className={`relative flex flex-col ${side === "left" ? "items-start" : "items-end"}`}>
      <span
        className="text-[10px] tracking-widest uppercase mb-2"
        style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
      >
        {label}
      </span>

      <motion.button
        onClick={() => setOpen(!open)}
        whileTap={{ scale: 0.96 }}
        className="w-full flex flex-col items-center gap-2 p-2 sm:p-4 rounded-2xl transition-all duration-300 focus:outline-none overflow-hidden relative"
        style={{
          background: `linear-gradient(155deg, ${color}1E 0%, ${color2}0C 50%, var(--color-arena-card) 100%)`,
          border: `1px solid ${color}30`,
          boxShadow: open ? `0 0 32px ${color}30, 0 0 0 1px ${color}28` : `0 0 0 1px ${color}12`,
        }}
      >
        {/* Stadium field overlay */}
        <StadiumOverlay color={color} />
        {/* Flag color top strip */}
        <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: 2, background: `linear-gradient(90deg, ${color}, ${color2})`, opacity: open ? 1 : 0.55, transition: "opacity 0.2s" }} />
        <motion.span
          key={selected}
          initial={{ scale: 0.5, opacity: 0, rotate: -12 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 260, damping: 20 }}
          className="text-4xl sm:text-5xl leading-none"
          style={{ filter: "drop-shadow(0 4px 12px rgba(0,0,0,0.5))" }}
        >
          {info?.flag ?? "🏳️"}
        </motion.span>

        <div className="text-center">
          <p
            className="text-base leading-tight font-bold tracking-wide"
            style={{ fontFamily: "var(--font-heading)", color: "var(--color-ink-primary)" }}
          >
            {selected}
          </p>
          {info && (
            <p
              className="text-[10px] tracking-widest mt-0.5"
              style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-secondary)" }}
            >
              ELO {info.elo.toFixed(0)} · #{info.rank}
            </p>
          )}
        </div>

        <motion.span
          animate={{ rotate: open ? 180 : 0 }}
          transition={{ duration: 0.18 }}
          className="text-[10px]"
          style={{ color: "var(--color-ink-muted)" }}
        >
          ▼
        </motion.span>
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scaleY: 0.88 }}
            animate={{ opacity: 1, y: 0, scaleY: 1 }}
            exit={{ opacity: 0, y: -8, scaleY: 0.88 }}
            transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
            style={{ transformOrigin: "top" }}
            className={`absolute top-full mt-2 z-50 w-56 sm:w-64 max-w-[calc(100vw-2rem)] rounded-2xl overflow-hidden ${
              side === "left" ? "left-0" : "right-0"
            }`}
          >
            <div
              style={{
                background: "var(--color-arena-deep)",
                border: "1px solid rgba(255,255,255,0.10)",
                boxShadow: "0 24px 60px rgba(0,0,0,0.82)",
              }}
            >
              <div className="p-3" style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
                <input
                  autoFocus
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={T.searchTeam}
                  className="w-full rounded-xl px-3 py-2 text-sm focus:outline-none transition-colors"
                  style={{
                    background: "var(--color-arena-elevated)",
                    border: "1px solid rgba(255,255,255,0.07)",
                    color: "var(--color-ink-primary)",
                    fontFamily: "var(--font-body)",
                  }}
                />
              </div>

              <div className="max-h-60 overflow-y-auto">
                {filtered.length === 0 ? (
                  <p className="text-center text-sm py-6" style={{ color: "var(--color-ink-muted)" }}>
                    {T.noResults}
                  </p>
                ) : (
                  filtered.map(([name, t]) => {
                    const tc = getTeamColor(name);
                    return (
                      <motion.button
                        key={name}
                        whileHover={{ backgroundColor: "rgba(255,255,255,0.038)" }}
                        onClick={() => { onChange(name); setOpen(false); setSearch(""); }}
                        className="w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors"
                        style={{ backgroundColor: name === selected ? "rgba(255,255,255,0.04)" : "transparent" }}
                      >
                        <span className="text-2xl shrink-0">{t.flag}</span>
                        <div className="flex-1 min-w-0">
                          <p
                            className="text-sm truncate"
                            style={{ color: "var(--color-ink-primary)", fontFamily: "var(--font-body)" }}
                          >
                            {name}
                          </p>
                          <p
                            className="text-[10px]"
                            style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
                          >
                            {t.confederation} · {T.group} {t.group}
                          </p>
                        </div>
                        <span
                          className="text-[10px] px-1.5 py-0.5 rounded-md shrink-0"
                          style={{
                            fontFamily: "var(--font-mono)",
                            background: `${tc}18`,
                            color: tc,
                            border: `1px solid ${tc}28`,
                          }}
                        >
                          {t.elo.toFixed(0)}
                        </span>
                      </motion.button>
                    );
                  })
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/* ══════════════════════════════════════════════════════
   ESTADOS DE LA ZONA DE RESULTADOS
══════════════════════════════════════════════════════ */
function IdleHint() {
  const T = useLang();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex flex-col items-center justify-center gap-2 py-5"
    >
      <span className="text-3xl">⚽</span>
      <p className="text-sm text-center" style={{ fontFamily: "var(--font-body)", color: "var(--color-ink-muted)" }}>
        {T.selectIdle}
      </p>
    </motion.div>
  );
}

function ScannerLoader({ homeFlag, awayFlag }: { homeFlag?: string; awayFlag?: string }) {
  const T = useLang();
  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="flex flex-col gap-4">
      <div
        className="flex items-center justify-center gap-4 text-lg tracking-wider"
        style={{ fontFamily: "var(--font-heading)", fontWeight: 700, color: "var(--color-ink-secondary)" }}
      >
        <span>{homeFlag}</span>
        <motion.span
          animate={{ opacity: [1, 0.2, 1] }}
          transition={{ duration: 0.9, repeat: Infinity }}
          style={{ color: "var(--color-wc-gold)" }}
        >
          ···
        </motion.span>
        <span>{awayFlag}</span>
      </div>

      <div
        className="relative h-12 rounded-xl overflow-hidden"
        style={{ background: "var(--color-arena-elevated)", border: "1px solid rgba(255,255,255,0.05)" }}
      >
        <motion.div
          className="absolute left-0 right-0 h-px"
          style={{ background: "linear-gradient(90deg, transparent, rgba(212,168,67,0.85), transparent)" }}
          animate={{ y: [0, 46] }}
          transition={{ duration: 1.6, repeat: Infinity, ease: "linear" }}
        />
        <div className="flex items-center justify-center h-full">
          <span className="text-[10px] tracking-widest uppercase" style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}>
            {T.scannerText}
          </span>
        </div>
      </div>

      <div className="space-y-2.5">
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex items-center gap-3">
            <div className="w-20 h-4 rounded shimmer-skeleton" />
            <div className="flex-1 h-9 rounded-xl shimmer-skeleton" />
            <div className="w-10 h-5 rounded shimmer-skeleton" />
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function ResultsZone({
  pred, home, away, homeInfo, awayInfo,
  homeColor, homeColor2, awayColor, awayColor2, winnerKey, donutData, justPredicted,
}: {
  pred: Prediction;
  home: string; away: string;
  homeInfo: TeamInfo | undefined; awayInfo: TeamInfo | undefined;
  homeColor: string; homeColor2: string; awayColor: string; awayColor2: string;
  winnerKey: "home" | "draw" | "away";
  donutData: { name: string; value: number; fill: string }[];
  justPredicted?: boolean;
}) {
  const T = useLang();
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.35 }}
      className="space-y-6"
    >
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {/* Donut chart */}
        <div
          className="rounded-xl p-4 flex flex-col items-center"
          style={{ background: "var(--color-arena-elevated)" }}
        >
          <p
            className="text-[10px] uppercase tracking-widest mb-3"
            style={{ fontFamily: "var(--font-mono)", color: "var(--color-ink-muted)" }}
          >
            {T.probabilities}
          </p>
          <ResponsiveContainer width="100%" height={176}>
            <RadialBarChart innerRadius="50%" outerRadius="88%" data={donutData} startAngle={90} endAngle={-270}>
              <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
              <RadialBar dataKey="value" cornerRadius={5} />
              <Tooltip
                formatter={(v: number) => `${(+v).toFixed(1)}%`}
                contentStyle={{
                  background: "var(--color-arena-deep)",
                  border: "1px solid rgba(255,255,255,0.08)",
                  borderRadius: 10,
                  fontFamily: "var(--font-mono)",
                  fontSize: 12,
                  color: "var(--color-ink-primary)",
                }}
              />
            </RadialBarChart>
          </ResponsiveContainer>
          <div className="flex gap-3 flex-wrap justify-center mt-1">
            {donutData.map((d) => (
              <span key={d.name} className="flex items-center gap-1.5 text-xs" style={{ fontFamily: "var(--font-body)", color: "var(--color-ink-secondary)" }}>
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ background: d.fill }} />
                {d.name}
              </span>
            ))}
          </div>
        </div>

        {/* Barras animadas */}
        <div className="flex flex-col justify-center space-y-3.5">
          <ProbBar pct={pred.home_win} color={homeColor} label={`${homeInfo?.flag ?? ""} ${home}`} isWinner={winnerKey === "home"} delay={0} />
          <ProbBar pct={pred.draw}     color="#777799"   label={T.draw}                               isWinner={winnerKey === "draw"} delay={0.12} />
          <ProbBar pct={pred.away_win} color={awayColor} label={`${awayInfo?.flag ?? ""} ${away}`} isWinner={winnerKey === "away"} delay={0.24} />
        </div>
      </div>

      {/* Cards de ELO — colores de bandera + stadium immersion */}
      <div className="grid grid-cols-2 gap-4">
        {([
          { team: home, info: homeInfo, color: homeColor, color2: homeColor2, isWinner: winnerKey === "home" },
          { team: away, info: awayInfo, color: awayColor, color2: awayColor2, isWinner: winnerKey === "away" },
        ] as { team: string; info: TeamInfo | undefined; color: string; color2: string; isWinner: boolean }[]).map(({ team, info, color, color2, isWinner }) => (
          <motion.div
            key={team}
            variants={popIn}
            initial="hidden"
            animate={isWinner && justPredicted
              ? { opacity: 1, scale: [1, 1.07, 1.02], y: [8, -6, 0] }
              : "visible"
            }
            whileHover={{ y: -4, scale: 1.02 }}
            transition={{ type: "spring", stiffness: 260, damping: 20, delay: isWinner ? 0.2 : 0 }}
            className="rounded-2xl p-4 text-center overflow-hidden relative"
            style={{
              background: `linear-gradient(155deg, ${color}26 0%, ${color2}0E 40%, var(--color-arena-card) 100%)`,
              border: `1px solid ${isWinner && justPredicted ? color + "55" : color + "30"}`,
              boxShadow: isWinner && justPredicted
                ? `0 0 0 2px ${color}40, 0 8px 32px ${color}30`
                : `0 4px 20px ${color}15, 0 1px 0 rgba(255,255,255,0.04)`,
            }}
          >
            {/* Stadium field overlay — immersive background */}
            <StadiumOverlay color={color} />

            {/* Flag color strip at top */}
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, height: 3,
              background: `linear-gradient(90deg, ${color}, ${color2})`,
              borderRadius: "16px 16px 0 0",
            }} />

            {/* Winner crown badge */}
            {isWinner && justPredicted && (
              <motion.div
                initial={{ scale: 0, y: -10 }}
                animate={{ scale: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 400, damping: 18, delay: 0.3 }}
                style={{
                  position: "absolute", top: 8, right: 8,
                  background: `linear-gradient(135deg, ${color}, ${color2})`,
                  borderRadius: 6, padding: "0.1rem 0.4rem",
                  fontFamily: "var(--font-mono)", fontSize: "0.46rem",
                  letterSpacing: "0.12em", color: "#000",
                  fontWeight: 800, textTransform: "uppercase",
                  zIndex: 2,
                }}
              >
                ✦ WIN
              </motion.div>
            )}

            <div className="relative z-10">
              <div className="text-4xl mb-2 mt-1">{info?.flag}</div>
              <div className="font-bold tracking-wide" style={{ fontFamily: "var(--font-heading)", fontSize: "0.82rem", color: "var(--color-ink-primary)" }}>
                {team}
              </div>
              <div className="tabular-nums mt-2 leading-none" style={{ fontFamily: "var(--font-display)", fontSize: "2.2rem", color }}>
                {info?.elo.toFixed(0)}
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.5rem", letterSpacing: "0.1em", color: "var(--color-ink-muted)", textTransform: "uppercase", marginTop: "0.2rem" }}>
                ELO · #{info?.rank}
              </div>
              <div style={{ height: 1, background: `linear-gradient(90deg, transparent, ${color}30, transparent)`, margin: "0.65rem 0 0.5rem" }} />
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.6rem", color: "var(--color-ink-secondary)" }}>
                ⚽ {info?.goals_scored.toFixed(2)} — {info?.goals_conceded.toFixed(2)} 🛡
              </div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: "0.52rem", color: "var(--color-ink-muted)", marginTop: "0.2rem" }}>
                {info?.wc_matches} {T.wcMatches}
              </div>
            </div>
          </motion.div>
        ))}
      </div>
    </motion.div>
  );
}

/* ══════════════════════════════════════════════════════
   BOTÓN CTA — World Cup electric blue→red gradient
══════════════════════════════════════════════════════ */
function PredictCTA({ onClick, disabled, loading }: { onClick: () => void; disabled: boolean; loading: boolean }) {
  const T = useLang();
  return (
    <motion.button
      onClick={onClick}
      disabled={disabled}
      whileHover={disabled ? {} : { scale: 1.025, y: -2 }}
      whileTap={disabled ? {} : { scale: 0.965, y: 0 }}
      className="relative w-full h-14 rounded-xl overflow-hidden"
      style={{
        fontFamily: "var(--font-heading)",
        fontWeight: 700,
        fontSize: "1.1rem",
        letterSpacing: "0.1em",
        textTransform: "uppercase",
        background: disabled
          ? "rgba(0,31,160,0.18)"
          : "linear-gradient(110deg, #001F8C 0%, #0033CC 25%, #C8102E 65%, #8B0018 100%)",
        backgroundSize: "200% 100%",
        color: disabled ? "rgba(80,120,255,0.35)" : "#FFFFFF",
        boxShadow: disabled ? "none" : "0 6px 28px rgba(0,50,200,0.35), 0 0 0 1px rgba(200,16,46,0.25), inset 0 1px 0 rgba(255,255,255,0.18)",
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "box-shadow 0.3s",
        animation: disabled ? "none" : "btn-world-cup 3s ease-in-out infinite",
      }}
    >
      {/* Shimmer sweep */}
      {!disabled && (
        <motion.div
          className="absolute inset-0 pointer-events-none"
          style={{ background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.18) 50%, transparent 100%)" }}
          initial={{ x: "-110%" }}
          whileHover={{ x: "210%" }}
          transition={{ duration: 0.6 }}
        />
      )}
      {/* Football texture lines */}
      {!disabled && (
        <svg aria-hidden style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.06, pointerEvents: "none" }} viewBox="0 0 400 56" preserveAspectRatio="none">
          <ellipse cx="200" cy="28" rx="60" ry="22" fill="none" stroke="white" strokeWidth="1"/>
          <circle cx="200" cy="28" r="3" fill="none" stroke="white" strokeWidth="1"/>
          <line x1="200" y1="0" x2="200" y2="56" stroke="white" strokeWidth="0.5"/>
        </svg>
      )}

      <span className="relative z-10 flex items-center justify-center gap-2.5">
        {loading ? (
          <>
            <motion.span
              animate={{ rotate: 360 }}
              transition={{ duration: 0.85, repeat: Infinity, ease: "linear" }}
              className="inline-block w-4 h-4 rounded-full border-2 border-current border-t-transparent"
            />
            {T.calculating}
          </>
        ) : (
          <>
            <span style={{ fontSize: "1rem" }}>⚽</span>
            {T.predictBtn}
          </>
        )}
      </span>
    </motion.button>
  );
}

/* ══════════════════════════════════════════════════════
   OVERLAY ESPECIAL — Colombia vs Portugal
   Aparece durante los 2 s de cálculo
══════════════════════════════════════════════════════ */
function ColombiaPortugalOverlay({ active }: { active: boolean }) {
  return (
    <AnimatePresence>
      {active && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
          style={{
            position: "fixed",
            inset: 0,
            zIndex: 999,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            background: "rgba(0,0,0,0.82)",
            backdropFilter: "blur(6px)",
            WebkitBackdropFilter: "blur(6px)",
          }}
        >
          {/* Card contenedor */}
          <motion.div
            initial={{ scale: 0.88, y: 24 }}
            animate={{ scale: 1, y: 0 }}
            exit={{ scale: 0.92, y: -16, opacity: 0 }}
            transition={{ type: "spring", stiffness: 260, damping: 22 }}
            style={{
              position: "relative",
              borderRadius: 20,
              overflow: "hidden",
              maxWidth: "min(560px, 92vw)",
              width: "100%",
              boxShadow: "0 32px 80px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.08)",
            }}
          >
            <img
              src="/images/colombia-vs-portugal.webp"
              alt="Colombia vs Portugal"
              style={{ display: "block", width: "100%", height: "auto" }}
            />

            {/* Gradient overlay bottom */}
            <div style={{
              position: "absolute", bottom: 0, left: 0, right: 0, height: "45%",
              background: "linear-gradient(0deg, rgba(6,6,16,0.95) 0%, rgba(6,6,16,0.6) 55%, transparent 100%)",
            }} />

            {/* Label */}
            <div style={{
              position: "absolute", bottom: 0, left: 0, right: 0,
              padding: "1rem 1.25rem",
              display: "flex", alignItems: "flex-end", justifyContent: "space-between",
            }}>
              <div>
                <div style={{
                  fontFamily: "var(--font-display)",
                  fontSize: "clamp(1.3rem, 5vw, 1.9rem)",
                  letterSpacing: "0.04em",
                  lineHeight: 1,
                  color: "#FFFFFF",
                  textShadow: "0 2px 12px rgba(0,0,0,0.8)",
                }}>
                  🇨🇴 Colombia <span style={{ color: "rgba(255,255,255,0.35)", margin: "0 0.3em" }}>vs</span> Portugal 🇵🇹
                </div>
                <div style={{
                  fontFamily: "var(--font-mono)",
                  fontSize: "0.52rem",
                  letterSpacing: "0.18em",
                  color: "var(--color-wc-gold)",
                  textTransform: "uppercase",
                  marginTop: "0.4rem",
                }}>
                  FIFA World Cup 2026 · Analizando…
                </div>
              </div>

              {/* Scanning dots */}
              <div style={{ display: "flex", gap: 5, paddingBottom: 4 }}>
                {[0, 1, 2].map((i) => (
                  <motion.div
                    key={i}
                    animate={{ opacity: [0.2, 1, 0.2], scale: [0.8, 1, 0.8] }}
                    transition={{ duration: 0.9, repeat: Infinity, delay: i * 0.22 }}
                    style={{
                      width: 7, height: 7, borderRadius: "50%",
                      background: i === 0 ? "#FCD116" : i === 1 ? "#AF0C00" : "#FFFFFF",
                    }}
                  />
                ))}
              </div>
            </div>

            {/* Top accent bar — Colombia + Portugal colors */}
            <div style={{
              position: "absolute", top: 0, left: 0, right: 0, height: 3,
              background: "linear-gradient(90deg, #FCD116 0%, #009C3B 33%, #AF0C00 66%, #006600 100%)",
            }} />
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* ══════════════════════════════════════════════════════
   CELEBRATION BURST — confetti after prediction
══════════════════════════════════════════════════════ */
function CelebrationBurst({ active, winnerColor }: { active: boolean; winnerColor: string }) {
  if (!active) return null;
  const colors = [winnerColor, "#E5002D", "#C9981F", "#FFFFFF", "#0033CC", "#00CC44"];
  const particles = Array.from({ length: 28 }, (_, i) => ({
    id: i,
    color: colors[i % colors.length],
    cx: `${(Math.random() - 0.5) * 200}px`,
    cy: `${-(Math.random() * 120 + 40)}px`,
    cr: `${Math.random() * 360}deg`,
    size: Math.random() * 6 + 4,
    delay: i * 0.035,
    shape: i % 3, // 0=circle, 1=rect, 2=diamond
  }));

  return (
    <div style={{ position: "absolute", bottom: "50%", left: "50%", pointerEvents: "none", zIndex: 30 }} aria-hidden>
      {particles.map((p) => (
        <motion.div
          key={p.id}
          initial={{ x: 0, y: 0, rotate: 0, scale: 1, opacity: 1 }}
          animate={{ x: p.cx, y: p.cy, rotate: p.cr, scale: 0, opacity: 0 }}
          transition={{ duration: 1.1 + Math.random() * 0.5, delay: p.delay, ease: "easeOut" }}
          style={{
            position: "absolute",
            width: p.size,
            height: p.size,
            background: p.color,
            borderRadius: p.shape === 0 ? "50%" : p.shape === 1 ? "1px" : "2px",
            transform: p.shape === 2 ? "rotate(45deg)" : "none",
          }}
        />
      ))}
    </div>
  );
}
