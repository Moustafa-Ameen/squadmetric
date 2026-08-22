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

test("decision dashboard prioritizes recommendations and progressively discloses evidence", async ({ page }) => {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Your decision dashboard" })).toBeVisible();
  await expect(page.getByText("Primary recommendation", { exact: true })).toBeVisible();
  await expect(page.getByText("This gameweek’s decisions")).toBeVisible();
  await expect(page.getByText("Why SquadMetric prefers this plan")).toBeVisible();
  await expect(page.getByRole("navigation", { name: /navigation/i }).first()).toBeVisible();
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
