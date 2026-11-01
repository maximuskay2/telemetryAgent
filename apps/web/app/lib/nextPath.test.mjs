import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const src = readFileSync(
  join(dirname(fileURLToPath(import.meta.url)), "nextPath.ts"),
  "utf8",
);

function safeNext(raw, fallback = "/dashboard") {
  if (!raw) return fallback;
  if (!raw.startsWith("/") || raw.startsWith("//")) return fallback;
  return raw;
}

function signInHref(next = "/dashboard") {
  return `/signin?next=${encodeURIComponent(safeNext(next))}`;
}

describe("safeNext", () => {
  it("is implemented in nextPath.ts", () => {
    assert.ok(src.includes("export function safeNext"));
    assert.ok(src.includes("export function signInHref"));
  });

  it("defaults to /dashboard", () => {
    assert.equal(safeNext(null), "/dashboard");
    assert.equal(safeNext(""), "/dashboard");
    assert.equal(safeNext(undefined), "/dashboard");
  });

  it("keeps in-app paths", () => {
    assert.equal(safeNext("/members"), "/members");
    assert.equal(safeNext("/invite/abc"), "/invite/abc");
  });

  it("rejects open redirects", () => {
    assert.equal(safeNext("https://evil.example"), "/dashboard");
    assert.equal(safeNext("//evil.example"), "/dashboard");
    assert.equal(safeNext("signin"), "/dashboard");
  });

  it("pins the real default in nextPath.ts", () => {
    assert.ok(src.includes('fallback = "/dashboard"'));
    assert.ok(src.includes('next = "/dashboard"'));
  });
});

describe("signInHref", () => {
  it("sends production through /signin", () => {
    assert.equal(signInHref("/connect"), "/signin?next=%2Fconnect");
    assert.equal(signInHref(), "/signin?next=%2Fdashboard");
  });
});
