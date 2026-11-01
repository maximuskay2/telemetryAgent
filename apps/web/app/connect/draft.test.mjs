// Draft store round-trips wizard progress per system.
// Run: node --test app/connect/ (from apps/web)
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

const draft = loadTs("connect/draft.ts");

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
  kind: "software",
  name: "Acme",
  repoPerms: null,
  hostingKind: null,
};

describe("connect drafts", () => {
  it("saves and reloads progress per system", () => {
    const store = memStore();
    draft.saveDraft(DATA, 3, store);
    const drafts = draft.loadDrafts(store);
    assert.equal(drafts["acme-1"].index, 3);
    assert.equal(drafts["acme-1"].data.name, "Acme");
  });

  it("keeps systems independent and clears on finish", () => {
    const store = memStore();
    draft.saveDraft(DATA, 2, store);
    draft.saveDraft({ ...DATA, systemId: "acme-2", name: "B" }, 5, store);
    assert.equal(Object.keys(draft.loadDrafts(store)).length, 2);
    draft.clearDraft("acme-1", store);
    const rest = draft.loadDrafts(store);
    assert.equal(Object.keys(rest).length, 1);
    assert.ok("acme-2" in rest);
  });

  it("ignores corrupt or missing storage", () => {
    assert.deepEqual(draft.loadDrafts(memStore()), {});
    assert.deepEqual(
      draft.loadDrafts(memStore({ ta_connect_drafts: "{nope" })),
      {},
    );
    assert.deepEqual(draft.loadDrafts(null), {});
    draft.saveDraft(DATA, 1, null);
    draft.clearDraft("acme-1", null);
  });

  it("names the resume step from titles", () => {
    assert.equal(
      draft.draftStepTitle({ data: DATA, index: 2, updatedAt: 0 }, [
        "System",
        "Logs",
        "Repo",
      ]),
      "Repo",
    );
  });
});
