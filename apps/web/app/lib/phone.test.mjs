// Demo setup flow: a phone/APK step sits between setup and the demo.
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

describe("setup phone step", () => {
  it("setup completion routes through the phone page, not straight to the demo", () => {
    const setup = read("start/setup/page.tsx");
    assert.ok(setup.includes('"/start/phone"'), "setup leads to the phone page");
    assert.ok(
      !setup.includes("?tour=1"),
      "nothing in setup jumps past the phone page",
    );
  });

  it("phone page offers the APK download with a scannable code", () => {
    const phone = read("start/phone/page.tsx");
    assert.ok(phone.includes("/downloads/telemetry-agent.apk"));
    assert.ok(phone.includes("ApkQr"));
  });

  it("phone page connects with the server pairing details", () => {
    const phone = read("start/phone/page.tsx");
    assert.ok(phone.includes("/api/pairing"), "uses the canonical pairing URL");
    assert.ok(phone.includes("QRCodeSVG"), "scannable pairing code");
    assert.ok(phone.includes("Mobile token"), "token guidance");
  });

  it("phone page continues into the demo", () => {
    const phone = read("start/phone/page.tsx");
    assert.ok(phone.includes('href="/?tour=1"'));
  });
});
