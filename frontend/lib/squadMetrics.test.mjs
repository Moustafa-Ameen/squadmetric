import assert from "node:assert/strict";
import test from "node:test";

import { selectBestOwnedSquad } from "./squadLineup.ts";

function player(id, position, expectedPoints) {
  return {
    element_id: id,
    name: `Player ${id}`,
    position,
    team: `T${id}`,
    is_captain: false,
    is_vice_captain: false,
    raw_xp: expectedPoints,
    expected_points: expectedPoints,
    start_adjusted_xp: expectedPoints,
    start_likelihood: 1,
    form: 0,
  };
}

test("selects the highest projected legal XI from the owned squad", () => {
  const squad = [
    player(1, "GKP", 5), player(2, "GKP", 2),
    player(3, "DEF", 5), player(4, "DEF", 4), player(5, "DEF", 3), player(6, "DEF", 2), player(7, "DEF", 1),
    player(8, "MID", 10), player(9, "MID", 9), player(10, "MID", 8), player(11, "MID", 7), player(12, "MID", 6),
    player(13, "FWD", 11), player(14, "FWD", 1), player(15, "FWD", 0),
  ];

  const result = selectBestOwnedSquad(squad);
  const starters = result.slice(0, 11);

  assert.deepEqual(starters.map((row) => row.element_id), [1, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13]);
  assert.equal(starters.filter((row) => row.position === "GKP").length, 1);
  assert.equal(starters.filter((row) => row.position === "DEF").length, 4);
  assert.equal(starters.filter((row) => row.position === "MID").length, 5);
  assert.equal(starters.filter((row) => row.position === "FWD").length, 1);
  assert.equal(result.find((row) => row.is_captain)?.element_id, 13);
  assert.equal(result.find((row) => row.is_vice_captain)?.element_id, 8);
  assert.deepEqual(result.slice(11).map((row) => row.element_id), [7, 14, 15, 2]);
});

test("does not claim a best XI when projections are incomplete", () => {
  const squad = Array.from({ length: 15 }, (_, index) => player(index + 1, index < 2 ? "GKP" : "MID", 1));
  squad[4].expected_points = null;

  assert.equal(selectBestOwnedSquad(squad), squad);
});
