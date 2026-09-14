import assert from "node:assert/strict";
import test from "node:test";
import { parseFplTeamInput } from "./fplTeam.ts";

test("parses a numeric FPL Team ID", () => {
  assert.deepEqual(parseFplTeamInput(" 00123456 "), { ok: true, value: { teamId: "123456", source: "team_id" } });
});

test("parses official FPL points and history URLs", () => {
  assert.deepEqual(parseFplTeamInput("https://fantasy.premierleague.com/entry/98765/event/1"), { ok: true, value: { teamId: "98765", source: "fpl_url" } });
  assert.deepEqual(parseFplTeamInput("https://fantasy.premierleague.com/entry/42/history"), { ok: true, value: { teamId: "42", source: "fpl_url" } });
});

test("parses localized, www, scheme-free, and query-string FPL URLs", () => {
  const expected = { ok: true, value: { teamId: "3254925", source: "fpl_url" } };

  assert.deepEqual(parseFplTeamInput("https://fantasy.premierleague.com/en/entry/3254925/event/4"), expected);
  assert.deepEqual(parseFplTeamInput("https://www.fantasy.premierleague.com/en/entry/3254925/history/"), expected);
  assert.deepEqual(parseFplTeamInput("fantasy.premierleague.com/entry/3254925/transfers"), expected);
  assert.deepEqual(parseFplTeamInput("https://fantasy.premierleague.com/en/entry/3254925/event/4?view=classic#points"), expected);
});

test("rejects lookalike hosts, insecure URLs, and invalid IDs", () => {
  assert.equal(parseFplTeamInput("https://fantasy.premierleague.com.evil.test/entry/123/history").ok, false);
  assert.equal(parseFplTeamInput("https://fantasy.premierleague.com@evil.test/en/entry/123/history").ok, false);
  assert.equal(parseFplTeamInput("http://fantasy.premierleague.com/entry/123/history").ok, false);
  assert.equal(parseFplTeamInput("0").ok, false);
  assert.equal(parseFplTeamInput("https://fantasy.premierleague.com/players").ok, false);
});
