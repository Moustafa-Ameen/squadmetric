import assert from "node:assert/strict";
import test from "node:test";

import {
  DRAFTS_STORAGE_KEY,
  LEGACY_DRAFTS_STORAGE_KEY,
  migrateLegacyDrafts,
  readDraftsValue,
} from "./draftStorage.ts";

function memoryStorage(initial = {}) {
  const values = new Map(Object.entries(initial));
  return {
    getItem: (key) => (values.has(key) ? values.get(key) : null),
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
}

const OLD_DRAFTS = JSON.stringify([{ id: "old", name: "Saved before the rename" }]);
const NEW_DRAFTS = JSON.stringify([{ id: "new", name: "Saved after the rename" }]);

test("drafts saved under the old key move to the new key", () => {
  const storage = memoryStorage({ [LEGACY_DRAFTS_STORAGE_KEY]: OLD_DRAFTS });

  assert.equal(readDraftsValue(storage), OLD_DRAFTS);
  assert.equal(storage.getItem(DRAFTS_STORAGE_KEY), OLD_DRAFTS);
  assert.equal(storage.getItem(LEGACY_DRAFTS_STORAGE_KEY), null);
});

test("moving drafts twice changes nothing", () => {
  const storage = memoryStorage({ [LEGACY_DRAFTS_STORAGE_KEY]: OLD_DRAFTS });

  migrateLegacyDrafts(storage);
  migrateLegacyDrafts(storage);

  assert.equal(readDraftsValue(storage), OLD_DRAFTS);
});

test("drafts under the new key are never overwritten by the old key", () => {
  const storage = memoryStorage({
    [DRAFTS_STORAGE_KEY]: NEW_DRAFTS,
    [LEGACY_DRAFTS_STORAGE_KEY]: OLD_DRAFTS,
  });

  assert.equal(readDraftsValue(storage), NEW_DRAFTS);
  assert.equal(storage.getItem(LEGACY_DRAFTS_STORAGE_KEY), null);
});

test("a manager with no saved drafts has nothing written", () => {
  const storage = memoryStorage();

  assert.equal(readDraftsValue(storage), null);
  assert.equal(storage.getItem(DRAFTS_STORAGE_KEY), null);
});

test("old drafts stay readable and in place when the new key cannot be written", () => {
  const storage = memoryStorage({ [LEGACY_DRAFTS_STORAGE_KEY]: OLD_DRAFTS });
  storage.setItem = () => {
    throw new Error("storage is full");
  };

  assert.equal(readDraftsValue(storage), OLD_DRAFTS);
  assert.equal(storage.getItem(LEGACY_DRAFTS_STORAGE_KEY), OLD_DRAFTS);
});
