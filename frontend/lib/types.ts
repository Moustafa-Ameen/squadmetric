export interface Player {
  element_id?: number | null;
  name: string;
  team: string;
  position: string;
  price: number;
  total_points: number;
  ppg: number;
  form: number;
  start_likelihood: number;
  value: number;
  captain_score: number;
  transfer_score: number;
  selected_by_percent?: number;
  defensive_contribution?: number;
  defensive_contribution_per_90?: number;
  safety_tier?: "Safe" | "Risky" | "";
  web_name?: string;
  team_code?: number;
  reasoning?: string;
  season?: string;
  bootstrap_hash?: string;
  data_cutoff?: string;
  prior_source?: string;
}

export interface CaptainPick {
  element_id?: number | null;
  name: string;
  team: string;
  position: string;
  price?: number;
  ppg?: number;
  form?: number;
  start_likelihood: number;
  captain_score?: number;
  predicted_pts?: number | null;
  adjusted_pts?: number | null;
  team_code?: number;
  web_name?: string;
  reasoning?: string;
  season?: string;
  bootstrap_hash?: string;
  rules_version?: string;
  data_cutoff?: string;
  model?: string;
  portfolio_version?: string;
}

export interface TransferTarget {
  element_id?: number | null;
  name: string;
  team: string;
  position: string;
  price: number;
  form?: number;
  predicted_pts?: number | null;
  adjusted_pts?: number | null;
  start_likelihood: number;
  value?: number;
  transfer_score: number;
  selected_by_percent?: number;
  rotation_risk?: boolean;
  defensive_contribution?: number;
  defensive_contribution_per_90?: number;
  safety_tier?: "Safe" | "Risky" | "";
  team_code?: number;
  season?: string;
  bootstrap_hash?: string;
  rules_version?: string;
  data_cutoff?: string;
  model?: string;
  portfolio_version?: string;
  prior_source?: string;
}

export interface Fixture {
  id: number;
  team_h: number;
  team_a: number;
  team_h_name?: string;
  team_a_name?: string;
  team_h_short?: string;
  team_a_short?: string;
  team_h_score?: number | null;
  team_a_score?: number | null;
  event: number | null;
  kickoff_time?: string | null;
  started?: boolean;
  finished?: boolean;
  minutes?: number | null;
  team_h_difficulty: number;
  team_a_difficulty: number;
  source?: string;
  season?: string;
  difficulty_source?: string;
}

export interface FixtureTick {
  team: string;
  team_short: string;
  range?: number;
  source?: string;
  season?: string;
  difficulty_source?: string;
  fixtures: {
    gw: number;
    opponent: string;
    home: boolean;
    difficulty: number;
  }[];
}

export interface ComparisonFixture {
  gw: number;
  opponent: string;
  home: boolean;
  difficulty: number;
}

export interface ComparisonPlayer {
  element_id: number;
  name: string;
  web_name?: string;
  team: string;
  position: string;
  price: number | null;
  points_per_game: number | null;
  form: number | null;
  captain_score: number | null;
  transfer_score: number | null;
  minutes_security: number | null;
  defensive_contribution_per_90: number | null;
  selected_by_percent: number | null;
  team_code?: number | null;
  fixtures: ComparisonFixture[];
  average_fixture_difficulty: number | null;
  live_metrics_available: boolean;
  live_metrics_unavailable_reason: string | null;
}

export interface PlayerComparisonResponse {
  players: ComparisonPlayer[];
  season_state: SeasonStateCode;
  fpl_api_season?: string;
  fixture_source: string;
  fixture_season: string;
  difficulty_source: string;
}

export interface PlayerHistoryPoint {
  element_id?: number | null;
  gw: number;
  price: number;
  total_points: number;
  minutes: number;
  selected_by_percent: number;
}

export interface TeamData {
  team_name: string;
  overall_rank: number | null;
  total_points: number | null;
  bank_value: number | null;
  current_gw_points: number | null;
  squad_value: number | null;
  free_transfers_available: number | null;
}

export interface SquadPlayer {
  element_id?: number | null;
  name: string;
  position: string;
  team: string;
  team_code?: number;
  web_name?: string;
  price?: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
  predicted_pts: number | null;
  start_likelihood: number | null;
  form: number | null;
}

export interface SeasonState {
  season_state: SeasonStateCode;
  fpl_api_season: string;
  fixture_source: string;
  fixture_season: string;
  difficulty_source: string;
  current_gw: number | null;
  next_gw: number | null;
  last_completed_gw: number | null;
  next_season_start: string | null;
  data_freshness: {
    fpl_api: string;
    fixtures: string;
  };
  recommendations_ready?: boolean;
  artifact_status?: string;
  artifact_errors?: string[];
  artifact_manifest?: Record<string, unknown> | null;
}

export type SeasonStateCode =
  | "pre_season"
  | "in_season"
  | "season_ended_preseason"
  | "season_ended_no_next_data";

export interface PlannerFixtureProjection {
  opponent: string;
  opponent_name: string;
  home: boolean;
  opponent_difficulty?: number | null;
  opponent_strength: number;
  predicted_points: number;
  start_likelihood: number;
  projected_points: number;
}

export interface PlannerProjection {
  gameweek: number;
  projected_points: number;
  blank: boolean;
  double: boolean;
  fixtures: PlannerFixtureProjection[];
}

export interface PlannerPlayer {
  element_id: number;
  name: string;
  web_name?: string;
  team: string;
  team_code?: number;
  position: string;
  price: number;
  start_likelihood: number;
  projections: PlannerProjection[];
  pick_order?: number;
  is_starter?: boolean;
  is_captain?: boolean;
  is_vice_captain?: boolean;
}

export interface PlannerBaselinePoint {
  gameweek: number;
  projected_points: number;
  blank_count: number;
  double_count: number;
}

export interface PlannerResponse {
  team_id: number;
  season_state: SeasonStateCode;
  fpl_api_season?: string;
  fixture_season?: string;
  next_season_start?: string | null;
  message?: string;
  start_gameweek: number;
  horizon: number;
  squad_gameweek: number;
  model: string;
  portfolio_version?: string;
  transfer_model?: string;
  captain_model?: string;
  chip_model?: string;
  assumption: string;
  bank_value: number | null;
  free_transfers_available: number;
  max_extra_free_transfers: number;
  baseline: PlannerBaselinePoint[];
  squad: PlannerPlayer[];
  player_pool: PlannerPlayer[];
  decision?: PlannerDecision | null;
  decision_error?: string | null;
}

export interface PlannerDecisionTransfer {
  outgoing_id: number | null;
  outgoing_name: string | null;
  incoming_id: number | null;
  incoming_name: string | null;
  projected_gain: number;
  hit_cost: number;
  hit_selected: boolean;
}

export interface PlannerDecision {
  transfer: PlannerDecisionTransfer;
  chip: string | null;
  chip_key: string | null;
  starting_ids: number[];
  bench_order: number[];
  captain_id: number | null;
  vice_captain_id: number | null;
  expected_gameweek_points: number;
  expected_horizon_points: number;
  no_chip_horizon_points: number;
  expected_horizon_gain: number;
  uncertainty_penalty: number;
  reason: string;
}

export interface InitialSquadPlayer {
  element_id: number;
  player_name: string;
  web_name?: string;
  team: string;
  position: string;
  price: number;
  gw1_points: number;
  horizon_points: number;
  is_starter: boolean;
  bench_order: number | null;
}

export interface InitialSquadResponse {
  season: string;
  bootstrap_hash: string;
  rules_version: string;
  data_cutoff: string;
  model: string;
  portfolio_version: string;
  horizon: number;
  budget: number;
  cost: number;
  formation: string;
  captain_id: number;
  vice_captain_id: number;
  expected_gw1_points: number;
  squad: InitialSquadPlayer[];
  assumption: string;
}

export type ChipTipsStatus = "no_team" | "unavailable" | "insufficient_data" | "ready";

export interface ChipTipAlert {
  chip: string;
  key: string;
  message: string;
  strength_percent: number;
  metrics: Record<string, number | boolean>;
}

export interface ChipAlternative {
  gameweek: number;
  chip_key: string;
  chip: string;
  expected_immediate_gain: number;
  expected_horizon_gain: number;
  reason: string;
}

export interface ChipRecommendation {
  action: "use" | "save";
  chip: string | null;
  chip_key: string | null;
  chip_number: number | null;
  gameweek: number;
  expected_immediate_gain: number;
  expected_horizon_gain: number;
  expected_gameweek_points: number;
  no_chip_gameweek_points: number;
  expected_horizon_points: number;
  no_chip_horizon_points: number;
  uncertainty_penalty: number;
  downside_range: { low: number; high: number };
  confidence: "low" | "medium" | "high";
  ordinary_transfer_allowed: boolean;
  ordinary_transfer_applied: boolean;
  reason: string;
  best_alternative: ChipAlternative | null;
}

export interface ChipCounterfactual {
  chip_key: string;
  chip_number: number | null;
  legal: boolean;
  selected: boolean;
  expected_gameweek_points: number;
  no_chip_gameweek_points: number;
  expected_horizon_points: number;
  no_chip_horizon_points: number;
  expected_horizon_gain: number;
  future_opportunity_cost: number;
  uncertainty_penalty: number;
  reason: string;
}

export interface ChipTipsResponse {
  status: ChipTipsStatus;
  team_id?: number | null;
  season_state?: SeasonStateCode;
  fpl_api_season?: string;
  fixture_season?: string;
  difficulty_source?: string;
  current_gw?: number | null;
  next_gw?: number | null;
  target_gameweek?: number;
  message: string;
  alerts: ChipTipAlert[];
  recommendation?: ChipRecommendation;
  counterfactuals?: ChipCounterfactual[];
  alternatives?: ChipAlternative[];
  remaining_chips?: string[];
  used_chips?: string[];
  explanatory_signals?: Record<string, unknown>;
  baseline_gameweeks?: number | number[];
  minimum_baseline_gameweeks?: number;
  model?: string;
  model_version?: string;
  chip_mode?: string;
  rules_version?: string;
  rules_payload_hash?: string;
  data_cutoff?: string | null;
  generated_at?: string;
}

export type ChipAvailabilityStatus = "used" | "available" | "not_yet_available" | "expired";

export interface ChipStatusRow {
  key: string;
  chip_type: string;
  name: string;
  subtitle: string;
  definition_id?: number | null;
  number: number;
  start_event: number;
  stop_event: number;
  status: ChipAvailabilityStatus;
  used_gameweek?: number | null;
  available_from?: number | null;
}

export interface ChipStatusResponse {
  status: "no_team" | "unavailable" | "ready";
  team_id?: number | null;
  season_state?: SeasonStateCode;
  fpl_api_season?: string;
  fixture_season?: string;
  current_gameweek?: number;
  season_reset?: boolean;
  next_season_start?: string | null;
  message: string;
  chips: ChipStatusRow[];
}

export interface BacktestResult {
  strategy: string;
  total_captain_points: number;
  avg_per_gameweek: number;
}

export interface AccuracyResult {
  model: string;
  raw_MAE: number;
  raw_RMSE: number;
  raw_beats_naive_MAE: string;
  raw_beats_naive_RMSE: string;
  adjusted_MAE: number;
  adjusted_RMSE: number;
  adjusted_beats_naive_MAE: string;
  adjusted_beats_naive_RMSE: string;
}

export interface Top10Metric {
  model: string;
  precision_at_10: number;
  recall_at_10: number;
}
