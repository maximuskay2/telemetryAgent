// Guided-demo step sync: readiness, track domains, scroll targets.
// Run: node --test app/lib/ (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const ts = require("typescript");

function loadTs() {
  const source = readFileSync(join(here, "tourSteps.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
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

const steps = loadTs();

describe("tour step sync", () => {
  it("starts at step 1 with nothing seen", () => {
    assert.equal(
      steps.maxReadyStep({
        triggered: false,
        diagnosed: false,
        verified: false,
        resolved: false,
      }),
      1,
    );
  });

  it("unlocks one step per pipeline mark, in order", () => {
    const base = {
      triggered: false,
      diagnosed: false,
      verified: false,
      resolved: false,
    };
    assert.equal(steps.maxReadyStep({ ...base, triggered: true }), 2);
    assert.equal(
      steps.maxReadyStep({ ...base, triggered: true, diagnosed: true }),
      3,
    );
    assert.equal(
      steps.maxReadyStep({
        ...base,
        triggered: true,
        diagnosed: true,
        verified: true,
      }),
      4,
    );
    assert.equal(
      steps.maxReadyStep({
        triggered: true,
        diagnosed: true,
        verified: true,
        resolved: true,
      }),
      5,
    );
  });

  it("never skips ahead on out-of-order marks", () => {
    assert.equal(
      steps.maxReadyStep({
        triggered: false,
        diagnosed: false,
        verified: true,
        resolved: false,
      }),
      1,
    );
    assert.equal(
      steps.maxReadyStep({
        triggered: true,
        diagnosed: false,
        verified: true,
        resolved: true,
      }),
      2,
    );
  });

  it("maps socket domains to demo tracks", () => {
    assert.equal(steps.trackOfDomain("software"), "shop");
    assert.equal(steps.trackOfDomain("appliance"), "freezer");
    assert.equal(steps.trackOfDomain("other"), null);
    assert.equal(steps.trackOfDomain(null), null);
    assert.equal(steps.trackOfDomain(undefined), null);
  });

  it("scrolls each step to its live panel per track", () => {
    assert.equal(steps.stepTarget(1, "shop"), "tour-shop");
    assert.equal(steps.stepTarget(1, "freezer"), "tour-freezer");
    assert.equal(steps.stepTarget(2, "shop"), "tour-trace");
    assert.equal(steps.stepTarget(3, "freezer"), "tour-trace");
    assert.equal(steps.stepTarget(4, "shop"), "tour-veto");
    assert.equal(steps.stepTarget(5, "freezer"), "tour-freezer");
  });

  it("labels all five steps on both tracks", () => {
    for (const track of ["shop", "freezer"]) {
      assert.equal(steps.STEP_LABELS[track].length, 5);
      for (const label of steps.STEP_LABELS[track]) {
        assert.ok(label.length > 0);
      }
    }
    assert.ok(steps.STEP_LABELS.shop[0].includes("shop"));
    assert.ok(steps.STEP_LABELS.freezer[0].includes("freezer"));
  });
});
