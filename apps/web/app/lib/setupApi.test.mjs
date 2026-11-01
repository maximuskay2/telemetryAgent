// setupApi carries the session (wizard profile reads 404'd without the
// org header: the API read the file store instead of the org's rows).
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

const moduleCache = {};
function loadTs(relativePath) {
  if (moduleCache[relativePath]) return moduleCache[relativePath];
  const source = readFileSync(join(appDir, relativePath), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  const module = { exports: {} };
  const localRequire = (request) => {
    if (request === "./api") return loadTs("lib/api.ts");
    if (request === "./sessionAuth") return loadTs("lib/sessionAuth.ts");
    return require(request);
  };
  new Function("module", "exports", "require", compiled)(
    module,
    module.exports,
    localRequire,
  );
  moduleCache[relativePath] = module.exports;
  return module.exports;
}

const setupApi = loadTs("lib/setupApi.ts");
const { setSessionAuthProvider } = loadTs("lib/sessionAuth.ts");

function stubFetch() {
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push([url, init]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ profile: {}, conflicts: [], feedback: [] }),
    };
  };
  return seen;
}

describe("setupApi auth", () => {
  it("sends no session headers when signed out", async () => {
    const seen = stubFetch();
    await setupApi.getProfile("sys1");
    assert.equal(seen[0][0].endsWith("/api/systems/sys1/profile"), true);
    const headers = seen[0][1].headers;
    assert.ok(!("Authorization" in headers));
    assert.ok(!("X-Org-Id" in headers));
  });

  it("sends the session token and org once provided", async () => {
    const seen = stubFetch();
    setSessionAuthProvider(() => ({ token: "jwt123", orgId: "org1" }));
    await setupApi.getProfile("sys1");
    const headers = seen[0][1].headers;
    assert.equal(headers.Authorization, "Bearer jwt123");
    assert.equal(headers["X-Org-Id"], "org1");
  });
});
