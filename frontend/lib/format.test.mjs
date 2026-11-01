import assert from "node:assert/strict";
import test from "node:test";

import { timeAgo } from "./format.ts";

test("timeAgo reads naturally from minutes to days", () => {
  assert.equal(timeAgo(0.2), "12 min ago");
  assert.equal(timeAgo(1), "1 hour ago");
  assert.equal(timeAgo(5.4), "5 hours ago");
  assert.equal(timeAgo(550.1), "23 days ago");
  assert.equal(timeAgo(null), "-");
});
