// Keys page: list every secret by hint, rotate for a new one.
// Run: node --test app/keys/ (from apps/web)
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

describe("keys page", () => {
  it("is a signed-in page behind auth", () => {
    const page = read("keys/page.tsx");
    assert.ok(page.includes("RequireAuth"));
    assert.ok(page.includes("AccountChrome"));
    assert.ok(page.includes("setSessionAuthProvider(getSessionAuth)"));
  });

  it("lists keys by hint and rotates minted kinds", () => {
    const page = read("keys/page.tsx");
    assert.ok(page.includes("listConnections"));
    assert.ok(page.includes("secret_hint"));
    assert.ok(page.includes("rotateConnection"));
    assert.ok(page.includes("KeyOnce"));
    assert.ok(page.includes("****last4"));
  });

  it("sends pasted-secret kinds to the connections panel", () => {
    const page = read("keys/page.tsx");
    assert.ok(page.includes("Manage in Connections"));
    assert.ok(page.includes("/connect?system="));
  });

  it("sits in the dashboard menus", () => {
    assert.ok(read("dashboard/page.tsx").includes('href="/keys"'));
    assert.ok(
      read("commerce/AccountChrome.tsx").includes('href: "/keys"'),
    );
  });
});
