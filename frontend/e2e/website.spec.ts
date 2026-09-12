import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page, type Route } from "@playwright/test";

const seasonState = {
  fpl_api_season: "2026-27",
  fixture_source: "FPL Fantasy API",
  fixture_season: "2026-27",
  difficulty_source: "Official FPL FDR",
  current_gw: 1,
  next_gw: 1,
  season_state: "pre_season",
  recommendations_ready: true,
  decision_status: "ready",
  recommendation_mode: "current",
  decision_blockers: [],
  artifact_status: "ready",
  artifact_errors: [],
  artifact_manifest: { rules_version: "2026-27-test", data_cutoff: "2026-08-18T08:00:00Z" },
  live_data: { checked_at: "2026-08-18T08:01:00Z" },
  artifact_data: { age_hours: 0.1 },
  last_completed_gw: null,
  next_season_start: "2026-08-21T19:00:00Z",
  data_freshness: { fpl_api: "live", fixtures: "live" },
};

const positions = ["GKP", "GKP", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"];
const players = positions.map((position, index) => ({
  element_id: index + 1,
  name: `Player ${index + 1}`,
  web_name: `P${index + 1}`,
  team: `T${Math.floor(index / 3) + 1}`,
  team_id: Math.floor(index / 3) + 1,
  team_code: index + 100,
  position,
  price: 6,
  gw1_points: 3 + index / 10,
  horizon_points: 18 + index,
  start_likelihood: 0.9,
  availability_probability: 1,
  status: "a",
  prior_source: "test",
}));

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async (route) => mockApi(route));
});

test("public landing page explains the product and leads with one clear action", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Make the smarter FPL decision. Every gameweek." })).toBeVisible();
  await expect(page.getByText("SquadMetric", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("link", { name: "Create your account" })).toBeVisible();
  await expect(page.getByText("Primary recommendation", { exact: true })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("privacy and terms are public, linked, and explicit about recommendation limits", async ({ page }) => {
  await page.goto("/privacy");
  await expect(page.getByRole("heading", { name: "Privacy Policy" })).toBeVisible();
  await expect(page.getByText("We do not ask for or store your official Fantasy Premier League password.")).toBeVisible();
  await page.getByRole("link", { name: "Terms", exact: true }).last().click();
  await expect(page.getByRole("heading", { name: "Terms of Use" })).toBeVisible();
  await expect(page.getByText("No score, rank, profit, availability, or top-1% finish is guaranteed.")).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("account creation exposes requirements and validates beside the field", async ({ page }) => {
  await page.goto("/signup");
  await expect(page.getByRole("heading", { name: "Create your account" })).toBeVisible();
  await page.getByLabel("Email address").fill("not-an-email");
  await page.getByLabel("Email address").blur();
  await expect(page.getByText("Enter a valid email address.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Create account" })).toBeDisabled();
  await expect(page.getByText("8+ characters")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /I agree to the Terms of Use/ })).not.toBeChecked();
  await expectNoSeriousAccessibilityViolations(page);
});

test("unconfigured authentication never simulates account creation", async ({ page }) => {
  await page.goto("/signup");
  await page.getByLabel("Email address").fill("manager@example.com");
  await page.getByLabel("Password", { exact: true }).fill("squadmetric1");
  await page.getByLabel("Confirm password").fill("squadmetric1");
  await expect(page.getByRole("button", { name: "Create account" })).toBeDisabled();
  await page.getByRole("checkbox", { name: /I agree to the Terms of Use/ }).check();
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText("Account access is not configured on this deployment.", { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/\/signup$/);
  await expectNoSeriousAccessibilityViolations(page);
});

test("guided onboarding accepts an official FPL URL and stores verified setup", async ({ page }) => {
  await page.goto("/onboarding");
  await page.getByLabel("FPL Team ID or URL").fill("https://fantasy.premierleague.com/entry/5605168/history");
  await page.getByRole("button", { name: "Verify team" }).click();
  await expect(page.getByText("Test XI")).toBeVisible();
  await page.getByText("Aggressive", { exact: true }).click();
  await page.getByRole("button", { name: "Continue" }).click();
  await page.getByRole("button", { name: "Finish setup" }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  const stored = await page.evaluate(() => ({ teamId: localStorage.getItem("fpl_team_id"), preferences: localStorage.getItem("squadmetric_preferences") }));
  expect(stored.teamId).toBe("5605168");
  expect(JSON.parse(stored.preferences ?? "{}").riskStyle).toBe("aggressive");
});

test("my team is readable and presents the lineup on a visual pitch", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/squad");
  await expect(page.getByRole("heading", { name: "My Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your current lineup" })).toBeVisible();
  await expect(page.getByText("Starting XI projection")).toBeVisible();
  await expect(page.getByText("Substitutes")).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("players page loads, searches clubs, switches view, and exposes player results", async ({ page }) => {
  await page.goto("/stats");
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible();
  await expect(page.getByText("Erling Haaland", { exact: true })).toBeVisible();
  await page.getByPlaceholder("Search player or club…").fill("Arsenal");
  await expect(page.getByText("Bukayo Saka", { exact: true })).toBeVisible();
  await expect(page.getByText("Erling Haaland", { exact: true })).not.toBeVisible();
  await page.getByRole("button", { name: "Cards" }).click();
  await expect(page.getByText("Bukayo Saka", { exact: true })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("players page keeps the official catalog usable while model data refreshes", async ({ page }) => {
  await page.route("**/api/fpl/season-state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...seasonState, recommendations_ready: false, decision_status: "blocked", decision_blockers: [{ code: "bootstrap_drift", message: "Official player data changed." }] }) }));
  await page.goto("/stats");
  await expect(page.getByRole("heading", { name: "Players" })).toBeVisible();
  await expect(page.getByText("Official players, clubs, positions and prices are still available below.", { exact: false })).toBeVisible();
  await expect(page.getByText("Erling Haaland", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Cards" }).click();
  await expect(page.getByText("Refresh needed", { exact: true }).first()).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("routine live FPL changes refresh captaincy without an updating banner", async ({ page }) => {
  await page.route("**/api/fpl/season-state", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ...seasonState,
      recommendations_ready: true,
      decision_status: "ready",
      decision_warnings: [
        "Official FPL now has 604 players; new player records are being onboarded directly.",
        "Latest official fixtures are being applied directly to this request.",
      ],
    }),
  }));

  await page.goto("/captain");

  await expect(page.getByRole("heading", { name: "Who should I captain this week?" })).toBeVisible();
  await expect(page.getByText("Erling Haaland", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Recommendations updating")).not.toBeVisible();
  await expect(page.getByText("Captaincy recommendations are not decision-ready")).not.toBeVisible();
});

test("gameweek plan leads with a clear action and a visual recommended XI", async ({ page }) => {
  await page.goto("/planner");
  await expect(page.getByRole("heading", { name: "2026-27 Initial Squad" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommended opening lineup" })).toBeVisible();
  await expect(page.getByText("Captain, vice-captain and bench order are shown on the pitch.")).toBeVisible();
  await expect(page.getByText("Explore alternatives and build a custom plan")).not.toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("performance evidence is readable and states its limits", async ({ page }) => {
  await page.goto("/proof");
  await expect(page.getByRole("heading", { name: "Performance evidence" })).toBeVisible();
  await expect(page.getByText("The model is tested on matches it was not trained to predict.")).toBeVisible();
  await expect(page.getByText("What it does not prove")).toBeVisible();
  await expect(page.getByText("A guaranteed top-1% finish or a fixed season score.")).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("decision dashboard prioritizes recommendations and progressively discloses evidence", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Your decision dashboard" })).toBeVisible();
  await expect(page.getByText("Primary recommendation", { exact: true })).toBeVisible();
  await expect(page.getByText("This gameweek’s decisions")).toBeVisible();
  await expect(page.getByText("Why SquadMetric prefers this plan")).toBeVisible();
  await expect(page.getByRole("navigation", { name: /navigation/i }).first()).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("decision dashboard stays useful while recommendations await a manual refresh", async ({ page }) => {
  await page.route("**/api/fpl/season-state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...seasonState, recommendations_ready: false, decision_status: "blocked", decision_blockers: [{ code: "bootstrap_drift", message: "Official player data changed." }] }) }));
  await page.route("**/api/predictions/overview", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "recommendations_blocked" } }) }));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Your decision dashboard" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommendations are paused until the data bundle is refreshed." })).toBeVisible();
  await expect(page.getByText("It will not update data automatically", { exact: false })).toBeVisible();
  await expect(page.getByText("Dashboard unavailable")).not.toBeVisible();
  await expect(page.locator('a[href="/stats"]').filter({ hasText: "Browse current official players and prices." })).toBeVisible();
  await expect(page.locator('a[href="/deadline"]').filter({ hasText: "Follow final checks and team-news timing." })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("deadline center is keyboard reachable, secure, and accessible", async ({ page }) => {
  await page.goto("/deadline");
  await expect(page.getByRole("heading", { name: "GW1 Deadline Intelligence" })).toBeVisible();
  await page.keyboard.press("Tab");
  await expect(page.getByRole("link", { name: "Skip to main content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.locator("#main-content")).toBeFocused();

  const response = await page.request.get("/");
  expect(response.headers()["x-content-type-options"]).toBe("nosniff");
  expect(response.headers()["x-frame-options"]).toBe("DENY");

  await expectNoSeriousAccessibilityViolations(page);
});

test("multi-draft workspace saves and compares a named legal draft", async ({ page }) => {
  await page.goto("/drafts");
  await expect(page.getByRole("heading", { name: "2026-27 Draft Workspace" })).toBeVisible();
  await page.getByLabel("Draft name").fill("GW1 contender");
  await page.getByRole("button", { name: "Save" }).click();
  await expect(page.getByRole("cell", { name: /GW1 contender/ })).toBeVisible();
  await expect(page.getByText("Legal", { exact: true }).first()).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("rank mode is opt-in review-only and handles preseason safely", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "2026-27 Post-GW Review" })).toBeVisible();
  await expect(page.getByText("Waiting for the first finalized Gameweek")).toBeVisible();
  await page.getByRole("button", { name: "Rank (review only)" }).click();
  await expect(page.getByText("Not a production optimizer objective.")).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

async function expectNoSeriousAccessibilityViolations(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const serious = result.violations.filter(
    (violation) => violation.impact === "critical" || violation.impact === "serious",
  );
  expect(serious, serious.map((violation) => `${violation.id}: ${violation.help}`).join("\n")).toEqual([]);
}

async function mockApi(route: Route) {
  const url = new URL(route.request().url());
  const json = (body: unknown) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  if (url.pathname === "/api/health") return json({ status: "ok" });
  if (url.pathname === "/api/fpl/current-gw") return json({ current_gw: 1 });
  if (url.pathname === "/api/fpl/season-state") return json(seasonState);
  if (url.pathname === "/api/fpl/team/5605168") return json({ team_name: "Test XI", overall_rank: 1000, total_points: 0, bank_value: 0, current_gw_points: 0, squad_value: 100, free_transfers_available: 1 });
  if (url.pathname === "/api/fpl/team/5605168/squad") return json(players.map((player, index) => ({ ...player, expected_points: player.gw1_points, raw_xp: player.gw1_points, start_adjusted_xp: player.gw1_points, form: 4, current_price: player.price, is_captain: index === 12, is_vice_captain: index === 8 })));
  if (url.pathname === "/api/players") return json([
    { element_id: 101, name: "Erling Haaland", web_name: "Haaland", team: "Man City", team_code: 43, position: "FWD", price: 14, total_points: 0, ppg: 7.2, form: 6.8, start_likelihood: 0.97, value: 0.51, captain_rank_score: 8.4, transfer_rank_score: 7.8, selected_by_percent: 58 },
    { element_id: 102, name: "Bukayo Saka", web_name: "Saka", team: "Arsenal", team_code: 3, position: "MID", price: 10, total_points: 0, ppg: 6.5, form: 6.1, start_likelihood: 0.95, value: 0.65, captain_rank_score: 7.5, transfer_rank_score: 7.3, selected_by_percent: 42 },
  ]);
  if (url.pathname === "/api/player-catalog") return json([
    { element_id: 101, name: "Erling Haaland", web_name: "Haaland", team: "Man City", team_code: 43, position: "FWD", price: 14, total_points: 0, ppg: 7.2, form: 6.8, start_likelihood: 0.97, value: 0.51, captain_rank_score: 0, transfer_rank_score: 0, selected_by_percent: 58, metrics_available: false },
    { element_id: 102, name: "Bukayo Saka", web_name: "Saka", team: "Arsenal", team_code: 3, position: "MID", price: 10, total_points: 0, ppg: 6.5, form: 6.1, start_likelihood: 0.95, value: 0.65, captain_rank_score: 0, transfer_rank_score: 0, selected_by_percent: 42, metrics_available: false },
  ]);
  if (url.pathname === "/api/backtest/accuracy") return json([
    { model: "FPL Intelligence (best)", raw_MAE: 2.1, raw_RMSE: 3.2, raw_beats_naive_MAE: "yes", raw_beats_naive_RMSE: "yes", adjusted_MAE: 1.8, adjusted_RMSE: 2.9, adjusted_beats_naive_MAE: "yes", adjusted_beats_naive_RMSE: "yes" },
    { model: "Naive form", raw_MAE: 2.5, raw_RMSE: 3.6, raw_beats_naive_MAE: "no", raw_beats_naive_RMSE: "no", adjusted_MAE: 2.3, adjusted_RMSE: 3.3, adjusted_beats_naive_MAE: "no", adjusted_beats_naive_RMSE: "no" },
  ]);
  if (url.pathname === "/api/backtest/captaincy") return json([
    { strategy: "FPL Intelligence (best)", total_captain_points: 510, avg_per_gameweek: 13.4 },
    { strategy: "Most popular player", total_captain_points: 472, avg_per_gameweek: 12.4 },
  ]);
  if (url.pathname === "/api/backtest/top10") return json([
    { model: "FPL Intelligence (best)", precision_at_10: 0.16, recall_at_10: 0.16 },
    { model: "Naive form", precision_at_10: 0.1, recall_at_10: 0.1 },
  ]);
  if (url.pathname === "/api/predictions/initial-squad") return json({
    season: "2026-27", bootstrap_hash: "test", rules_version: "2026-27-test", data_cutoff: "2026-08-18T08:00:00Z", model: "production-test", portfolio_version: "portfolio-test", decision_engine_version: "decision-test", horizon: Number(url.searchParams.get("horizon") ?? 8), risk_profile: url.searchParams.get("risk_profile") ?? "balanced", budget: 100, cost: 90, bank: 10, formation: "3-5-2", captain_id: 13, vice_captain_id: 9, expected_gw1_points: 62.4, decision_alternatives: [{ profile: "maximum_points", selected: false, status: "ready", cost: 91, bank: 9, expected_gw1_points: 63, expected_horizon_points: 400, mean_squad_start_probability: 0.9, outfield_bench_start_probability: 0.8, low_reliability_players: [], captain_id: 13, vice_captain_id: 9, changes_from_balanced: 2 }, { profile: "balanced", selected: true, status: "ready", cost: 90, bank: 10, expected_gw1_points: 62.4, expected_horizon_points: 398, mean_squad_start_probability: 0.92, outfield_bench_start_probability: 0.9, low_reliability_players: [], captain_id: 13, vice_captain_id: 9, changes_from_balanced: 0 }, { profile: "safe", selected: false, status: "ready", cost: 89, bank: 11, expected_gw1_points: 61, expected_horizon_points: 395, mean_squad_start_probability: 0.95, outfield_bench_start_probability: 0.95, low_reliability_players: [], captain_id: 13, vice_captain_id: 9, changes_from_balanced: 3 }], decision_audit: { availability_clear: true, low_reliability_starters: [], low_reliability_bench: [], captain_start_probability: 0.97, vice_captain_start_probability: 0.95, vice_captain_fallback_points: 6, first_outfield_cover_id: 4, first_outfield_cover_points: 3, first_outfield_cover_start_probability: 0.9, requires_deadline_refresh: false, reason: "Ready" }, set_piece_summary: { model_version: "test", source_url: null, selected_primary_penalty_takers: [] }, deadline_finalization: null, robustness: null, squad: players.map((player, index) => ({ ...player, player_name: player.name, is_starter: ![1, 4, 10, 14].includes(index), bench_order: [1, 4, 10, 14].includes(index) ? [1, 4, 10, 14].indexOf(index) : null })), assumption: "Uses current official prices, fixtures and availability." });
  if (url.pathname === "/api/predictions/captaincy") return json([
    { element_id: 1, name: "Erling Haaland", web_name: "Haaland", team: "Man City", team_code: 43, position: "FWD", start_likelihood: 0.96, raw_xp: 7.6, expected_points: 7.3, start_adjusted_xp: 7.3, captain_expected_points: 14.6, captaincy_score: 7.3, reasoning: "Best blend of expected points and minutes security.", projection_contract_version: "test-v1" },
    { element_id: 2, name: "Bukayo Saka", web_name: "Saka", team: "Arsenal", team_code: 3, position: "MID", start_likelihood: 0.94, raw_xp: 6.8, expected_points: 6.4, start_adjusted_xp: 6.4, captain_expected_points: 12.8, captaincy_score: 6.4, projection_contract_version: "test-v1" },
  ]);
  if (url.pathname === "/api/predictions/overview") return json({
    player_count: 620,
    captains: [
      { element_id: 1, name: "Erling Haaland", web_name: "Haaland", team: "Man City", position: "FWD", start_likelihood: 0.96, raw_xp: 7.6, expected_points: 7.3, start_adjusted_xp: 7.3, captain_expected_points: 14.6, captaincy_score: 7.3, reasoning: "Best blend of expected points and minutes security.", projection_contract_version: "test-v1" },
      { element_id: 2, name: "Bukayo Saka", web_name: "Saka", team: "Arsenal", position: "MID", start_likelihood: 0.94, raw_xp: 6.8, expected_points: 6.4, start_adjusted_xp: 6.4, captain_expected_points: 12.8, captaincy_score: 6.4, projection_contract_version: "test-v1" },
    ],
    predictions: players.slice(0, 11).map((player, index) => ({ ...player, raw_xp: 5 + index / 10, expected_points: 5 + index / 10, start_adjusted_xp: 5 + index / 10, captain_expected_points: 10 + index / 5, captaincy_score: 5 + index / 10, projection_contract_version: "test-v1" })),
    transfers: [{ element_id: 3, name: "Cole Palmer", team: "Chelsea", position: "MID", price: 10.5, raw_xp: 6.2, expected_points: 6.1, start_adjusted_xp: 6.1, captain_expected_points: 12.2, captaincy_score: 6.1, start_likelihood: 0.93, transfer_rank_score: 8.2, selected_by_percent: 42, projection_contract_version: "test-v1" }],
    fixtures: [],
    gems: [{ element_id: 4, name: "Differential Pick", team: "Fulham", position: "MID", price: 6.5, selected_by_percent: 3.2 }],
    accuracy: [{ model: "SquadMetric best", raw_MAE: 1.1, raw_RMSE: 1.4, raw_beats_naive_MAE: "yes", raw_beats_naive_RMSE: "yes", adjusted_MAE: 0.98, adjusted_RMSE: 1.2, adjusted_beats_naive_MAE: "yes", adjusted_beats_naive_RMSE: "yes" }],
    projection_contract_version: "test-v1",
    data_cutoff: "2026-08-18T08:00:00Z",
  });
  if (url.pathname === "/api/fixtures") return json([]);
  if (url.pathname === "/api/operations/deadline-readiness") return json({
    ready: true,
    season: "2026-27",
    data_cutoff: "2026-08-18T08:00:00Z",
    data_age_hours: 0.1,
    maximum_age_hours: 24,
    stale: false,
    next_gameweek: 1,
    deadline: "2026-08-21T19:00:00Z",
    hours_to_deadline: 72,
    final_refresh_required: false,
    blockers: [],
    decision_lock_ready: false,
    checklist: [
      { key: "fresh_data", passed: true },
      { key: "official_deadline", passed: true },
      { key: "robustness_current", passed: true },
      { key: "set_piece_roles_current", passed: true },
      { key: "shadow_captured", passed: true },
      { key: "final_team_news", passed: false },
    ],
    latest_shadow: { captured_at: "2026-08-18T08:00:00Z", decision_hash: "abcdef1234567890", expected_gw1_points: 60.2, current: true },
    p11: { status: "monitoring", data_ready: true, lock_ready: false, final_news_reviewed: false },
    p12: { model_version: "p12", source_url: "https://example.com", category_coverage: {}, primary_penalty_takers: 20 },
  });
  if (url.pathname === "/api/predictions/draft-workspace") return json({
    season: "2026-27",
    bootstrap_hash: "bootstrap-current",
    fixtures_hash: "fixtures-current",
    rules_version: "2026-27-test",
    data_cutoff: "2026-08-18T08:00:00Z",
    model: "production-test",
    horizon: 8,
    risk_profile: "balanced",
    constraints: { budget: 100, squad_size: 15, starting_xi_size: 11, max_players_per_team: 3, position_counts: { GKP: 2, DEF: 5, MID: 5, FWD: 3 } },
    optimized: { squad: players },
    player_pool: players,
  });
  if (url.pathname === "/api/review/post-gameweek") return json({
    schema_version: "post-gameweek-review-v1",
    team_id: 5605168,
    season: "2026-27",
    official_finalized_gameweeks: [],
    reviewed_gameweeks: 0,
    total_managers: 10_000_000,
    summary: { net_points: 0, hit_cost: 0, points_on_bench: 0, decision_evidence_gameweeks: 0, decision_regret: 0, latest_overall_rank: null },
    rank_mode: { available: false, validated_for_recommendations: false, default_mode: "points", reason: "Rank mode is an optional review lens." },
    gameweeks: [],
    automatic_fpl_actions: false,
  });
  return route.fulfill({ status: 404, contentType: "application/json", body: JSON.stringify({ detail: "not mocked" }) });
}
