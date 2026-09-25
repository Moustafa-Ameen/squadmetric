import assert from "node:assert/strict";
import test from "node:test";

import {
  compareDraft,
  draftChanges,
  draftRating,
  parseSavedDrafts,
  selectDraftLineup,
  validateDraft,
} from "./draftWorkspace.ts";

const constraints = {
  budget: 100,
  squad_size: 15,
  starting_xi_size: 11,
  max_players_per_team: 3,
  position_counts: { GKP: 2, DEF: 5, MID: 5, FWD: 3 },
};

function squad() {
  const positions = ["GKP", "GKP", "DEF", "DEF", "DEF", "DEF", "DEF", "MID", "MID", "MID", "MID", "MID", "FWD", "FWD", "FWD"];
  return positions.map((position, index) => ({
    element_id: index + 1,
    name: `Player ${index + 1}`,
    web_name: `P${index + 1}`,
    team: `T${(index % 5) + 1}`,
    team_id: (index % 5) + 1,
    position,
    price: 6,
    gw1_points: index + 1,
    horizon_points: (index + 1) * 5,
    start_likelihood: 0.9,
    availability_probability: 1,
  }));
}

test("validates an exact legal FPL opening squad", () => {
  const result = validateDraft(squad(), constraints);
  assert.equal(result.legal, true);
  assert.equal(result.cost, 90);
  assert.equal(result.bank, 10);
  assert.deepEqual(result.positionCounts, { GKP: 2, DEF: 5, MID: 5, FWD: 3 });
});

test("rejects over-budget and four-per-club drafts", () => {
  const players = squad();
  players[0].price = 17;
  players[0].team_id = 2;
  const result = validateDraft(players, constraints);
  assert.equal(result.legal, false);
  assert.ok(result.errors.some((message) => message.includes("over budget")));
  assert.ok(result.errors.some((message) => message.includes("maximum is 3")));
});

test("selects a legal XI, captain, vice, and outfield-first autosub bench", () => {
  const players = squad();
  const lineup = selectDraftLineup(players);
  assert.equal(lineup.startingIds.length, 11);
  assert.equal(lineup.benchIds.length, 4);
  assert.ok(/^\d-\d-\d$/.test(lineup.formation));
  assert.ok(lineup.startingIds.includes(lineup.captainId));
  assert.ok(lineup.startingIds.includes(lineup.viceCaptainId));
  const lastBench = players.find((player) => player.element_id === lineup.benchIds.at(-1));
  assert.equal(lastBench.position, "GKP");
});

test("reserves uncertainty instead of rating an optimized draft as perfect", () => {
  const players = squad();
  assert.equal(draftRating(players, players, true), 98);
  assert.equal(draftRating(players, players, false), 0);
});

test("compares saved drafts with horizon value, cover, and reliability", () => {
  const players = squad();
  players[0].start_likelihood = 0.5;
  const result = compareDraft(
    { id: "one", name: "Balanced", playerIds: players.map((player) => player.element_id) },
    players,
    constraints,
  );
  assert.equal(result.legal, true);
  assert.equal(result.expectedGw1Points, selectDraftLineup(players).expectedGw1Points);
  assert.ok(result.planningValue > result.expectedGw1Points);
  assert.ok(result.benchCoverValue > 0);
  assert.equal(result.lowReliabilityCount, 1);
});

test("reports exact player changes between two drafts", () => {
  assert.deepEqual(draftChanges([1, 2, 3], [2, 3, 4]), {
    playersOut: [1],
    playersIn: [4],
  });
});

test("migrates valid v1 drafts and rejects malformed storage rows", () => {
  const [draft] = parseSavedDrafts([
    {
      id: "legacy",
      name: "  My team  ",
      playerIds: squad().map((player) => player.element_id),
      bootstrapHash: "bootstrap",
      updatedAt: "2026-08-17T12:00:00Z",
    },
    { id: "broken", playerIds: [] },
  ]);
  assert.equal(draft.schemaVersion, 2);
  assert.equal(draft.name, "My team");
  assert.equal(draft.horizon, 8);
  assert.equal(draft.riskProfile, "balanced");
  assert.equal(draft.rulesVersion, "legacy");
});
