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
const decisionPlayers = players.map((player) => ({
  element_id: player.element_id,
  name: player.name,
  web_name: player.web_name,
  team: player.team,
  team_code: player.team_code,
  position: player.position,
  price: player.price,
  expected_points: player.gw1_points,
  start_likelihood: player.start_likelihood,
  blank: false,
  double: false,
}));
const decisionStarters = [0, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13].map((index) => decisionPlayers[index]);
const decisionBench = [5, 6, 14, 1].map((index) => decisionPlayers[index]);

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

test("my team is readable, interactive, and offers a best-XI view", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/squad");
  await expect(page.getByRole("heading", { name: "My Team" })).toBeVisible();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Your lineup" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Current XI" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Substitutes")).toBeVisible();
  await page.getByRole("button", { name: "Open P1 details", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Player 1", exact: true })).toBeVisible();
  await expect(page.getByText("3 most recent completed gameweeks")).toBeVisible();
  const rangePicker = page.getByLabel("Chart gameweek range");
  await expect(rangePicker.getByRole("button", { name: "3", exact: true })).toBeVisible();
  await expect(rangePicker.getByRole("button", { name: "5", exact: true })).toHaveCount(0);
  await expect(rangePicker.getByRole("button", { name: "10", exact: true })).toHaveCount(0);
  await expect(page.getByText("GW38", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Next fixtures" })).toBeVisible();
  await expect(page.getByText("GW5", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close", exact: true }).click();
  await page.getByRole("button", { name: "Best XI", exact: true }).click();
  await expect(page.getByRole("button", { name: "Best XI" })).toHaveAttribute("aria-pressed", "true");
  await expect(page.getByText("Best GW1 lineup", { exact: true })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("my team offers useful routes when prediction data needs a refresh", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.route("**/api/fpl/season-state", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      ...seasonState,
      recommendations_ready: false,
      decision_status: "blocked",
      decision_blockers: [{ code: "finalized_gameweek_missing", message: "GW4 is finalized, but predictions use results only through GW3." }],
    }),
  }));

  await page.goto("/dashboard");

  await expect(page.getByRole("heading", { name: "My Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommendations are paused until the data bundle is refreshed." })).toBeVisible();
  await expect(page.getByRole("link", { name: /Players Browse current official/ })).toBeVisible();
  await expect(page.getByRole("link", { name: /This Week See the latest saved/ })).toBeVisible();
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

test("legacy captain route converges on the weekly plan", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
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

  await expect(page).toHaveURL(/\/decisions$/);
  await expect(page.getByRole("heading", { name: "This Week · GW1" })).toBeVisible();
  await expect(page.getByText("P13", { exact: true })).toBeVisible();
  await expect(page.getByText("Recommendations updating")).not.toBeVisible();
  await expect(page.getByText("Captaincy recommendations are not decision-ready")).not.toBeVisible();
});

test("legacy planner route converges on the weekly plan", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/planner");
  await expect(page).toHaveURL(/\/decisions$/);
  await expect(page.getByRole("heading", { name: "This Week · GW1" })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("personal plan explains package funding and accepts corrected manager state", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/decisions");

  await expect(page.getByRole("heading", { name: "This Week · GW1" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Transfer package" })).toBeVisible();
  await expect(page.getByText("P8 to Value releases £2.0m, helping fund P9 to Star.")).toBeVisible();
  await expect(page.getByText("Reconstructed from public FPL history.")).toBeVisible();
  await expect(page.getByText("First substitute", { exact: true })).toBeVisible();
  await expect(page.getByText("P6", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Correct this" }).click();
  await page.getByLabel("Money in bank (£m)").fill("2.5");
  await page.getByLabel("Free transfers").selectOption("3");
  await page.getByRole("button", { name: "Recalculate" }).click();
  await expect(page.getByRole("heading", { name: "This Week · GW1" })).toBeVisible();
  const saved = await page.evaluate(() => JSON.parse(localStorage.getItem("squadmetric_manager_state_v1:5605168") ?? "null"));
  expect(saved).toEqual({ bank: 2.5, freeTransfers: 3 });
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
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "My Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your squad is B+" })).toBeVisible();
  await expect(page.getByText("Best improvement", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "View this week’s plan" })).toBeVisible();
  await expect(page.getByText(/Rating score/)).toHaveCount(0);
  await expect(page.getByRole("navigation", { name: /navigation/i }).first()).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("decision dashboard stays useful while recommendations await a prediction refresh", async ({ page }) => {
  await page.route("**/api/fpl/season-state", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ...seasonState, recommendations_ready: false, decision_status: "blocked", decision_blockers: [{ code: "bootstrap_drift", message: "Official player data changed." }] }) }));
  await page.route("**/api/predictions/overview", (route) => route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: { code: "recommendations_blocked" } }) }));
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "My Team" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Recommendations are paused until the data bundle is refreshed." })).toBeVisible();
  await expect(page.getByText("Your team and official FPL information remain available", { exact: false })).toBeVisible();
  await expect(page.getByText("Dashboard unavailable")).not.toBeVisible();
  await expect(page.locator('a[href="/stats"]').filter({ hasText: "Browse current official players and prices." })).toBeVisible();
  await expect(page.locator('a[href="/decisions"]').filter({ hasText: "See the latest saved weekly plan." })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("legacy deadline route redirects and the app remains keyboard reachable", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/deadline");
  await expect(page).toHaveURL(/\/decisions$/);
  await expect(page.getByRole("heading", { name: "This Week · GW1" })).toBeVisible();
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

test("results page handles preseason safely without an objective switch", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "Your Results", exact: true })).toBeVisible();
  await expect(page.getByText("Waiting for the first finalized gameweek")).toBeVisible();
  await expect(page.getByRole("button", { name: /Rank/ })).toHaveCount(0);
  await expectNoSeriousAccessibilityViolations(page);
});

test("navigation exposes one simple signed-in product structure", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/dashboard");
  const navigation = page.getByRole("navigation", { name: (page.viewportSize()?.width ?? 1280) < 1024 ? "Mobile navigation" : "Primary navigation" });
  await expect(navigation.getByRole("link", { name: "My Team", exact: true })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "This Week", exact: true })).toBeVisible();
  await expect(navigation.getByRole("link", { name: "Players", exact: true })).toBeVisible();
  await expect(navigation.getByText("Transfer planner", { exact: true })).toHaveCount(0);
  await expect(navigation.getByText("Draft workspace", { exact: true })).toHaveCount(0);
  await navigation.getByText("More", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Fixtures", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Chip guide", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Your results", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Settings", exact: true })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("fixtures keep squad and team targets one click apart", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/fixtures");

  await expect(page.getByRole("heading", { name: "Your squad's upcoming fixtures" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Best teams to target" })).toHaveCount(0);

  await page.getByRole("button", { name: "Team targets" }).click();
  await expect(page.getByRole("heading", { name: "Best teams to target" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your squad's upcoming fixtures" })).toHaveCount(0);

  await page.getByRole("button", { name: "My squad" }).click();
  await expect(page.getByRole("heading", { name: "Your squad's upcoming fixtures" })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);
});

test("chip guide is readable and legacy decision routes have one destination", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("fpl_team_id", "5605168"));
  await page.goto("/chips");
  await expect(page.getByRole("heading", { name: "Chip Guide" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Your chips" })).toBeVisible();
  await expect(page.getByText("recommendations are not personalized", { exact: false })).toBeVisible();
  await expectNoSeriousAccessibilityViolations(page);

  await page.goto("/transfers");
  await expect(page).toHaveURL(/\/decisions$/);
  await page.goto("/compare");
  await expect(page).toHaveURL(/\/stats$/);
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
  if (url.pathname === "/api/chip-opportunities") return json({ status: "ready", target_gameweek: 2, horizon_end_gameweek: 8, message: "Ready", model: "fixture-opportunity-v1", data_cutoff: "2026-08-18", personalized: false, automatic_chip_actions: false, opportunities: [{ chip_type: "3xc", chip: "Triple Captain", recommended_gameweek: 4, headline: "Consider Haaland in GW4", summary: "Strong attacking form meets a vulnerable defence.", confidence: "high", why_now: ["High projected involvement", "Opponent allows strong chances"], why_wait: "A double gameweek may offer a stronger ceiling.", primary_candidate: { gameweek: 4, player: "Haaland" }, alternatives: [] }] });
  if (url.pathname === "/api/fpl/team/5605168/chips" || url.pathname === "/api/fpl/chips") return json({ status: "ready", team_id: 5605168, message: "Ready", chips: [{ key: "wc1", chip_type: "wildcard", name: "Wildcard 1", subtitle: "first half", number: 1, start_event: 1, stop_event: 19, status: "available" }] });
  if (url.pathname === "/api/fpl/team/5605168") return json({ team_name: "Test XI", overall_rank: 1000, total_points: 0, bank_value: 0, current_gw_points: 0, squad_value: 100, free_transfers_available: 1 });
  if (url.pathname === "/api/fpl/team/5605168/squad") return json(players.map((player, index) => ({ ...player, expected_points: player.gw1_points, raw_xp: player.gw1_points, start_adjusted_xp: player.gw1_points, form: 4, current_price: player.price, is_captain: index === 12, is_vice_captain: index === 8 })));
  if (url.pathname === "/api/fpl/team/5605168/roster") return json(players.map((player, index) => ({ ...player, expected_points: null, raw_xp: 0, start_adjusted_xp: null, start_likelihood: null, form: 4, current_price: player.price, is_captain: index === 12, is_vice_captain: index === 8 })));
  if (url.pathname.match(/^\/api\/players\/.*\/history$/)) return json([
    { element_id: 1, gw: 1, price: 6.0, total_points: 2, minutes: 90, selected_by_percent: 5 },
    { element_id: 1, gw: 2, price: 6.0, total_points: 5, minutes: 90, selected_by_percent: 6 },
    { element_id: 1, gw: 3, price: 6.1, total_points: 7, minutes: 90, selected_by_percent: 7 },
    { element_id: 1, gw: 4, price: 6.1, total_points: 4, minutes: 90, selected_by_percent: 8 },
  ]);
  if (url.pathname === "/api/players") return json([
    { element_id: 1, name: "Player 1", web_name: "P1", team: "T1", team_code: 100, position: "GKP", price: 6, total_points: 18, ppg: 4.5, form: 4, start_likelihood: 0.9, value: 0.75, captain_rank_score: 4.5, transfer_rank_score: 4.1, selected_by_percent: 8 },
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
  if (url.pathname === "/api/predictions/decision-center") return json({
    status: "ready",
    message: "Complete personalized weekly decision from one legal planner state.",
    team_id: 5605168,
    season_state: "in_season",
    gameweek: 1,
    horizon: Number(url.searchParams.get("horizon") ?? 3),
    deadline: "2026-08-21T19:00:00Z",
    rating: {
      grade: "B+",
      score: 90,
      after_grade: "A-",
      after_score: 92,
      horizon: 3,
      projected_points: 185,
      recommended_projected_points: 190,
      benchmark_points: 200,
      gap_to_best: 15,
      budget: 100.5,
      provisional: false,
      summary: "A strong squad with one linked upgrade path.",
      factors: [{ label: "Three-gameweek strength", status: "strong", detail: "185 projected points over the next three gameweeks." }],
      method: "Compared with the strongest legal same-budget squad found.",
    },
    manager_state_confirmation: {
      bank_source: url.searchParams.has("bank_override") ? "user_override" : "public_history",
      free_transfers_source: url.searchParams.has("free_transfers_override") ? "user_override" : "public_history_inference",
      can_override: true,
    },
    state_before: {
      bank: Number(url.searchParams.get("bank_override") ?? 0.5),
      free_transfers: Number(url.searchParams.get("free_transfers_override") ?? 2),
      remaining_chips: [],
      used_chips: [],
    },
    current_lineup: {
      starting_xi: decisionStarters,
      bench_order: decisionBench,
      captain_id: 13,
      vice_captain_id: 8,
    },
    recommendation: {
      transfer_action: "make_2_transfers",
      transfers: [
        { outgoing_id: 8, outgoing_name: "P8", incoming_id: 108, incoming_name: "Value", projected_gain: -0.5, hit_cost: 0, outgoing_price: 8, incoming_price: 6, bank_effect: 2 },
        { outgoing_id: 9, outgoing_name: "P9", incoming_id: 109, incoming_name: "Star", projected_gain: 4, hit_cost: 0, outgoing_price: 6, incoming_price: 8, bank_effect: -2 },
      ],
      transfer_count: 2,
      hit_recommended: false,
      hit_cost: 0,
      bank_before: 0.5,
      bank_after: 0.5,
      free_transfers_after: 0,
      funds_released: 2,
      funds_spent: 2,
      funding_explanation: "P8 to Value releases £2.0m, helping fund P9 to Star.",
      future_plan: [{ gameweek: 2, transfers: [], transfer_count: 0, hit_cost: 0, expected_points: 61, net_expected_points: 61, bank_before: 0.5, bank_after: 0.5, free_transfers_before: 1, free_transfers_after: 2, funds_released: 0, funds_spent: 0 }],
      chip_action: "save",
      chip_key: "none",
      starting_xi: decisionStarters,
      bench_order: decisionBench,
      captain_id: 13,
      vice_captain_id: 8,
      expected_gameweek_points: 62,
      expected_horizon_points: 190,
      gain_vs_no_action: 5,
      future_opportunity_cost: 0,
      uncertainty_penalty: 0.3,
      downside_range: { low: 61, high: 63, method: "test" },
      confidence: "high",
      confidence_basis: { search_score_margin: 2, uncertainty_penalty: 0.3 },
      reason: "Best linked package.",
    },
    no_action: { expected_gameweek_points: 60, expected_horizon_points: 185, starting_ids: decisionStarters.map((player) => player.element_id), captain_id: 13, vice_captain_id: 8, reason: "Roll." },
    alternatives: [],
  });
  if (url.pathname === "/api/fixtures") return json([]);
  if (url.pathname === "/api/fixtures/ticker") return json([
    { team: "T1", team_short: "T1", range: 3, fixtures: [
      { gw: 5, opponent: "T2", home: true, difficulty: 2 },
      { gw: 6, opponent: "T3", home: false, difficulty: 3 },
      { gw: 7, opponent: "T4", home: true, difficulty: 4 },
    ] },
  ]);
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
