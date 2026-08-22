import { normalized, positionCode } from "./format";
import type { SquadPlayer } from "./types";

export interface CurrentSquadMetrics {
  starters: SquadPlayer[];
  bench: SquadPlayer[];
  totalStartingXp: number;
  captainPick: SquadPlayer | null;
  viceCaptainPick: SquadPlayer | null;
  captaincyEdge: number;
  formation: string;
  xPByName: Map<string, number>;
}

export function selectCurrentSquadMetrics(squad: SquadPlayer[]): CurrentSquadMetrics {
  if (!squad.length) {
    return {
      starters: [],
      bench: [],
      totalStartingXp: 0,
      captainPick: null,
      viceCaptainPick: null,
      captaincyEdge: 0,
      formation: "-",
      xPByName: new Map(),
    };
  }

  const xPByName = new Map(squad.map((player) => [normalized(player.name), playerXp(player)]));
  const starters = squad.slice(0, 11);
  const bench = squad.slice(11);
  const captainRows = [...starters].sort((a, b) => playerXp(b) - playerXp(a));
  const captainPick = captainRows[0] ?? null;
  const viceCaptainPick = captainRows[1] ?? null;
  const captaincyEdge = Math.max(0, playerXp(captainPick) - playerXp(viceCaptainPick));

  return {
    starters,
    bench,
    totalStartingXp: starters.reduce((sum, player) => sum + playerXp(player), 0),
    captainPick,
    viceCaptainPick,
    captaincyEdge,
    formation: inferredFormation(starters),
    xPByName,
  };
}

export function playerXp(player: SquadPlayer | null | undefined): number {
  return player?.expected_points ?? 0;
}

function inferredFormation(starters: SquadPlayer[]): string {
  const defenders = starters.filter((player) => positionCode(player.position) === "DEF").length;
  const midfielders = starters.filter((player) => positionCode(player.position) === "MID").length;
  const forwards = starters.filter((player) => positionCode(player.position) === "FWD").length;
  return `${defenders}-${midfielders}-${forwards}`;
}
