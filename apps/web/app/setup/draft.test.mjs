// Draft store round-trips manual /setup progress per system.
// Run: node --test app/setup/ (from apps/web)
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

function loadTs(relativePath) {
  const source = readFileSync(join(appDir, relativePath), "utf8");
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

const draft = loadTs("setup/draft.ts");

function memStore(initial = {}) {
  const data = { ...initial };
  return {
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = String(value);
    },
    removeItem: (key) => {
      delete data[key];
    },
    _data: data,
  };
}

const DATA = {
  systemId: "acme-1",
  step: "review",
  name: "Acme",
  kind: "software",
};

describe("setup drafts", () => {
  it("saves and reloads progress per system", () => {
    const store = memStore();
    draft.saveSetupDraft(DATA, store);
    const drafts = draft.loadSetupDrafts(store);
    assert.equal(drafts["acme-1"].data.step, "review");
    assert.equal(drafts["acme-1"].data.name, "Acme");
  });

  it("keeps systems independent and clears on finish", () => {
    const store = memStore();
    draft.saveSetupDraft(DATA, store);
    draft.saveSetupDraft(
      { ...DATA, systemId: "acme-2", name: "B", step: "teach" },
      store,
    );
    assert.equal(Object.keys(draft.loadSetupDrafts(store)).length, 2);
    draft.clearSetupDraft("acme-1", store);
    const rest = draft.loadSetupDrafts(store);
    assert.equal(Object.keys(rest).length, 1);
    assert.ok("acme-2" in rest);
  });

  it("ignores corrupt or missing storage", () => {
    assert.deepEqual(draft.loadSetupDrafts(memStore()), {});
    assert.deepEqual(
      draft.loadSetupDrafts(memStore({ ta_setup_drafts: "{nope" })),
      {},
    );
    assert.deepEqual(draft.loadSetupDrafts(null), {});
    draft.saveSetupDraft(DATA, null);
    draft.clearSetupDraft("acme-1", null);
  });
});
