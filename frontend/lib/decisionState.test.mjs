import assert from "node:assert/strict";
import test from "node:test";

import {
  decisionStatusLabel,
  recommendationsAreReady,
  squadAccessState,
} from "./decisionState.ts";

const readyState = {
  decision_status: "ready",
  recommendations_ready: true,
};

test("recommendations require both the ready status and ready flag", () => {
  assert.equal(recommendationsAreReady(readyState), true);
  assert.equal(recommendationsAreReady({ ...readyState, recommendations_ready: false }), false);
  assert.equal(recommendationsAreReady({ ...readyState, decision_status: "blocked" }), false);
  assert.equal(decisionStatusLabel({ ...readyState, decision_status: "unavailable" }), "Live FPL data unavailable");
  assert.equal(decisionStatusLabel({ ...readyState, decision_status: "blocked", recommendations_ready: false }), "Recommendations updating");
});

test("a saved Team ID is not treated as personalization without a loaded squad", () => {
  assert.equal(squadAccessState("123", 0, null, true), "loading");
  assert.equal(squadAccessState("123", 0), "service_unavailable");
  assert.equal(squadAccessState("123", 0, "squad_unavailable"), "squad_unavailable");
  assert.equal(squadAccessState("123", 0, "fpl_resource_not_found"), "invalid_team");
  assert.equal(squadAccessState("123", 15), "personalized");
  assert.equal(squadAccessState("", 15), "no_team");
});
