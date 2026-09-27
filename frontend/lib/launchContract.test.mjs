import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import test from "node:test";

test("production verification fails closed when launch credentials are absent", () => {
  const result = spawnSync(process.execPath, ["scripts/verify-production-env.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
    env: { PATH: process.env.PATH },
  });
  assert.equal(result.status, 1);
  assert.match(result.stderr, /FPL_API_SERVER_URL/);
  assert.match(result.stderr, /NEXT_PUBLIC_SITE_URL/);
});

test("production verification accepts a guest-first non-local launch contract", () => {
  const result = spawnSync(process.execPath, ["scripts/verify-production-env.mjs"], {
    cwd: process.cwd(),
    encoding: "utf8",
    env: {
      ...process.env,
      FPL_API_SERVER_URL: "https://api.squadmetric.test",
      NEXT_PUBLIC_SITE_URL: "https://squadmetric.test",
      NEXT_PUBLIC_SUPPORT_EMAIL: "support@squadmetric.test",
    },
  });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Production contract verified/);
  assert.match(result.stdout, /Guest-first browser storage enabled/);
});
