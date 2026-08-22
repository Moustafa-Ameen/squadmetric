import assert from "node:assert/strict";
import test from "node:test";

import {
  checklistProgress,
  deadlineAction,
  deadlineUrgency,
} from "./deadlineIntelligence.ts";

test("classifies deadline windows without inventing a deadline", () => {
  assert.equal(deadlineUrgency(null), "unknown");
  assert.equal(deadlineUrgency(48), "monitor");
  assert.equal(deadlineUrgency(24), "final_window");
  assert.equal(deadlineUrgency(2), "urgent");
  assert.equal(deadlineUrgency(-0.1), "passed");
});

test("requires final news before presenting a decision as lockable", () => {
  assert.match(deadlineAction(3, false, false).title, /news review required/i);
  assert.match(deadlineAction(3, false, true).title, /refresh and freeze/i);
  assert.match(deadlineAction(3, true, true).title, /lock is ready/i);
});

test("summarizes checklist progress", () => {
  assert.deepEqual(
    checklistProgress([
      { key: "one", passed: true },
      { key: "two", passed: false },
      { key: "three", passed: true },
    ]),
    { passed: 2, total: 3, percent: 67 },
  );
});
