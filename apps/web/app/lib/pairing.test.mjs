// Production onboarding: the wizard pair step offers the APK like the demo.
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

describe("wizard pair step", () => {
  it("offers the APK download with a scannable code", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("/downloads/telemetry-agent.apk"));
    assert.ok(wizard.includes("<ApkQr"));
  });

  it("still pairs with the server pairing details", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("pairingUrl"));
    assert.ok(wizard.includes("QRCodeSVG"));
    assert.ok(wizard.includes("Start watching"));
  });
});
