import type { SupabaseClient } from "@supabase/supabase-js";
import { parseSavedDrafts, type SavedDraft } from "./draftWorkspace";
import type { DecisionCenterResponse } from "./types";
import { createSupabaseBrowserClient } from "./supabase/client";
import { applyAuthoritativeTeamId, deriveAccountAccess } from "./accountAccess";
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
  provisionalSquad: "squadmetric_provisional_squad_v1",
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

export type AccountHydrationResult = {
  authenticated: boolean;
  requiresConsent: boolean;
  requiresOnboarding: boolean;
  teamId: number | null;
};

export async function hydrateAccountStorage(): Promise<AccountHydrationResult> {
  const supabase = createSupabaseBrowserClient();
  if (!supabase || typeof window === "undefined") {
    return { authenticated: false, requiresConsent: false, requiresOnboarding: false, teamId: null };
  }

  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) {
    return { authenticated: false, requiresConsent: false, requiresOnboarding: false, teamId: null };
  }
  const userId = userData.user.id;
  const markerKey = `squadmetric_account_hydrated_v3:${userId}`;
  const firstHydration = window.localStorage.getItem(markerKey) !== "true";

  const [profileResult, teamResult, preferencesResult, draftsResult, favoritesResult] = await Promise.all([
    supabase.from("profiles").select("onboarding_completed, terms_accepted_at, terms_version, privacy_version").eq("user_id", userId).maybeSingle(),
    supabase.from("fpl_team_links").select("team_id").eq("user_id", userId).maybeSingle(),
    supabase.from("user_preferences").select("risk_style, alternative_style, deadline_reminders, email_notifications, show_bench_players, compact_table_rows, objective_mode").eq("user_id", userId).maybeSingle(),
    supabase.from("saved_drafts").select("id, payload, updated_at").eq("user_id", userId),
    supabase.from("favorite_players").select("player_id, player_name").eq("user_id", userId),
  ]);

  const failure = profileResult.error ?? teamResult.error ?? preferencesResult.error ?? draftsResult.error ?? favoritesResult.error;
  if (failure) throw failure;

  const localDrafts = readSavedDrafts();
  const remoteDrafts = parseSavedDrafts((draftsResult.data ?? []).map((row) => row.payload));
  const localWatchlist = readWatchlist();
  const remoteWatchlist = (favoritesResult.data ?? []).map((row) => String(row.player_name)).filter(Boolean);
  const localPreferences = firstHydration ? readLocalPreferencePatch() : {};

  if (firstHydration) {
    const mergedDrafts = mergeDrafts(remoteDrafts, localDrafts);
    const mergedWatchlist = [...new Set([...remoteWatchlist, ...localWatchlist])];
    writeSavedDraftsLocal(mergedDrafts);
    writeWatchlistLocal(mergedWatchlist);
    await Promise.all([
      syncDrafts(supabase, userId, mergedDrafts),
      syncFavoriteNames(supabase, userId, mergedWatchlist, favoritesResult.data ?? []),
      syncLocalPreferences(supabase, userId, localPreferences),
    ]);
  } else {
    writeSavedDraftsLocal(remoteDrafts);
    writeWatchlistLocal(remoteWatchlist);
  }

  // Team ownership is account-authoritative. Never attach a stale Team ID from a
  // previous anonymous browser session (or another account) to a new user.
  applyAuthoritativeTeamId(window.localStorage, teamResult.data?.team_id);
  if (preferencesResult.data) hydratePreferences(preferencesResult.data);
  if (firstHydration) applyPreferencePatchLocally(localPreferences);
  window.localStorage.setItem(markerKey, "true");

  const hasProvisionalSquad = Boolean(window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.provisionalSquad));
  const access = deriveAccountAccess(profileResult.data, teamResult.data?.team_id, hasProvisionalSquad);
  return {
    authenticated: true,
    ...access,
  };
}

export function readSavedDrafts(): SavedDraft[] {
  if (typeof window === "undefined") return [];
  try {
    return parseSavedDrafts(JSON.parse(window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.drafts) ?? "[]"));
  } catch {
    return [];
  }
}

export function persistSavedDrafts(drafts: SavedDraft[]) {
  writeSavedDraftsLocal(drafts);
  void withUser((supabase, userId) => syncDrafts(supabase, userId, drafts)).catch(() => undefined);
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
  writeWatchlistLocal(names);
  void withUser(async (supabase, userId) => {
    await supabase.from("favorite_players").delete().eq("user_id", userId);
    const rows = players.map((player) => ({
      user_id: userId,
      player_id: Number(player.element_id) > 0 ? Number(player.element_id) : syntheticPlayerId(player.name),
      player_name: player.name,
    }));
    if (rows.length) {
      const { error } = await supabase.from("favorite_players").upsert(rows);
      if (error) throw error;
    }
  }).catch(() => undefined);
}

export function savePreferencePatch(patch: PreferencePatch) {
  applyPreferencePatchLocally(patch);
  void withUser(async (supabase, userId) => {
    const row = preferenceRow(userId, patch);
    const { error } = await supabase.from("user_preferences").upsert(row);
    if (error) throw error;
  }).catch(() => undefined);
}

export async function disconnectAccountTeam() {
  if (typeof window !== "undefined") {
    const teamId = window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.teamId);
    if (teamId) clearManagerStateOverride(teamId);
    window.localStorage.removeItem(ACCOUNT_STORAGE_KEYS.teamId);
  }
  await withUser(async (supabase, userId) => {
    const { error } = await supabase.from("fpl_team_links").delete().eq("user_id", userId);
    if (error) throw error;
  });
}

export async function persistWeeklyRecommendation(data: DecisionCenterResponse) {
  if (data.status !== "ready" || !data.recommendation) return;
  const decisionHash = await sha256(stableStringify({
    teamId: data.team_id,
    gameweek: data.gameweek,
    rulesVersion: data.rules_version,
    recommendation: data.recommendation,
  }));
  await withUser(async (supabase, userId) => {
    const { error } = await supabase.from("weekly_recommendations").upsert({
      user_id: userId,
      season: seasonFromRules(data.rules_version),
      gameweek: data.gameweek,
      payload: data,
      decision_hash: decisionHash,
      model_versions: {
        portfolio: data.portfolio_version,
        decision_engine: data.decision_engine_version,
        transfer: data.transfer_model,
        captain: data.captain_model,
        chip: data.chip_model,
      },
      data_cutoff: data.data_cutoff,
    }, { onConflict: "user_id,season,gameweek,decision_hash" });
    if (error) throw error;
  });
}

export async function persistDecisionResponse(data: DecisionCenterResponse, response: DecisionResponse) {
  const localRow = { gameweek: data.gameweek, response, savedAt: new Date().toISOString(), recommendation: data.recommendation };
  const existing = readJsonArray(ACCOUNT_STORAGE_KEYS.decisionHistory);
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.decisionHistory, JSON.stringify([localRow, ...existing].slice(0, 200)));
  await withUser(async (supabase, userId) => {
    const { error } = await supabase.from("decision_history").insert({
      user_id: userId,
      season: seasonFromRules(data.rules_version),
      gameweek: data.gameweek,
      decision_type: "squad",
      decision_payload: { response, recommendation: data.recommendation, state_before: data.state_before },
    });
    if (error) throw error;
  });
}

export async function exportAccountData() {
  const local = Object.fromEntries(Object.values(ACCOUNT_STORAGE_KEYS).map((key) => [key, window.localStorage.getItem(key)]));
  const supabase = createSupabaseBrowserClient();
  if (!supabase) return { exportedAt: new Date().toISOString(), storage: "local", local };
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) return { exportedAt: new Date().toISOString(), storage: "local", local };
  const userId = userData.user.id;
  const tables = ["profiles", "fpl_team_links", "user_preferences", "saved_drafts", "weekly_recommendations", "decision_history", "favorite_players"] as const;
  const entries = await Promise.all(tables.map(async (table) => {
    const result = await supabase.from(table).select("*").eq("user_id", userId);
    if (result.error) throw result.error;
    return [table, result.data] as const;
  }));
  return { exportedAt: new Date().toISOString(), storage: "account", email: userData.user.email, data: Object.fromEntries(entries), local };
}

function writeSavedDraftsLocal(drafts: SavedDraft[]) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.drafts, JSON.stringify(drafts));
}

function writeWatchlistLocal(names: string[]) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.watchlist, JSON.stringify(names));
}

async function syncDrafts(supabase: SupabaseClient, userId: string, drafts: SavedDraft[]) {
  const { data: existing, error: readError } = await supabase.from("saved_drafts").select("id").eq("user_id", userId);
  if (readError) throw readError;
  const wanted = new Set(drafts.map((draft) => draft.id));
  const stale = (existing ?? []).map((row) => String(row.id)).filter((id) => !wanted.has(id));
  if (stale.length) {
    const { error } = await supabase.from("saved_drafts").delete().eq("user_id", userId).in("id", stale);
    if (error) throw error;
  }
  if (!drafts.length) return;
  const { error } = await supabase.from("saved_drafts").upsert(drafts.map((draft) => ({
    id: draft.id,
    user_id: userId,
    name: draft.name,
    season: seasonFromRules(draft.rulesVersion),
    payload: draft,
    created_at: draft.createdAt,
    updated_at: draft.updatedAt,
  })), { onConflict: "user_id,id" });
  if (error) throw error;
}

async function syncFavoriteNames(supabase: SupabaseClient, userId: string, names: string[], remote: Array<{ player_id: number; player_name: string }>) {
  const idsByName = new Map(remote.map((row) => [row.player_name, row.player_id]));
  const rows = names.map((name, index) => ({ user_id: userId, player_id: idsByName.get(name) ?? 2_000_000_000 - index, player_name: name }));
  if (!rows.length) return;
  const { error } = await supabase.from("favorite_players").upsert(rows);
  if (error) throw error;
}

async function syncLocalPreferences(supabase: SupabaseClient, userId: string, patch: PreferencePatch) {
  if (!Object.keys(patch).length) return;
  const { error } = await supabase.from("user_preferences").upsert(preferenceRow(userId, patch));
  if (error) throw error;
}

function readLocalPreferencePatch(): PreferencePatch {
  const onboarding = readJsonObject(ACCOUNT_STORAGE_KEYS.onboardingPreferences);
  const patch: PreferencePatch = {};
  if (["safe", "balanced", "aggressive"].includes(String(onboarding.riskStyle))) patch.riskStyle = onboarding.riskStyle as PreferencePatch["riskStyle"];
  if (["popular", "differential", "both"].includes(String(onboarding.alternativeStyle))) patch.alternativeStyle = onboarding.alternativeStyle as PreferencePatch["alternativeStyle"];
  if (typeof onboarding.deadlineReminders === "boolean") patch.deadlineReminders = onboarding.deadlineReminders;
  if (typeof onboarding.emailNotifications === "boolean") patch.emailNotifications = onboarding.emailNotifications;
  if (window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.showBenchPlayers) !== null) patch.showBenchPlayers = localBoolean(ACCOUNT_STORAGE_KEYS.showBenchPlayers, true);
  if (window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.compactTableRows) !== null) patch.compactTableRows = localBoolean(ACCOUNT_STORAGE_KEYS.compactTableRows, false);
  const objective = window.localStorage.getItem(ACCOUNT_STORAGE_KEYS.objectiveMode);
  if (objective === "points" || objective === "rank") patch.objectiveMode = objective;
  return patch;
}

function hydratePreferences(row: Record<string, unknown>) {
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.onboardingPreferences, JSON.stringify({
    riskStyle: row.risk_style,
    alternativeStyle: row.alternative_style,
    deadlineReminders: row.deadline_reminders,
    emailNotifications: row.email_notifications,
  }));
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.showBenchPlayers, String(row.show_bench_players));
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.compactTableRows, String(row.compact_table_rows));
  window.localStorage.setItem(ACCOUNT_STORAGE_KEYS.objectiveMode, row.objective_mode === "rank" ? "rank" : "points");
}

function applyPreferencePatchLocally(patch: PreferencePatch) {
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

function preferenceRow(userId: string, patch: PreferencePatch) {
  return {
    user_id: userId,
    ...(patch.riskStyle ? { risk_style: patch.riskStyle } : {}),
    ...(patch.alternativeStyle ? { alternative_style: patch.alternativeStyle } : {}),
    ...(patch.deadlineReminders !== undefined ? { deadline_reminders: patch.deadlineReminders } : {}),
    ...(patch.emailNotifications !== undefined ? { email_notifications: patch.emailNotifications } : {}),
    ...(patch.showBenchPlayers !== undefined ? { show_bench_players: patch.showBenchPlayers } : {}),
    ...(patch.compactTableRows !== undefined ? { compact_table_rows: patch.compactTableRows } : {}),
    ...(patch.objectiveMode ? { objective_mode: patch.objectiveMode } : {}),
  };
}

async function withUser(action: (supabase: SupabaseClient, userId: string) => Promise<void>) {
  const supabase = createSupabaseBrowserClient();
  if (!supabase) return;
  const { data } = await supabase.auth.getUser();
  if (!data.user) return;
  await action(supabase, data.user.id);
}

function mergeDrafts(remote: SavedDraft[], local: SavedDraft[]) {
  const drafts = new Map(remote.map((draft) => [draft.id, draft]));
  for (const draft of local) {
    const current = drafts.get(draft.id);
    if (!current || Date.parse(draft.updatedAt) > Date.parse(current.updatedAt)) drafts.set(draft.id, draft);
  }
  return [...drafts.values()].sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt));
}

function seasonFromRules(value?: string | null): string {
  return value?.match(/20\d{2}[-/]\d{2,4}/)?.[0].replace("/", "-") ?? "2026-27";
}

function syntheticPlayerId(name: string): number {
  let hash = 0;
  for (const character of name) hash = (hash * 31 + character.charCodeAt(0)) >>> 0;
  return 1_000_000_000 + (hash % 1_000_000_000);
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

function localBoolean(key: string, fallback: boolean) {
  const value = window.localStorage.getItem(key);
  return value === null ? fallback : value === "true";
}

function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value as Record<string, unknown>).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${stableStringify(item)}`).join(",")}}`;
  return JSON.stringify(value);
}

async function sha256(value: string) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}
