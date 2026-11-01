import assert from "node:assert/strict";
import test from "node:test";

import {
  decisionStatusLabel,
  predictionLag,
  predictionLagMessage,
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
  assert.equal(decisionStatusLabel({ ...readyState, decision_status: "blocked", recommendations_ready: false }), "Recommendations need fresh prediction data");
});

test("a ready model that trails official results reports its lag", () => {
  const trailing = {
    ...readyState,
    live_data: { latest_finalized_gameweek: 8 },
    artifact_data: { latest_finalized_gameweek: 7, missing_finalized_gameweeks: [8] },
  };
  const lag = predictionLag(trailing);
  assert.deepEqual(lag, { throughGameweek: 7, missingGameweeks: [8] });
  assert.equal(
    predictionLagMessage(lag),
    "Projections use results through GW7. GW8 is added at the next data refresh; prices, injuries and fixtures are already live.",
  );
  assert.equal(
    predictionLagMessage({ throughGameweek: 6, missingGameweeks: [7, 8] }),
    "Projections use results through GW6. GW7 and GW8 are added at the next data refresh; prices, injuries and fixtures are already live.",
  );
  assert.deepEqual(
    predictionLag({ ...trailing, artifact_data: { latest_finalized_gameweek: 6 } }),
    { throughGameweek: 6, missingGameweeks: [7, 8] },
  );
});

test("no lag is reported when current or when recommendations are blocked", () => {
  const current = {
    ...readyState,
    live_data: { latest_finalized_gameweek: 7 },
    artifact_data: { latest_finalized_gameweek: 7 },
  };
  assert.equal(predictionLag(current), null);
  assert.equal(
    predictionLag({
      ...current,
      decision_status: "blocked",
      recommendations_ready: false,
      live_data: { latest_finalized_gameweek: 10 },
    }),
    null,
  );
  assert.equal(predictionLag(null), null);
});

test("a saved Team ID is not treated as personalization without a loaded squad", () => {
  assert.equal(squadAccessState("123", 0, null, true), "loading");
  assert.equal(squadAccessState("123", 0), "service_unavailable");
  assert.equal(squadAccessState("123", 0, "squad_unavailable"), "squad_unavailable");
  assert.equal(squadAccessState("123", 0, "fpl_resource_not_found"), "invalid_team");
  assert.equal(squadAccessState("123", 15), "personalized");
  assert.equal(squadAccessState("", 15), "no_team");
});
