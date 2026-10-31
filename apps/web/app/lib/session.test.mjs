// First sign-in bootstraps an organization so production connect works.
// Run: node --test app/lib/ (from apps/web)
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

describe("first-sign-in org", () => {
  it("creates an organization when the user has none", () => {
    const session = read("lib/session.tsx");
    assert.ok(
      session.includes("mine.length === 0"),
      "detects the empty-org case",
    );
    assert.ok(session.includes("createOrg("), "creates the org");
  });

  it("demo start page has no production connect", () => {
    const start = read("start/page.tsx");
    assert.ok(start.includes("Use the demo business"));
    assert.ok(start.includes('href="/start/setup"'));
    assert.ok(!start.includes("Connect my own system"));
    assert.ok(!start.includes("productionHref"));
  });
});
