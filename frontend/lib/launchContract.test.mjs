import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("production verification fails closed when launch credentials are absent", () => {
  const result = spawnSync(process.execPath, ["scripts/verify-production-env.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
    env: { PATH: process.env.PATH },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /NEXT_PUBLIC_SUPABASE_URL/);
  assert.match(result.stderr, /SUPABASE_SERVICE_ROLE_KEY/);
});

test("production verification accepts a complete non-local launch contract", () => {
  const result = spawnSync(process.execPath, ["scripts/verify-production-env.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
    env: {
      ...process.env,
      FPL_API_SERVER_URL: "https://api.squadmetric.test",
      NEXT_PUBLIC_SUPABASE_URL: "https://project.supabase.co",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
      SUPABASE_SERVICE_ROLE_KEY: "server_only_test_key",
      NEXT_PUBLIC_SITE_URL: "https://squadmetric.test",
      NEXT_PUBLIC_SUPPORT_EMAIL: "support@squadmetric.test",
    },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Production contract verified/);
});

test("account schema enables owner isolation and launch data contracts", () => {
  const migration = readFileSync("../supabase/migrations/202608210001_account_foundation.sql", "utf8");
  for (const table of ["profiles", "fpl_team_links", "user_preferences", "saved_drafts", "weekly_recommendations", "decision_history", "favorite_players"]) {
    assert.match(migration, new RegExp(`alter table public\\.${table} enable row level security`));
    assert.match(migration, new RegExp(`${table}_owner_all`));
  }
  for (const field of ["terms_accepted_at", "objective_mode", "player_name"]) {
    assert.match(migration, new RegExp(field));
  }
  assert.match(migration, /primary key \(user_id, id\)/);
  assert.match(migration, /security definer set search_path = ''/);
});

test("permanent deletion remains in a server-only route", () => {
  const route = readFileSync("app/api/account/delete/route.ts", "utf8");
  assert.match(route, /SUPABASE_SERVICE_ROLE_KEY/);
  assert.match(route, /auth\.admin\.deleteUser/);
  assert.doesNotMatch(route, /NEXT_PUBLIC_SUPABASE_SERVICE/);
});
