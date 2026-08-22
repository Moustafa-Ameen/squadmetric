import assert from "node:assert/strict";
import test from "node:test";

import {
  decisionHeadline,
  recommendationIsComplete,
} from "./decisionCenter.ts";

function recommendation() {
  const players = Array.from({ length: 15 }, (_, index) => ({
    element_id: index + 1,
    name: `Player ${index + 1}`,
  }));
  return {
    transfer_count: 2,
    hit_recommended: true,
    hit_cost: 4,
    chip_action: "save",
    starting_xi: players.slice(0, 11),
    bench_order: players.slice(11),
    captain_id: 1,
    vice_captain_id: 2,
  };
}

test("builds one transfer, hit, and chip headline", () => {
  assert.equal(decisionHeadline(recommendation()), "Make 2 transfers for a -4 · Save chips");
  assert.equal(
    decisionHeadline({ ...recommendation(), transfer_count: 0, hit_recommended: false, chip_action: "3xc" }),
    "Roll the transfer · Use Triple Captain",
  );
});

test("requires a complete legal display state before rendering advice", () => {
  const complete = recommendation();
  assert.equal(recommendationIsComplete(complete), true);
  assert.equal(recommendationIsComplete({ ...complete, bench_order: [] }), false);
  assert.equal(recommendationIsComplete({ ...complete, captain_id: 15 }), false);
});
