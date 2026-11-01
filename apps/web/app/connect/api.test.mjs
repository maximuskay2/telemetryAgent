// Connect API client sends the session (N-R4 fix): production routes
// 401 without Authorization + X-Org-Id.
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
    if (request === "../lib/api") return loadTs("lib/api.ts");
    if (request === "../lib/sessionAuth") return loadTs("lib/sessionAuth.ts");
    if (request === "../types/production") return {};
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

const api = loadTs("connect/api.ts");

function stubFetch() {
  const seen = [];
  globalThis.fetch = async (url, init) => {
    seen.push([url, init]);
    return {
      ok: true,
      status: 200,
      json: async () => ({ system_id: "sys1", name: "n", kind: "software" }),
    };
  };
  return seen;
}

describe("connect api auth", () => {
  it("sends no session headers when signed out", async () => {
    const seen = stubFetch();
    await api.createSystem({ name: "n", kind: "software" });
    const headers = seen[0][1].headers;
    assert.ok(!("Authorization" in headers));
    assert.ok(!("X-Org-Id" in headers));
  });

  it("sends the session token and org once provided", async () => {
    const seen = stubFetch();
    const { setSessionAuthProvider } = loadTs("lib/sessionAuth.ts");
    setSessionAuthProvider(() => ({ token: "jwt123", orgId: "org1" }));
    await api.createSystem({ name: "n", kind: "software" });
    const headers = seen[0][1].headers;
    assert.equal(headers.Authorization, "Bearer jwt123");
    assert.equal(headers["X-Org-Id"], "org1");
  });

  it("retries once with a fresh token after a 401", async () => {
    const seen = [];
    let calls = 0;
    globalThis.fetch = async (url, init) => {
      seen.push(init.headers);
      calls += 1;
      if (calls === 1) {
        return { ok: false, status: 401, json: async () => ({}) };
      }
      return {
        ok: true,
        status: 200,
        json: async () => ({ system_id: "sys1", name: "n", kind: "software" }),
      };
    };
    const { setSessionAuthProvider, setSessionAuthRefresher } = loadTs(
      "lib/sessionAuth.ts",
    );
    setSessionAuthProvider(() => ({ token: "stale", orgId: "org1" }));
    setSessionAuthRefresher(async () => "fresh123");
    await api.createSystem({ name: "n", kind: "software" });
    assert.equal(seen.length, 2);
    assert.equal(seen[0].Authorization, "Bearer stale");
    assert.equal(seen[1].Authorization, "Bearer fresh123");
    setSessionAuthRefresher(async () => null);
  });

  it("surfaces the 401 when refresh is impossible", async () => {
    globalThis.fetch = async () => ({
      ok: false,
      status: 401,
      json: async () => ({ detail: "sign-in required" }),
    });
    const { setSessionAuthProvider, setSessionAuthRefresher } = loadTs(
      "lib/sessionAuth.ts",
    );
    setSessionAuthProvider(() => ({ token: null, orgId: null }));
    setSessionAuthRefresher(async () => null);
    await assert.rejects(
      api.createSystem({ name: "n", kind: "software" }),
      /sign-in required/,
    );
  });
});
