import type {
  AccuracyResult,
  BacktestResult,
  CaptainPick,
  ChipStatusResponse,
  ChipTipsResponse,
  DraftWorkspaceResponse,
  DecisionCenterResponse,
  DeadlineReadinessResponse,
  Fixture,
  FixtureTick,
  InitialSquadResponse,
  OverviewResponse,
  Player,
  PlayerComparisonResponse,
  PlayerHistoryPoint,
  PlannerResponse,
  PostGameweekReviewResponse,
  SeasonState,
  SquadPlayer,
  TeamData,
  Top10Metric,
  TransferTarget,
} from "./types";

const CLIENT_API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "";
const SERVER_API_BASE =
  process.env.FPL_API_SERVER_URL ??
  process.env.NEXT_PUBLIC_API_BASE_URL ??
  "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
    public readonly code: string,
    public readonly detail: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export function apiErrorCode(error: unknown): string | null {
  return error instanceof ApiError ? error.code : null;
}

async function fetchJson<T>(
  path: string,
  options: RequestInit & { next?: { revalidate: number } } = { next: { revalidate: 300 } },
): Promise<T> {
  const base = typeof window === "undefined" ? SERVER_API_BASE : CLIENT_API_BASE;
  const response = await fetch(`${base}${path}`, options);
  if (!response.ok) {
    let detail: unknown = null;
    try {
      const body = (await response.json()) as { detail?: unknown };
      detail = body.detail ?? body;
    } catch {
      detail = null;
    }
    const structured = detail && typeof detail === "object" ? detail as Record<string, unknown> : null;
    const message =
      (structured && typeof structured.message === "string" && structured.message) ||
      (typeof detail === "string" && detail) ||
      `API request failed: ${path}`;
    const code =
      (structured && typeof structured.code === "string" && structured.code) ||
      `http_${response.status}`;
    throw new ApiError(message, response.status, code, detail);
  }
  return response.json() as Promise<T>;
}

export async function getCurrentGameweek(): Promise<{ current_gw: number | null }> {
  return fetchJson("/api/fpl/current-gw");
}

export async function getSeasonState(): Promise<SeasonState> {
  return fetchJson("/api/fpl/season-state", { cache: "no-store" });
}

export async function getPlayers(params?: {
  position?: string;
  sort_by?: string;
  limit?: number;
}): Promise<Player[]> {
  const search = new URLSearchParams();
  if (params?.position) search.set("position", params.position);
  if (params?.sort_by) search.set("sort_by", params.sort_by);
  if (params?.limit) search.set("limit", String(params.limit));
  const suffix = search.toString() ? `?${search}` : "";
  return fetchJson(`/api/players${suffix}`);
}

export async function comparePlayers(elementIds: number[]): Promise<PlayerComparisonResponse> {
  const ids = elementIds.slice(0, 3).join(",");
  return fetchJson(`/api/players/compare?ids=${encodeURIComponent(ids)}`, { cache: "no-store" });
}

export async function getCaptains(): Promise<Player[]> {
  return fetchJson("/api/players/captains");
}

export async function getTransferTargets(): Promise<Player[]> {
  return fetchJson("/api/players/transfers");
}

export async function getDifferentials(): Promise<Player[]> {
  return fetchJson("/api/players/differentials");
}

export async function getFixtureTicker(range?: number): Promise<FixtureTick[]> {
  const suffix = range ? `?range=${range}` : "";
  return fetchJson(`/api/fixtures/ticker${suffix}`);
}

export async function getFixtures(): Promise<Fixture[]> {
  return fetchJson("/api/fixtures");
}

export async function getHealth(): Promise<{ status: string }> {
  return fetchJson("/api/health");
}

export async function getReadiness(): Promise<{
  status: string;
  ready: boolean;
  season: string;
  errors: string[];
}> {
  return fetchJson("/api/readiness", { cache: "no-store" });
}

export async function getPlayerHistory(name: string): Promise<PlayerHistoryPoint[]> {
  return fetchJson(`/api/players/${encodeURIComponent(name)}/history`);
}

export async function getCaptaincyPredictions(gw?: number, limit = 50): Promise<CaptainPick[]> {
  const search = new URLSearchParams({ limit: String(limit) });
  if (gw) search.set("gw", String(gw));
  return fetchJson(`/api/predictions/captaincy?${search}`);
}

export async function getPredictionTransfers(): Promise<TransferTarget[]> {
  return fetchJson("/api/predictions/transfers");
}

export async function getOverview(): Promise<OverviewResponse> {
  return fetchJson("/api/predictions/overview");
}

export async function getTeam(teamId: string): Promise<TeamData> {
  return fetchJson(`/api/fpl/team/${teamId}`);
}

export async function getSquad(teamId: string, gw: number): Promise<SquadPlayer[]> {
  return fetchJson(`/api/fpl/team/${teamId}/squad?gw=${gw}`);
}

export async function getTeamHistory(teamId: string): Promise<unknown> {
  return fetchJson(`/api/fpl/team/${teamId}/history`);
}

export async function getTeamTransfers(teamId: string): Promise<unknown[]> {
  return fetchJson(`/api/fpl/team/${teamId}/transfers`);
}

export async function getPlanner(teamId: string, horizon: number): Promise<PlannerResponse> {
  return fetchJson(`/api/predictions/planner?team_id=${encodeURIComponent(teamId)}&horizon=${horizon}`);
}

export async function getDecisionCenter(
  teamId: string,
  horizon: 3 | 5 | 8 = 3,
): Promise<DecisionCenterResponse> {
  return fetchJson(
    `/api/predictions/decision-center?team_id=${encodeURIComponent(teamId)}&horizon=${horizon}`,
    { cache: "no-store" },
  );
}

export async function getInitialSquad(
  horizon: number,
  riskProfile: "maximum_points" | "balanced" | "safe" = "balanced",
): Promise<InitialSquadResponse> {
  return fetchJson(`/api/predictions/initial-squad?horizon=${horizon}&risk_profile=${riskProfile}`, {
    cache: "no-store",
  });
}

export async function getDraftWorkspace(
  horizon: 3 | 5 | 8 = 8,
  riskProfile: "maximum_points" | "balanced" | "safe" = "balanced",
): Promise<DraftWorkspaceResponse> {
  return fetchJson(
    `/api/predictions/draft-workspace?horizon=${horizon}&risk_profile=${riskProfile}`,
    { cache: "no-store" },
  );
}

export async function getDeadlineReadiness(): Promise<DeadlineReadinessResponse> {
  return fetchJson("/api/operations/deadline-readiness", { cache: "no-store" });
}

export async function getPostGameweekReview(teamId: string): Promise<PostGameweekReviewResponse> {
  return fetchJson(`/api/review/post-gameweek?team_id=${encodeURIComponent(teamId)}`, {
    cache: "no-store",
  });
}

export async function getChipTips(teamId?: string): Promise<ChipTipsResponse> {
  const suffix = teamId ? "?team_id=" + encodeURIComponent(teamId) : "";
  return fetchJson("/api/chip-tips" + suffix, { cache: "no-store" });
}

export async function getChipStatuses(teamId?: string): Promise<ChipStatusResponse> {
  const path = teamId
    ? `/api/fpl/team/${encodeURIComponent(teamId)}/chips`
    : "/api/fpl/chips";
  return fetchJson(path, { cache: "no-store" });
}

export async function getAccuracy(): Promise<AccuracyResult[]> {
  return fetchJson("/api/backtest/accuracy");
}

export async function getCaptaincyBacktest(): Promise<BacktestResult[]> {
  return fetchJson("/api/backtest/captaincy");
}

export async function getTop10Metrics(): Promise<Top10Metric[]> {
  return fetchJson("/api/backtest/top10");
}
