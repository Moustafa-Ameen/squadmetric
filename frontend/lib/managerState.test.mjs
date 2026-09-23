import assert from "node:assert/strict";
import test from "node:test";

import {
  clearManagerStateOverride,
  readManagerStateOverride,
  saveManagerStateOverride,
} from "./managerState.ts";

function memoryStorage() {
  const values = new Map();
  return {
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: (key) => values.delete(key),
  };
}

test("stores manager-state confirmation separately for each FPL team", () => {
  const storage = memoryStorage();
  saveManagerStateOverride("123", { bank: 1.7, freeTransfers: 2 }, storage);
  saveManagerStateOverride("456", { bank: 0.2, freeTransfers: 1 }, storage);

  assert.deepEqual(readManagerStateOverride("123", storage), {
    bank: 1.7,
    freeTransfers: 2,
  });
  assert.deepEqual(readManagerStateOverride("456", storage), {
    bank: 0.2,
    freeTransfers: 1,
  });

  clearManagerStateOverride("123", storage);
  assert.equal(readManagerStateOverride("123", storage), undefined);
});

test("rejects corrupt or impossible manager state", () => {
  const storage = memoryStorage();
  storage.setItem("squadmetric_manager_state_v1:123", JSON.stringify({ bank: -1, freeTransfers: 8 }));
  assert.equal(readManagerStateOverride("123", storage), undefined);
});
