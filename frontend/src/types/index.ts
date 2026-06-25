export interface TeamInfo {
  elo: number;
  rank: number;
  flag: string;
  group: string;
  confederation: string;
  goals_scored: number;
  goals_conceded: number;
  wc_matches: number;
  pen_wins: number;
  pen_total: number;
}

// ── Live tournament (openfootball) ─────────────────────────────────────────────

export interface LiveMatch {
  team1: string;
  team2: string;
  score1: number | null;
  score2: number | null;
  group?: string;
  round?: string;
  date?: string;
  /** solo vía API football-data: TIMED | IN_PLAY | PAUSED | FINISHED */
  status?: string;
  /** solo vía API football-data: fecha-hora UTC del kickoff (ISO) */
  utc?: string;
}

/** clave canónica "A|B" (orden alfabético) → ganador o null si empate */
export type FixedResults = Map<string, string | null>;

export interface Prediction {
  home_win: number;
  draw: number;
  away_win: number;
}

export interface HistoricalMatch {
  date: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  outcome: string;
  year: number;
}

export interface GoalsByYear {
  year: number;
  total: number;
  matches: number;
  avg: number;
}

export interface TopScoringTeam {
  team: string;
  flag: string;
  matches: number;
  goals_for: number;
  goals_against: number;
  goal_diff: number;
  avg: number;
}

export interface Upset {
  year: number;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  favored: string;
  winner: string;
  elo_favored: number;
  elo_winner: number;
  elo_advantage: number;
  flag_favored: string;
  flag_winner: string;
}

export interface ColombiaStats {
  total_matches: number;
  wins: number;
  draws: number;
  losses: number;
  goals_for: number;
  goals_against: number;
  win_pct: number;
  elo_current: number;
  elo_rank: number;
}

export interface SiteStats {
  total_matches: number;
  total_goals: number;
  avg_goals_all: number;
  n_editions: number;
  highest_scoring_match: {
    home_team: string; away_team: string;
    home_score: number; away_score: number;
    total: number; year: number;
    flag_home: string; flag_away: string;
  };
  biggest_victory: {
    home_team: string; away_team: string;
    home_score: number; away_score: number;
    margin: number; year: number;
    flag_home: string; flag_away: string;
  };
  goals_by_year: GoalsByYear[];
  best_avg_edition: { year: number; avg: number };
  worst_avg_edition: { year: number; avg: number };
  top_scoring_teams: TopScoringTeam[];
  top_upsets: Upset[];
  colombia: ColombiaStats;
}

export interface SimResult {
  team: string;
  flag: string;
  group: string;
  confederation: string;
  elo: number;
  // Group finish positions
  first: number;
  second: number;
  third: number;
  fourth: number;
  // Probabilidad de ser uno de los 8 mejores terceros (subconjunto de "third")
  bestThird: number;
  // Knockout stages
  r32: number;
  r16: number;
  qf: number;
  sf: number;
  final: number;
  champion: number;
}

// ── Group phase ────────────────────────────────────────────────────────────────

export interface GroupMatch {
  date: string;
  round: string;
  ground: string;
  team1: string;
  team2: string;
  team1_flag: string;
  team2_flag: string;
  t1_win: number;
  draw: number;
  t2_win: number;
}

export interface GroupStandingEntry {
  team: string;
  flag: string;
  first: number;
  second: number;
  third: number;
  fourth: number;
}

// ── Backtest Qatar 2022 ────────────────────────────────────────────────────────

export interface BacktestMatch {
  date: string;
  home_team: string;
  away_team: string;
  home_flag: string;
  away_flag: string;
  home_score: number;
  away_score: number;
  home_win: number;
  draw: number;
  away_win: number;
  predicted: string;
  actual: string;
  hit: boolean;
}

export interface QatarBacktest {
  n: number;
  hits: number;
  accuracy: number;
  matches: BacktestMatch[];
}

// ── Goalscorers ────────────────────────────────────────────────────────────────

export interface GoalscorerVictim {
  team: string;
  flag: string;
  goals: number;
}

export interface Goalscorer {
  rank: number;
  scorer: string;
  country: string;
  flag: string;
  goals: number;
  victims: GoalscorerVictim[];
}
