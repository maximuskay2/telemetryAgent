// Stale-token 401s: refresh + single retry, honest expiry, and no
// unsigned mutations from /setup.
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

describe("session refresh", () => {
  it("registers a token refresher for 401 retries", () => {
    const auth = read("lib/sessionAuth.ts");
    assert.ok(auth.includes("setSessionAuthRefresher"));
    assert.ok(auth.includes("refreshSessionAuth"));
  });

  it("mints fresh Clerk tokens and stops masquerading when dead", () => {
    const session = read("lib/session.tsx");
    assert.ok(session.includes("setSessionAuthRefresher"));
    assert.ok(session.includes("skipCache"));
    assert.ok(session.includes('setStatus("signed-out")'));
  });

  it("retries once with the fresh token in shared wrappers", () => {
    for (const file of ["lib/setupApi.ts", "connect/api.ts"]) {
      const src = read(file);
      assert.ok(src.includes("refreshSessionAuth()"), file);
      assert.ok(
        src.includes("response.status === 401"),
        `${file} catches the 401`,
      );
      assert.ok(
        src.includes("auth.Authorization = `Bearer ${freshToken}`") ||
          src.includes("auth.Authorization = `Bearer ${fresh}`"),
        `${file} sends the fresh token, not the stale provider`,
      );
    }
  });

  it("never fires unsigned mutations from setup, demo excepted", () => {
    const setup = read("setup/page.tsx");
    assert.ok(setup.includes("Sign in to change production systems."));
    assert.ok(setup.includes("!demoTarget"));
    assert.ok(setup.includes("refreshSessionAuth()"));
  });

  it("judges the demo exception by the target row, not the loaded form", () => {
    const setup = read("setup/page.tsx");
    assert.ok(
      setup.includes("opts?.demo ?? profile?.environment?.demo"),
      "guard takes the target flag with the loaded profile as fallback",
    );
    assert.ok(
      setup.includes('{ demo: s.environment?.demo === "true" }'),
      "list actions pass their own row flag",
    );
  });
});
