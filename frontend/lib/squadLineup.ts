import type { SquadPlayer } from "./types";

export function selectBestOwnedSquad(squad: SquadPlayer[]): SquadPlayer[] {
  if (squad.length !== 15 || squad.some((player) => typeof player.expected_points !== "number" || !Number.isFinite(player.expected_points))) {
    return squad;
  }

  const byPosition = new Map<string, SquadPlayer[]>();
  for (const player of squad) {
    const position = normalizedPosition(player.position);
    const rows = byPosition.get(position) ?? [];
    rows.push(player);
    byPosition.set(position, rows);
  }
  for (const rows of byPosition.values()) {
    rows.sort((left, right) => expectedPoints(right) - expectedPoints(left));
  }

  const goalkeeper = byPosition.get("GK")?.[0];
  let best: SquadPlayer[] = [];
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
      const candidatePoints = candidate.reduce((total, player) => total + expectedPoints(player), 0);
      if (candidatePoints > bestPoints) {
        best = candidate;
        bestPoints = candidatePoints;
      }
    }
  }
  if (best.length !== 11) return squad;

  const captainOrder = [...best].sort((left, right) => expectedPoints(right) - expectedPoints(left));
  const captain = captainOrder[0];
  const viceCaptain = captainOrder[1];
  const starters = best.map((player) => ({
    ...player,
    is_captain: player === captain,
    is_vice_captain: player === viceCaptain,
  }));
  const starterSet = new Set(best);
  const bench = squad
    .filter((player) => !starterSet.has(player))
    .sort((left, right) => {
      const leftGoalkeeper = normalizedPosition(left.position) === "GK";
      const rightGoalkeeper = normalizedPosition(right.position) === "GK";
      if (leftGoalkeeper !== rightGoalkeeper) return leftGoalkeeper ? 1 : -1;
      return expectedPoints(right) - expectedPoints(left);
    })
    .map((player) => ({ ...player, is_captain: false, is_vice_captain: false }));
  return [...starters, ...bench];
}

function expectedPoints(player: SquadPlayer): number {
  return player.expected_points ?? 0;
}

function normalizedPosition(position: string): string {
  const value = position.trim().toUpperCase();
  if (value === "GKP" || value === "GOALKEEPER") return "GK";
  if (value.startsWith("DEF")) return "DEF";
  if (value.startsWith("MID")) return "MID";
  if (value.startsWith("F")) return "FWD";
  return value;
}
