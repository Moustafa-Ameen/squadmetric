import { parseSavedDrafts, type SavedDraft } from "./draftWorkspace";
import type { DecisionCenterResponse } from "./types";
import { clearManagerStateOverride } from "./managerState";

export const ACCOUNT_STORAGE_KEYS = {
  drafts: "fpl_intelligence_drafts_v1",
  watchlist: "watchlist",
  onboardingPreferences: "squadmetric_preferences",
  teamId: "fpl_team_id",
  showBenchPlayers: "show_bench_players",
  compactTableRows: "compact_table_rows",
  objectiveMode: "fpl_decision_objective_mode",
  decisionHistory: "squadmetric_decision_history_v1",
  weeklyRecommendations: "squadmetric_weekly_recommendations_v1",
  provisionalSquad: "squadmetric_provisional_squad_v1",
  guestDemo: "squadmetric_guest_demo_v1",
} as const;

type PreferencePatch = {
  riskStyle?: "safe" | "balanced" | "aggressive";
  alternativeStyle?: "popular" | "differential" | "both";
  deadlineReminders?: boolean;
  emailNotifications?: boolean;
  showBenchPlayers?: boolean;
  compactTableRows?: boolean;
  objectiveMode?: "points" | "rank";
};

type DecisionResponse = "accepted" | "rejected";

export function readSavedDrafts(): SavedDraft[] {
  if (typeof window === "undefined") return [];
  try {
    return parseSavedDrafts(JSON.parse(window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.drafts) ?? "[]"));
  } catch {
    return [];
  }
}

export function persistSavedDrafts(drafts: SavedDraft[]) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.drafts, JSON.stringify(drafts));
}

export function readWatchlist(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const value = JSON.parse(window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.watchlist) ?? "[]");
    return Array.isArray(value) ? value.filter((name): name is string => typeof name === "string") : [];
  } catch {
    return [];
  }
}

export function persistWatchlist(players: Array<{ name: string; element_id?: number | null }>) {
  const names = [...new Set(players.map((player) => player.name).filter(Boolean))];
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.watchlist, JSON.stringify(names));
}

export function savePreferencePatch(patch: PreferencePatch) {
  const onboarding = readJsonObject(ACCOUNT_STORAGE_KEYS.onboardingPreferences);
  const next = {
    ...onboarding,
    ...(patch.riskStyle ? { riskStyle: patch.riskStyle } : {}),
    ...(patch.alternativeStyle ? { alternativeStyle: patch.alternativeStyle } : {}),
    ...(patch.deadlineReminders !== undefined ? { deadlineReminders: patch.deadlineReminders } : {}),
    ...(patch.emailNotifications !== undefined ? { emailNotifications: patch.emailNotifications } : {}),
  };
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.onboardingPreferences, JSON.stringify(next));
  if (patch.showBenchPlayers !== undefined) window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.showBenchPlayers, String(patch.showBenchPlayers));
  if (patch.compactTableRows !== undefined) window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.compactTableRows, String(patch.compactTableRows));
  if (patch.objectiveMode) window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.objectiveMode, patch.objectiveMode);
}

export async function disconnectAccountTeam() {
  if (typeof window === "undefined") return;
  const teamId = window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.teamId);
  if (teamId) clearManagerStateOverride(teamId);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.teamId);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.guestDemo);
  window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.provisionalSquad);
}

export function isGuestDemoMode(): boolean {
  if (typeof window === "undefined") return false;
  const guestMode = window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.guestDemo) === "true";
  if (guestMode) {
    // Migrate the original guest implementation, which reused a real manager's Team ID.
    window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.teamId);
  }
  return guestMode;
}

export async function persistWeeklyRecommendation(data: DecisionCenterResponse) {
  if (data.status !== "ready" || !data.recommendation || typeof window === "undefined") return;
  const existing = readJsonArray(ACCOUNT_STORAGE_KEYS.weeklyRecommendations);
  const row = {
    teamId: data.team_id,
    gameweek: data.gameweek,
    savedAt: new Date().toISOString(),
    data,
  };
  const withoutSameDecision = existing.filter((item) => {
    if (!item || typeof item !== "object") return true;
    const record = item as Record<string, unknown>;
    return record.teamId !== data.team_id || record.gameweek !== data.gameweek;
  });
  window.localStorage.setItem(
    ACCOUNT_STORAGE_KEYS.weeklyRecommendations,
    JSON.stringify([row, ...withoutSameDecision].slice(0, 20)),
  );
}

export async function persistDecisionResponse(data: DecisionCenterResponse, response: DecisionResponse) {
  const localRow = { gameweek: data.gameweek, response, savedAt: new Date().toISOString(), recommendation: data.recommendation };
  const existing = readJsonArray(ACCOUNT_STORAGE_KEYS.decisionHistory);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.decisionHistory, JSON.stringify([localRow, ...existing].slice(0, 200)));
}

export async function exportAccountData() {
  const local = Object.fromEntries(
    Object.values(ACCOUNT_STORAGE_KEYS).map((key) => [key, window.localStorage.getItem(key)]),
  );
  return { exportedAt: new Date().toISOString(), storage: "browser", local };
}

function readJsonObject(key: string): Record<string, unknown> {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) ?? "{}");
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  } catch {
    return {};
  }
}

function readJsonArray(key: string): unknown[] {
  try {
    const value = JSON.parse(window.localStorage.getItem(key) ?? "[]");
    return Array.isArray(value) ? value : [];
  } catch {
    return [];
  }
}
