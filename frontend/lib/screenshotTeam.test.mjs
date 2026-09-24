import assert from "node:assert/strict";
import test from "node:test";
import { detectPlayersFromOcr, normalizePlayerName } from "./screenshotTeam.ts";

test("normalizes accented player names for screenshot matching", () => {
  assert.equal(normalizePlayerName("João Pedro"), "joao pedro");
});

test("detects unique catalog players from noisy OCR text", () => {
  const catalog = [
    { element_id: 1, name: "Erling Haaland", web_name: "Haaland" },
    { element_id: 2, name: "João Pedro", web_name: "João Pedro" },
  ];
  const found = detectPlayersFromOcr("CAPTAIN Haaland 8.9\nJoao Pedro 5.5", catalog);
  assert.deepEqual(found.map((player) => player.element_id).sort(), [1, 2]);
});

test("does not double-match ambiguous or overlapping player labels", () => {
  const catalog = [
    { element_id: 1, name: "Rayan Cherki", web_name: "Cherki" },
    { element_id: 2, name: "Rayan Ait Nouri", web_name: "Rayan" },
    { element_id: 3, name: "Cole Palmer", web_name: "Palmer" },
    { element_id: 4, name: "Kasey Palmer", web_name: "Palmer" },
  ];
  const found = detectPlayersFromOcr("Rayan Cherki\nPalmer", catalog);
  assert.deepEqual(found.map((player) => player.element_id), [1]);
});
