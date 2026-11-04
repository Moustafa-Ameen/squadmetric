export const DRAFTS_STORAGE_KEY = "squadmetric_drafts_v1";
// Drafts saved before the project was renamed. Kept only so they can be moved across.
export const LEGACY_DRAFTS_STORAGE_KEY = "fpl_intelligence_drafts_v1";

type DraftStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;

/** Moves drafts saved under the old key, leaving them there if the new key cannot be written. */
export function migrateLegacyDrafts(storage: DraftStorage) {
  const legacy = storage.getItem(LEGACY_DRAFTS_STORAGE_KEY);
  if (legacy === null) return;
  if (storage.getItem(DRAFTS_STORAGE_KEY) === null) {
    try {
      storage.setItem(DRAFTS_STORAGE_KEY, legacy);
    } catch {
      return;
    }
  }
  storage.removeItem(LEGACY_DRAFTS_STORAGE_KEY);
}

/** Reads the saved drafts, falling back to the old key if they could not be moved. */
export function readDraftsValue(storage: DraftStorage): string | null {
  migrateLegacyDrafts(storage);
  return storage.getItem(DRAFTS_STORAGE_KEY) ?? storage.getItem(LEGACY_DRAFTS_STORAGE_KEY);
}
