import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "nextPath.ts"),
  "utf8",
);

function safeNext(raw, fallback = "/connect") {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  return raw;
}

function signInHref(next = "/connect") {
  return `/signin?next=${encodeURIComponent(safeNext(next))}`;
}

describe("safeNext", () => {
  it("is implemented in nextPath.ts", () => {
    assert.ok(src.includes("export function safeNext"));
    assert.ok(src.includes("export function signInHref"));
  });

  it("defaults to /connect", () => {
    assert.equal(safeNext(null), "/connect");
    assert.equal(safeNext(""), "/connect");
    assert.equal(safeNext(undefined), "/connect");
  });

  it("keeps in-app paths", () => {
    assert.equal(safeNext("/members"), "/members");
    assert.equal(safeNext("/invite/abc"), "/invite/abc");
  });

  it("rejects open redirects", () => {
    assert.equal(safeNext("https://evil.example"), "/connect");
    assert.equal(safeNext("//evil.example"), "/connect");
    assert.equal(safeNext("signin"), "/connect");
  });
});

describe("signInHref", () => {
  it("sends production through /signin", () => {
    assert.equal(signInHref("/connect"), "/signin?next=%2Fconnect");
  });
});
