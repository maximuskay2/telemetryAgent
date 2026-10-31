// Learning-window contract: 30 s demo / 60 s production (was 120 s).
// Run: node --test app/lib/ (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(rel) {
  return readFileSync(join(appDir, rel), "utf8");
}

describe("learning window", () => {
  it("demo learn button promises 30 seconds, not 2 minutes", () => {
    const page = read("start/setup/page.tsx");
    assert.ok(page.includes("Watch normal for 30 sec"));
    assert.ok(!page.includes("Watch normal for 2 min"));
    assert.ok(!page.includes("Two quiet minutes"));
  });

  it("demo learn sends no explicit duration (server default 30 s applies)", () => {
    const api = read("lib/setupApi.ts");
    const start = api.indexOf("export async function demoLearn");
    const end = api.indexOf("export async function getProfile");
    assert.ok(start !== -1 && end > start);
    const fn = api.slice(start, end);
    assert.ok(!fn.includes("duration_s"));
  });

  it("production baseline learns for 60 seconds, not 120", () => {
    const page = read("setup/page.tsx");
    assert.ok(page.includes("duration_s: 60"));
    assert.ok(!page.includes("duration_s: 120"));
  });

  it("explainer copy matches the shorter windows", () => {
    const setup = read("start/setup/page.tsx");
    assert.ok(setup.includes("Thirty quiet seconds"));
    const start = read("start/page.tsx");
    assert.ok(!start.includes("two quiet minutes"));
    const howTo = read("welcome/HowTo.tsx");
    assert.ok(!howTo.includes("two quiet minutes"));
    assert.ok(howTo.includes("thirty seconds of normal traffic"));
  });
});
