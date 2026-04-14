// ── API response types ─────────────────────────────────────────────────────
// Matches the PredictResponse schema from api/main.py v0.2.0

export interface BookmakerOdds {
  bookmaker_title: string;
  price: number;
  raw_implied: number;
}

export interface SentimentResult {
  available: boolean;
  flag: "positive" | "concern" | "neutral";
  label: string | null;
  headline: string | null;
}

export interface H2HResult {
  available: boolean;
  total: number;
  a_wins: number;
  b_wins: number;
  total_surface: number;
  a_wins_surface: number;
  b_wins_surface: number;
  leader: "a" | "b" | null;
  leader_surface: "a" | "b" | null;
}

export interface PlayerPrediction {
  player: string;
  rank: number;
  points: number;
  model_prob: number;
  raw_implied: number;
  true_implied: number;
  vig_per_player: number;
  edge: number;
  signal: "value_bet" | "marginal" | "no_bet";
  recommendation: string;
  sentiment: SentimentResult | null;
  bookmakers: BookmakerOdds[];
}

export interface MatchPrediction {
  home: string;
  away: string;
  commence_time: string;
  surface: "clay" | "grass" | "hard" | "indoor_hard";
  h2h: H2HResult | null;
  players: PlayerPrediction[] | null;
  error: string | null;
}

export interface PredictResponse {
  fetched_at: string;
  matches_total: number;
  predictions: MatchPrediction[];
}
