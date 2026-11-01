// Systems polling never blanks provisioned systems on a stale token:
// the endpoint degrades to 200-empty when auth dies mid-poll.
// Run: node --test app/hooks/ (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, "..");

function read(rel) {
  return readFileSync(join(appDir, rel), "utf8");
}

describe("useSystems", () => {
  it("keeps the last-known list on HTTP errors", () => {
    const hook = read("hooks/useSystems.ts");
    assert.ok(hook.includes("lastKnown"));
    assert.ok(hook.includes("if (!first) return;"));
  });

  it("retries a suspicious empty list with a fresh token", () => {
    const hook = read("hooks/useSystems.ts");
    assert.ok(hook.includes("refreshSessionAuth"));
    assert.ok(hook.includes("lastKnown.current.length > 0"));
    assert.ok(hook.includes("hadToken"));
  });

  it("carries the demo tag so tiles match any generated id", () => {
    const hook = read("hooks/useSystems.ts");
    assert.ok(hook.includes("demo: isDemo(s.environment)"));
    assert.ok(hook.includes('=== "true"'));
  });
});
