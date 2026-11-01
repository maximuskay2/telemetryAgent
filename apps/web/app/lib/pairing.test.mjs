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

  it("offers per-device pairing URLs, not one generic string", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("pairingVariants"));
    assert.ok(wizard.includes("Which device is the app on?"));
  });
});

// Mirror of lib/pairing.ts (node cannot import TS): LAN IP in, one
// working URL per device out. The pins below keep the mirror honest.
const pairingSrc = readFileSync(join(here, "pairing.ts"), "utf8");

function pairingVariants(apiUrl) {
  const IPV4 = /^\d{1,3}(\.\d{1,3}){3}$/;
  const phone = {
    target: "phone",
    label: "Physical phone",
    hint: "same Wi-Fi",
    url: apiUrl,
    unreachable: false,
  };
  let parsed;
  try {
    parsed = new URL(apiUrl);
  } catch {
    return [phone];
  }
  if (!IPV4.test(parsed.hostname)) return [phone];
  const withHost = (host) => {
    const swapped = new URL(parsed.toString());
    swapped.hostname = host;
    return swapped.toString().replace(/\/$/, "");
  };
  const loopback =
    parsed.hostname === "127.0.0.1" || parsed.hostname === "::1";
  return [
    {
      ...phone,
      hint: loopback
        ? "API could not detect its LAN IP — use the emulator entry"
        : "same Wi-Fi",
      unreachable: loopback,
    },
    {
      target: "emulator",
      label: "Android emulator",
      hint: "host loopback alias",
      url: withHost("10.0.2.2"),
      unreachable: false,
    },
    {
      target: "computer",
      label: "This computer",
      hint: "app + API on this machine",
      url: withHost("localhost"),
      unreachable: false,
    },
  ];
}

describe("pairingVariants", () => {
  it("is implemented in pairing.ts", () => {
    assert.ok(pairingSrc.includes("export function pairingVariants"));
    assert.ok(pairingSrc.includes("10.0.2.2"));
    assert.ok(
      pairingSrc.includes("API could not detect its LAN IP"),
      "loopback warning survives refactors",
    );
  });

  it("derives one working URL per device from a LAN URL", () => {
    const variants = pairingVariants("http://192.168.1.97:8001");
    assert.equal(variants.length, 3);
    assert.equal(variants[0].url, "http://192.168.1.97:8001");
    assert.equal(variants[0].unreachable, false);
    assert.equal(variants[1].target, "emulator");
    assert.equal(variants[1].url, "http://10.0.2.2:8001");
    assert.equal(variants[2].target, "computer");
    assert.equal(variants[2].url, "http://localhost:8001");
  });

  it("flags the loopback fallback as unreachable on a phone", () => {
    const variants = pairingVariants("http://127.0.0.1:8001");
    assert.equal(variants[0].unreachable, true);
    assert.match(variants[0].hint, /could not detect its LAN IP/);
    assert.equal(variants[1].url, "http://10.0.2.2:8001");
  });

  it("leaves hosted domains and garbage untouched", () => {
    const hosted = pairingVariants(
      "https://api-production-0c9a.up.railway.app",
    );
    assert.equal(hosted.length, 1);
    assert.equal(
      hosted[0].url,
      "https://api-production-0c9a.up.railway.app",
    );
    const garbage = pairingVariants("not a url");
    assert.equal(garbage.length, 1);
    assert.equal(garbage[0].url, "not a url");
  });
});
