import assert from "node:assert/strict";
import test from "node:test";
import { sanitizeNextPath } from "./auth.ts";

test("sanitizeNextPath preserves safe relative application paths", () => {
  assert.equal(sanitizeNextPath("/decisions?gw=2#captain"), "/decisions?gw=2#captain");
  assert.equal(sanitizeNextPath("/dashboard"), "/dashboard");
});

test("sanitizeNextPath rejects open redirects and malformed values", () => {
  assert.equal(sanitizeNextPath("https://evil.example/steal"), "/dashboard");
  assert.equal(sanitizeNextPath("//evil.example/steal"), "/dashboard");
  assert.equal(sanitizeNextPath(null, "/login"), "/login");
});
