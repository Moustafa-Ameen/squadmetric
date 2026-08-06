import type {
  AccuracyResult,
  BacktestResult,
  CaptainPick,
  ChipStatusResponse,
  ChipTipsResponse,
  Fixture,
  FixtureTick,
  InitialSquadResponse,
  Player,
  PlayerComparisonResponse,
  PlayerHistoryPoint,
  PlannerResponse,
  SeasonState,
  SquadPlayer,
  TeamData,
  Top10Metric,
  TransferTarget,
} from "./types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function fetchJson<T>(
  path: string,
  options: RequestInit & { next?: { revalidate: number } } = { next: { revalidate: 300 } },
): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);
  if (!response.ok) {
    throw new Error(`API request failed: ${path}`);
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

export async function getCaptains(): Promise<CaptainPick[]> {
  return fetchJson("/api/players/captains");
}

export async function getTransferTargets(): Promise<TransferTarget[]> {
  return fetchJson("/api/players/transfers");
}

export async function getDifferentials(): Promise<TransferTarget[]> {
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

export async function getCaptaincyPredictions(gw?: number): Promise<CaptainPick[]> {
  const suffix = gw ? `?gw=${gw}` : "";
  return fetchJson(`/api/predictions/captaincy${suffix}`);
}

export async function getPredictionTransfers(): Promise<TransferTarget[]> {
  return fetchJson("/api/predictions/transfers");
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

export async function getInitialSquad(horizon: number): Promise<InitialSquadResponse> {
  return fetchJson(`/api/predictions/initial-squad?horizon=${horizon}`, {
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
