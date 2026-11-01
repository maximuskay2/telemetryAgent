// Silent per-device demo session: anonymous dashboards pair in the
// background so every demo veto traces to a device.
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

describe("demo device session", () => {
  it("pairs once per tab and stores the token", () => {
    const lib = read("lib/demoSession.ts");
    assert.ok(lib.includes("/api/demo/devices"));
    assert.ok(lib.includes("ta.demo.device"));
    assert.ok(lib.includes("sessionStorage"));
  });

  it("attaches the demo token as a fallback veto header", () => {
    const veto = read("mission/VetoRing.tsx");
    assert.ok(veto.includes("ensureDemoDeviceToken"));
    assert.ok(veto.includes("demoAuthHeaders"));
    // Signed-in session headers spread last, so production wins.
    assert.ok(
      veto.indexOf("demoAuthHeaders()") < veto.indexOf("...session"),
    );
  });

  it("declares the demo watch on anonymous streams", () => {
    const stream = read("hooks/useAgentStream.ts");
    assert.ok(stream.includes("declareDemoWatch"));
    assert.ok(stream.includes("/api/demo/devices/watch") || stream.includes("declareDemoWatch([\"shop\", \"freezer\"])"));
  });
});
