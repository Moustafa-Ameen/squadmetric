import assert from "node:assert/strict";
import test from "node:test";
import { applyAuthoritativeTeamId, deriveAccountAccess } from "./accountAccess.ts";

test("new accounts require consent and onboarding", () => {
  assert.deepEqual(deriveAccountAccess(null, null), {
    requiresConsent: true,
    requiresOnboarding: true,
    teamId: null,
  });
});

test("an authenticated account cannot skip onboarding without a verified team", () => {
  const profile = { terms_accepted_at: "2026-08-22T00:00:00Z", onboarding_completed: true };
  assert.equal(deriveAccountAccess(profile, null).requiresOnboarding, true);
  assert.equal(deriveAccountAccess(profile, 123456).requiresOnboarding, false);
});

test("account team state clears a stale browser team when the account has no team", () => {
  const actions = [];
  const storage = {
    setItem: (key, value) => actions.push(["set", key, value]),
    removeItem: (key) => actions.push(["remove", key]),
  };
  assert.equal(applyAuthoritativeTeamId(storage, null), null);
  assert.deepEqual(actions, [["remove", "fpl_team_id"]]);
});

test("verified account team replaces browser state", () => {
  const actions = [];
  const storage = {
    setItem: (key, value) => actions.push(["set", key, value]),
    removeItem: (key) => actions.push(["remove", key]),
  };
  assert.equal(applyAuthoritativeTeamId(storage, "5605168"), 5605168);
  assert.deepEqual(actions, [["set", "fpl_team_id", "5605168"]]);
});
