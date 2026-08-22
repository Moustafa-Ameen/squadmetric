import assert from "node:assert/strict";
import test from "node:test";

import { parseReviewMode, rankMovementLabel } from "./reviewMode.ts";

test("points mode remains the fail-safe default", () => {
  assert.equal(parseReviewMode(null), "points");
  assert.equal(parseReviewMode("unexpected"), "points");
  assert.equal(parseReviewMode("rank"), "rank");
});

test("rank movement labels preserve direction", () => {
  assert.equal(rankMovementLabel(10_000), "Up 10,000");
  assert.equal(rankMovementLabel(-500), "Down 500");
  assert.equal(rankMovementLabel(null), "Opening rank");
});
