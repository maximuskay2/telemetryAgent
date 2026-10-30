// Proof-shop API suite: exercises the HTTP layer against an ephemeral port.
import test, { after, before } from "node:test";
import assert from "node:assert/strict";
import { createServer } from "../src/server.js";

let base;
let srv;

before(async () => {
  srv = createServer();
  await new Promise((resolve) => srv.listen(0, "127.0.0.1", resolve));
  base = `http://127.0.0.1:${srv.address().port}`;
});

after(async () => {
  await new Promise((resolve) => srv.close(resolve));
});

async function post(path, body) {
  const res = await fetch(base + path, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  return { status: res.status, json: await res.json() };
}

test("health", async () => {
  const res = await fetch(`${base}/health`);
  assert.equal(res.status, 200);
  assert.deepEqual(await res.json(), { status: "ok" });
});

test("checkout ok", async () => {
  const { status, json } = await post("/checkout", {
    items: [{ name: "a", price: 2.0, qty: 2 }],
  });
  assert.equal(status, 200);
  assert.equal(json.total, 4.0);
});

test("checkout validates price", async () => {
  const { status } = await post("/checkout", {
    items: [{ name: "a", price: -1, qty: 1 }],
  });
  assert.equal(status, 422);
});

test("checkout validates name", async () => {
  const { status } = await post("/checkout", {
    items: [{ name: "", price: 1, qty: 1 }],
  });
  assert.equal(status, 422);
});

test("checkout bulk order", async () => {
  const { status, json } = await post("/checkout", {
    items: [0, 1, 2].map((i) => ({ name: `n${i}`, price: 10.0, qty: 10 })),
  });
  assert.equal(status, 200);
  assert.equal(json.discount, 15.0);
});

test("checkout single bulk line has no discount", async () => {
  const { status, json } = await post("/checkout", {
    items: [{ name: "a", price: 1.0, qty: 25 }],
  });
  assert.equal(status, 200);
  assert.equal(json.discount, 0.0);
});

test("checkout zero qty line", async () => {
  const { status, json } = await post("/checkout", {
    items: [{ name: "a", price: 3.0, qty: 0 }],
  });
  assert.equal(status, 200);
  assert.equal(json.total, 0.0);
});

test("unknown route is 404", async () => {
  const res = await fetch(`${base}/nope`);
  assert.equal(res.status, 404);
});
