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
  captain_rank_score: number;
  transfer_rank_score: number;
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
  robustness_class?: "locked" | "stable" | "fragile" | null;
  scenario_selection_rate?: number | null;
  metrics_available?: boolean;
  catalog_source?: string;
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
  raw_xp: number;
  expected_points: number;
  start_adjusted_xp: number;
  captain_expected_points: number;
  captaincy_score: number;
  team_code?: number;
  web_name?: string;
  reasoning?: string;
  season?: string;
  bootstrap_hash?: string;
  rules_version?: string;
  data_cutoff?: string;
  model?: string;
  portfolio_version?: string;
  projection_contract_version: string;
}

export interface TransferTarget {
  element_id?: number | null;
  name: string;
  team: string;
  position: string;
  price: number;
  form?: number;
  raw_xp: number;
  expected_points: number;
  start_adjusted_xp: number;
  captain_expected_points: number;
  captaincy_score: number;
  start_likelihood: number;
  value?: number;
  transfer_rank_score: number;
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
  projection_contract_version: string;
  prior_source?: string;
}

export interface OverviewResponse {
  player_count: number;
  captains: CaptainPick[];
  predictions: CaptainPick[];
  transfers: TransferTarget[];
  fixtures: FixtureTick[];
  gems: Player[];
  accuracy: AccuracyResult[];
  projection_contract_version: string;
  data_cutoff: string;
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
  raw_xp: number | null;
  expected_points: number | null;
  captain_rank_score: number | null;
  transfer_rank_score: number | null;
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
  purchase_price?: number | null;
  current_price?: number | null;
  selling_price?: number | null;
  is_captain: boolean;
  is_vice_captain: boolean;
  raw_xp: number | null;
  expected_points: number | null;
  start_adjusted_xp: number | null;
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
  recommendations_ready: boolean;
  decision_status: "ready" | "blocked" | "unavailable";
  recommendation_mode: "generic" | "blocked";
  decision_blockers: DecisionBlocker[];
  artifact_status?: string;
  artifact_errors?: string[];
  artifact_manifest?: Record<string, unknown> | null;
  live_data: {
    checked_at: string;
    bootstrap_hash: string | null;
    fixtures_hash: string | null;
    player_count: number | null;
    team_count: number | null;
  };
  artifact_data: {
    data_cutoff: string | null;
    age_hours: number | null;
    bootstrap_hash: string | null;
    fixtures_hash: string | null;
    player_count: number | null;
    team_count: number | null;
    rules_version: string | null;
  };
}

export interface DecisionBlocker {
  code: string;
  message: string;
}

export type SeasonStateCode =
  | "pre_season"
  | "in_season"
  | "unavailable"
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

export interface PlannerDecisionMove {
  outgoing_id: number | null;
  outgoing_name: string | null;
  incoming_id: number | null;
  incoming_name: string | null;
  projected_gain: number;
  hit_cost: number;
}

export interface PlannerDecision {
  transfer: PlannerDecisionTransfer;
  transfers: PlannerDecisionMove[];
  transfer_count: number;
  total_hit_cost: number;
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

export interface DecisionCenterPlayer {
  element_id: number;
  name: string;
  web_name?: string;
  team: string;
  team_code?: number | null;
  position: string;
  price: number;
  expected_points: number;
  start_likelihood: number;
  blank: boolean;
  double: boolean;
}

export interface DecisionCenterTransfer {
  outgoing_id: number | null;
  outgoing_name: string | null;
  incoming_id: number | null;
  incoming_name: string | null;
  projected_gain: number;
  hit_cost: number;
}

export interface DecisionCenterRecommendation {
  transfer_action: string;
  transfers: DecisionCenterTransfer[];
  transfer_count: number;
  hit_recommended: boolean;
  hit_cost: number;
  chip_action: string;
  chip_key: string | null;
  starting_xi: DecisionCenterPlayer[];
  bench_order: DecisionCenterPlayer[];
  captain_id: number | null;
  vice_captain_id: number | null;
  expected_gameweek_points: number;
  expected_horizon_points: number;
  gain_vs_no_action: number;
  future_opportunity_cost: number;
  uncertainty_penalty: number;
  downside_range: { low: number; high: number; method: string };
  confidence: "low" | "medium" | "high";
  confidence_basis: {
    search_score_margin: number;
    uncertainty_penalty: number;
  };
  reason: string;
}

export interface DecisionCenterAlternative {
  branch_id: string;
  chip: string;
  transfers: DecisionCenterTransfer[];
  hit_cost: number;
  expected_gameweek_points: number;
  expected_horizon_points: number;
  gain_vs_no_action: number;
  reason: string;
}

export interface DecisionCenterResponse {
  status: "ready" | "unavailable";
  message: string;
  team_id: number;
  season_state: SeasonStateCode;
  gameweek: number;
  horizon: number;
  rules_version?: string | null;
  data_cutoff?: string | null;
  deadline?: string | null;
  bootstrap_hash?: string | null;
  fixtures_hash?: string | null;
  portfolio_version?: string | null;
  decision_engine_version?: string | null;
  transfer_model?: string | null;
  captain_model?: string | null;
  chip_model?: string | null;
  state_before?: {
    bank: number;
    free_transfers: number;
    remaining_chips: string[];
    used_chips: string[];
  };
  recommendation?: DecisionCenterRecommendation;
  no_action?: {
    expected_gameweek_points: number;
    expected_horizon_points: number;
    starting_ids: number[];
    captain_id: number | null;
    vice_captain_id: number | null;
    reason: string;
  };
  alternatives?: DecisionCenterAlternative[];
}

export interface InitialSquadPlayer {
  element_id: number;
  player_name: string;
  web_name?: string;
  team: string;
  position: string;
  price: number;
  purchase_price?: number | null;
  current_price?: number | null;
  selling_price?: number | null;
  gw1_points: number;
  horizon_points: number;
  is_starter: boolean;
  bench_order: number | null;
  start_likelihood?: number;
  availability_probability?: number;
  status?: string;
  prior_source?: string;
  robustness_class?: "locked" | "stable" | "fragile" | null;
  scenario_selection_rate?: number | null;
  set_piece?: {
    model_version: string | null;
    source_url: string | null;
    available: boolean;
    reason: string | null;
    transition_adjustment_per_start: number;
    penalties_rank: number | null;
    direct_free_kicks_rank: number | null;
    corners_indirect_rank: number | null;
  } | null;
}

export interface InitialSquadAlternative {
  profile: "maximum_points" | "balanced" | "safe";
  selected: boolean;
  status: string;
  cost: number;
  bank: number;
  expected_gw1_points: number;
  expected_horizon_points: number;
  mean_squad_start_probability: number;
  outfield_bench_start_probability: number;
  low_reliability_players: string[];
  captain_id: number;
  vice_captain_id: number;
  changes_from_balanced: number;
}

export interface InitialSquadResponse {
  season: string;
  bootstrap_hash: string;
  rules_version: string;
  data_cutoff: string;
  model: string;
  portfolio_version: string;
  decision_engine_version: string;
  horizon: number;
  risk_profile: "maximum_points" | "balanced" | "safe";
  budget: number;
  cost: number;
  bank: number;
  formation: string;
  captain_id: number;
  vice_captain_id: number;
  expected_gw1_points: number;
  decision_alternatives: InitialSquadAlternative[];
  decision_audit: {
    availability_clear: boolean;
    low_reliability_starters: string[];
    low_reliability_bench: string[];
    captain_start_probability: number;
    vice_captain_start_probability: number;
    vice_captain_fallback_points: number;
    first_outfield_cover_id: number | null;
    first_outfield_cover_points: number;
    first_outfield_cover_start_probability: number;
    requires_deadline_refresh: boolean;
    reason: string;
  };
  set_piece_summary: {
    model_version: string | null;
    source_url: string | null;
    selected_primary_penalty_takers: string[];
  };
  deadline_finalization?: {
    status: "monitoring" | "blocked" | "finalization_ready";
    data_ready: boolean;
    lock_ready: boolean;
    hours_to_deadline: number | null;
    final_news_reviewed: boolean;
    timing_blockers: string[];
    verdict: string;
    primary_challenger: {
      scenario_rate: number;
      players_out: string[];
      players_in: string[];
    } | null;
  } | null;
  robustness?: {
    scenario_count: number;
    distinct_squads: number;
    robust_squad_rate: number;
    autosub_activation_probability: number;
  } | null;
  squad: InitialSquadPlayer[];
  assumption: string;
}

export interface DraftWorkspacePlayer {
  element_id: number;
  name: string;
  web_name?: string;
  team: string;
  team_id?: number | null;
  team_code?: number | null;
  position: string;
  price: number;
  gw1_points: number;
  horizon_points: number;
  start_likelihood: number;
  availability_probability: number;
  status?: string | null;
  prior_source?: string | null;
}

export interface DraftConstraints {
  budget: number;
  squad_size: number;
  starting_xi_size: number;
  max_players_per_team: number;
  position_counts: Record<string, number>;
}

export interface DraftWorkspaceResponse {
  season: string;
  bootstrap_hash: string;
  fixtures_hash?: string | null;
  rules_version: string;
  data_cutoff: string;
  model: string;
  horizon: number;
  risk_profile: "maximum_points" | "balanced" | "safe";
  constraints: DraftConstraints;
  optimized: InitialSquadResponse;
  player_pool: DraftWorkspacePlayer[];
}

export interface DeadlineChecklistItem {
  key: string;
  passed: boolean;
}

export interface DeadlineReadinessResponse {
  ready: boolean;
  season: string;
  data_cutoff: string;
  data_age_hours: number;
  maximum_age_hours: number;
  stale: boolean;
  next_gameweek: number | null;
  deadline: string | null;
  hours_to_deadline: number | null;
  final_refresh_required: boolean;
  blockers: string[];
  decision_lock_ready: boolean;
  checklist: DeadlineChecklistItem[];
  latest_shadow: {
    captured_at: string;
    decision_hash: string;
    expected_gw1_points: number;
    current: boolean;
  } | null;
  p11: {
    status: "monitoring" | "blocked" | "finalization_ready";
    data_ready: boolean;
    lock_ready: boolean;
    final_news_reviewed: boolean;
  } | null;
  p12: {
    model_version: string;
    source_url: string;
    category_coverage: Record<string, number>;
    primary_penalty_takers: number;
  } | null;
}

export interface PostGameweekDecisionEvidence {
  status: "finalized" | "not_captured";
  snapshot_hash?: string | null;
  outcome_hash?: string | null;
  expected_points?: number | null;
  selected_net_points?: number | null;
  best_frozen_branch_points?: number | null;
  selected_regret?: number | null;
}

export interface PostGameweekRow {
  gameweek: number;
  gross_points: number;
  hit_cost: number;
  net_points: number;
  total_points: number;
  overall_rank: number | null;
  rank_change: number | null;
  rank_percentile: number | null;
  points_on_bench: number;
  transfers: number;
  squad_value: number | null;
  bank: number | null;
  decision_evidence: PostGameweekDecisionEvidence;
}

export interface PostGameweekReviewResponse {
  schema_version: string;
  team_id: number;
  season: string;
  official_finalized_gameweeks: number[];
  reviewed_gameweeks: number;
  total_managers: number | null;
  summary: {
    net_points: number;
    hit_cost: number;
    points_on_bench: number;
    decision_evidence_gameweeks: number;
    decision_regret: number;
    latest_overall_rank: number | null;
  };
  rank_mode: {
    available: boolean;
    validated_for_recommendations: boolean;
    default_mode: "points";
    reason: string;
  };
  gameweeks: PostGameweekRow[];
  automatic_fpl_actions: false;
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
