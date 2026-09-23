import assert from "node:assert/strict";
import test from "node:test";
import { getDecisionCenter, getHealth } from "./api.ts";

test("coalesces simultaneous identical GET requests", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  let release;
  const waiting = new Promise((resolve) => { release = resolve; });

  globalThis.fetch = async () => {
    calls += 1;
    await waiting;
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    const first = getHealth();
    const second = getHealth();
    release();
    assert.deepEqual(await Promise.all([first, second]), [
      { status: "ok" },
      { status: "ok" },
    ]);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("keeps a completed decision response warm for repeated page visits", async () => {
  const originalFetch = globalThis.fetch;
  let calls = 0;
  const payload = { status: "ready", team_id: 987654, horizon: 5 };
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(JSON.stringify(payload), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    assert.deepEqual(await getDecisionCenter("987654", 5), payload);
    assert.deepEqual(await getDecisionCenter("987654", 5), payload);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("sends confirmed bank and free transfers as separate decision inputs", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl = "";
  globalThis.fetch = async (url) => {
    requestedUrl = String(url);
    return new Response(JSON.stringify({ status: "ready" }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  try {
    await getDecisionCenter("123456", 3, { bank: 1.7, freeTransfers: 2 });
    const query = new URL(requestedUrl, "http://local.test").searchParams;
    assert.equal(query.get("team_id"), "123456");
    assert.equal(query.get("bank_override"), "1.7");
    assert.equal(query.get("free_transfers_override"), "2");
  } finally {
    globalThis.fetch = originalFetch;
  }
});
