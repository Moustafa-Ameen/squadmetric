import type { DraftConstraints, DraftWorkspacePlayer } from "./types";

export interface DraftValidation {
  legal: boolean;
  errors: string[];
  cost: number;
  bank: number;
  positionCounts: Record<string, number>;
  teamCounts: Record<string, number>;
}

export interface DraftLineup {
  startingIds: number[];
  benchIds: number[];
  captainId: number | null;
  viceCaptainId: number | null;
  formation: string;
  expectedGw1Points: number;
  benchStartProbability: number;
}

export type DraftHorizon = 3 | 5 | 8;
export type DraftRiskProfile = "maximum_points" | "balanced" | "safe";

export interface SavedDraft {
  schemaVersion: 2;
  id: string;
  name: string;
  playerIds: number[];
  bootstrapHash: string;
  fixturesHash: string | null;
  rulesVersion: string;
  horizon: DraftHorizon;
  riskProfile: DraftRiskProfile;
  createdAt: string;
  updatedAt: string;
}

export interface DraftComparison {
  id: string;
  name: string;
  legal: boolean;
  cost: number;
  bank: number;
  expectedGw1Points: number;
  planningValue: number;
  benchCoverValue: number;
  averageStartLikelihood: number;
  lowReliabilityCount: number;
  captainId: number | null;
  formation: string;
  playerIds: number[];
}

export function normalizedDraftPosition(value: string): "GKP" | "DEF" | "MID" | "FWD" {
  const normalized = value.trim().toUpperCase();
  if (normalized === "GK" || normalized === "GOALKEEPER") return "GKP";
  if (normalized.startsWith("DEF")) return "DEF";
  if (normalized.startsWith("MID")) return "MID";
  if (normalized.startsWith("F")) return "FWD";
  return normalized as "GKP" | "DEF" | "MID" | "FWD";
}

export function validateDraft(
  players: DraftWorkspacePlayer[],
  constraints: DraftConstraints,
): DraftValidation {
  const errors: string[] = [];
  const positionCounts: Record<string, number> = {};
  const teamCounts: Record<string, number> = {};
  const seen = new Set<number>();
  let cost = 0;

  for (const player of players) {
    if (seen.has(player.element_id)) {
      errors.push(`${player.web_name ?? player.name} is selected more than once.`);
      continue;
    }
    seen.add(player.element_id);
    const position = normalizedDraftPosition(player.position);
    positionCounts[position] = (positionCounts[position] ?? 0) + 1;
    const teamKey = String(player.team_id ?? player.team);
    teamCounts[teamKey] = (teamCounts[teamKey] ?? 0) + 1;
    cost += player.price;
  }

  if (seen.size !== constraints.squad_size) {
    errors.push(`Select exactly ${constraints.squad_size} unique players.`);
  }
  for (const [position, required] of Object.entries(constraints.position_counts)) {
    const normalized = normalizedDraftPosition(position);
    if ((positionCounts[normalized] ?? 0) !== required) {
      errors.push(`${normalized} requires ${required} players.`);
    }
  }
  for (const [team, count] of Object.entries(teamCounts)) {
    if (count > constraints.max_players_per_team) {
      errors.push(`Club ${team} has ${count} players; maximum is ${constraints.max_players_per_team}.`);
    }
  }
  cost = roundMoney(cost);
  if (cost > constraints.budget + 0.001) {
    errors.push(`Squad is £${roundMoney(cost - constraints.budget).toFixed(1)}m over budget.`);
  }

  return {
    legal: errors.length === 0,
    errors,
    cost,
    bank: roundMoney(constraints.budget - cost),
    positionCounts,
    teamCounts,
  };
}

export function selectDraftLineup(players: DraftWorkspacePlayer[]): DraftLineup {
  const byPosition = new Map<string, DraftWorkspacePlayer[]>();
  for (const player of players) {
    const position = normalizedDraftPosition(player.position);
    const rows = byPosition.get(position) ?? [];
    rows.push(player);
    byPosition.set(position, rows);
  }
  for (const rows of byPosition.values()) {
    rows.sort((a, b) => decisionPoints(b) - decisionPoints(a));
  }

  const goalkeeper = byPosition.get("GKP")?.[0];
  let best: DraftWorkspacePlayer[] = [];
  let bestPoints = Number.NEGATIVE_INFINITY;
  for (let defenders = 3; defenders <= 5; defenders += 1) {
    for (let midfielders = 2; midfielders <= 5; midfielders += 1) {
      const forwards = 10 - defenders - midfielders;
      if (forwards < 1 || forwards > 3) continue;
      const candidate = [
        ...(goalkeeper ? [goalkeeper] : []),
        ...(byPosition.get("DEF") ?? []).slice(0, defenders),
        ...(byPosition.get("MID") ?? []).slice(0, midfielders),
        ...(byPosition.get("FWD") ?? []).slice(0, forwards),
      ];
      if (candidate.length !== 11) continue;
      const candidatePoints = candidate.reduce((sum, player) => sum + player.gw1_points, 0);
      if (candidatePoints > bestPoints) {
        best = candidate;
        bestPoints = candidatePoints;
      }
    }
  }

  const startingIds = best.map((player) => player.element_id);
  const startingSet = new Set(startingIds);
  const captainOrder = [...best].sort((a, b) => decisionPoints(b) - decisionPoints(a));
  const bench = players
    .filter((player) => !startingSet.has(player.element_id))
    .sort((a, b) => {
      const aGoalkeeper = normalizedDraftPosition(a.position) === "GKP";
      const bGoalkeeper = normalizedDraftPosition(b.position) === "GKP";
      if (aGoalkeeper !== bGoalkeeper) return aGoalkeeper ? 1 : -1;
      return benchValue(b) - benchValue(a);
    });
  const captain = captainOrder[0];

  return {
    startingIds,
    benchIds: bench.map((player) => player.element_id),
    captainId: captain?.element_id ?? null,
    viceCaptainId: captainOrder[1]?.element_id ?? null,
    formation: formation(best),
    expectedGw1Points: roundMoney(bestPoints + (captain?.gw1_points ?? 0)),
    benchStartProbability: bench.length
      ? roundFour(bench.reduce((sum, player) => sum + player.start_likelihood, 0) / bench.length)
      : 0,
  };
}

export function draftValue(players: DraftWorkspacePlayer[]): number {
  const lineup = selectDraftLineup(players);
  const bench = new Set(lineup.benchIds);
  const coverValue = players
    .filter((player) => bench.has(player.element_id))
    .reduce(
      (sum, player) => sum + player.gw1_points * player.start_likelihood * 0.08,
      0,
    );
  return roundMoney(lineup.expectedGw1Points + coverValue);
}

export function draftRating(
  players: DraftWorkspacePlayer[],
  optimizedPlayers: DraftWorkspacePlayer[],
  legal: boolean,
): number {
  if (!legal || !optimizedPlayers.length) return 0;
  const reference = draftValue(optimizedPlayers);
  if (reference <= 0) return 0;
  return Math.min(98, Math.max(0, Math.round((draftValue(players) / reference) * 98)));
}

export function compareDraft(
  draft: Pick<SavedDraft, "id" | "name" | "playerIds">,
  playerPool: DraftWorkspacePlayer[],
  constraints: DraftConstraints,
): DraftComparison {
  const byId = new Map(playerPool.map((player) => [player.element_id, player]));
  const players = draft.playerIds.map((id) => byId.get(id)).filter(isDraftPlayer);
  const validation = validateDraft(players, constraints);
  const lineup = selectDraftLineup(players);
  const starters = new Set(lineup.startingIds);
  const benchPlayers = players.filter((player) => !starters.has(player.element_id));
  const starterHorizon = players
    .filter((player) => starters.has(player.element_id))
    .reduce((sum, player) => sum + player.horizon_points, 0);
  const captainHorizon = players.find(
    (player) => player.element_id === lineup.captainId,
  )?.horizon_points ?? 0;
  const benchCoverValue = benchPlayers.reduce(
    (sum, player) => sum + player.horizon_points * player.start_likelihood * 0.08,
    0,
  );
  return {
    id: draft.id,
    name: draft.name,
    legal: validation.legal,
    cost: validation.cost,
    bank: validation.bank,
    expectedGw1Points: lineup.expectedGw1Points,
    planningValue: roundMoney(starterHorizon + captainHorizon + benchCoverValue),
    benchCoverValue: roundMoney(benchCoverValue),
    averageStartLikelihood: roundFour(
      players.length
        ? players.reduce((sum, player) => sum + player.start_likelihood, 0) / players.length
        : 0,
    ),
    lowReliabilityCount: players.filter((player) => player.start_likelihood < 0.75).length,
    captainId: lineup.captainId,
    formation: lineup.formation,
    playerIds: [...draft.playerIds],
  };
}

export function draftChanges(
  referenceIds: number[],
  candidateIds: number[],
): { playersOut: number[]; playersIn: number[] } {
  const reference = new Set(referenceIds);
  const candidate = new Set(candidateIds);
  return {
    playersOut: referenceIds.filter((id) => !candidate.has(id)),
    playersIn: candidateIds.filter((id) => !reference.has(id)),
  };
}

export function parseSavedDrafts(value: unknown): SavedDraft[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((candidate) => {
    if (!candidate || typeof candidate !== "object") return [];
    const row = candidate as Record<string, unknown>;
    const playerIds = Array.isArray(row.playerIds)
      ? row.playerIds.filter((id): id is number => Number.isInteger(id))
      : [];
    if (
      typeof row.id !== "string" ||
      typeof row.name !== "string" ||
      typeof row.bootstrapHash !== "string" ||
      playerIds.length !== 15
    ) return [];
    const updatedAt = typeof row.updatedAt === "string" ? row.updatedAt : new Date(0).toISOString();
    const horizon = row.horizon === 3 || row.horizon === 5 || row.horizon === 8 ? row.horizon : 8;
    const riskProfile =
      row.riskProfile === "maximum_points" || row.riskProfile === "safe"
        ? row.riskProfile
        : "balanced";
    return [{
      schemaVersion: 2 as const,
      id: row.id,
      name: row.name.trim() || "Unnamed draft",
      playerIds,
      bootstrapHash: row.bootstrapHash,
      fixturesHash: typeof row.fixturesHash === "string" ? row.fixturesHash : null,
      rulesVersion: typeof row.rulesVersion === "string" ? row.rulesVersion : "legacy",
      horizon,
      riskProfile,
      createdAt: typeof row.createdAt === "string" ? row.createdAt : updatedAt,
      updatedAt,
    }];
  });
}

function decisionPoints(player: DraftWorkspacePlayer): number {
  return player.gw1_points + player.start_likelihood * 0.05;
}

function benchValue(player: DraftWorkspacePlayer): number {
  return player.gw1_points * player.start_likelihood + player.horizon_points * 0.05;
}

function formation(players: DraftWorkspacePlayer[]): string {
  const count = (position: string) =>
    players.filter((player) => normalizedDraftPosition(player.position) === position).length;
  return `${count("DEF")}-${count("MID")}-${count("FWD")}`;
}

function roundMoney(value: number): number {
  return Math.round(value * 10) / 10;
}

function roundFour(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}

function isDraftPlayer(
  player: DraftWorkspacePlayer | undefined,
): player is DraftWorkspacePlayer {
  return player !== undefined;
}
