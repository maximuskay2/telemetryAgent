// APK download QR: scannable absolute link beside the Phone download.
// Run: node --test app/lib/ (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, "..");
const require = createRequire(import.meta.url);
const ts = require("typescript");

function loadTsx(relativePath) {
  const source = readFileSync(join(appDir, relativePath), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const module = { exports: {} };
  new Function("module", "exports", "require", compiled)(
    module,
    module.exports,
    require,
  );
  return module.exports;
}

const apkQr = loadTsx("welcome/ApkQr.tsx");

describe("apk download qr", () => {
  it("builds an absolute download URL from any host", () => {
    assert.equal(
      apkQr.apkDownloadUrl("https://demo.example.com"),
      "https://demo.example.com/downloads/telemetry-agent.apk",
    );
    assert.equal(
      apkQr.apkDownloadUrl("https://demo.example.com/"),
      "https://demo.example.com/downloads/telemetry-agent.apk",
    );
    assert.equal(
      apkQr.apkDownloadUrl("http://localhost:3000"),
      "http://localhost:3000/downloads/telemetry-agent.apk",
    );
  });

  it("sits beside the Phone download button", () => {
    const howTo = readFileSync(join(appDir, "welcome/HowTo.tsx"), "utf8");
    assert.ok(howTo.includes("ApkQr"), "phone section renders the QR");
    assert.ok(howTo.includes("Download APK"));
    assert.ok(
      howTo.indexOf("<ApkQr") > howTo.indexOf('id="phone"'),
      "QR renders in the phone section",
    );
  });

  it("encodes the live origin, not a hardcoded host", () => {
    const source = readFileSync(join(appDir, "welcome/ApkQr.tsx"), "utf8");
    assert.ok(source.includes("window.location.origin"));
    assert.ok(source.includes("QRCodeSVG"));
    assert.ok(!source.includes("railway.app"));
    assert.ok(!source.includes("localhost"));
  });
});
