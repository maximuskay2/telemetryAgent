// C-N3: commerce client shapes + mock behaviors (mocked fetch, no server).
// Run: node --test app/lib/  (from apps/web)
import { describe, it, beforeEach } from "node:test";
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
    if (request === "./commerce") return loadTs("lib/commerce.ts");
    if (request === "./commerce-mock") return loadTs("lib/commerce-mock.ts");
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

const commerce = loadTs("lib/commerce.ts");
const mockMod = loadTs("lib/commerce-mock.ts");

function jsonResponse(body, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  };
}

describe("CommerceClient", () => {
  it("sends the bearer token and parses orgs", async () => {
    const calls = [];
    const fetchFn = async (url, init) => {
      calls.push([url, init]);
      return jsonResponse({ orgs: [{ id: "o1", name: "Acme", role: "owner" }] });
    };
    const client = new commerce.CommerceClient({
      baseUrl: "http://api",
      getToken: () => "tok",
      fetchFn,
    });
    const out = await client.listOrgs();
    assert.equal(out.orgs[0].name, "Acme");
    assert.equal(calls[0][0], "http://api/api/orgs");
    assert.equal(calls[0][1].headers.Authorization, "Bearer tok");
  });

  it("omits auth when signed out", async () => {
    let headers = null;
    const client = new commerce.CommerceClient({
      baseUrl: "http://api",
      fetchFn: async (url, init) => {
        headers = init.headers;
        return jsonResponse({ orgs: [] });
      },
    });
    await client.listOrgs();
    assert.ok(!("Authorization" in headers));
  });

  it("throws CommerceError with status on 403", async () => {
    const client = new commerce.CommerceClient({
      baseUrl: "http://api",
      fetchFn: async () => jsonResponse({ detail: "no" }, 403),
    });
    await assert.rejects(client.listMembers("o1"), (err) => {
      assert.ok(err instanceof commerce.CommerceError);
      assert.equal(err.status, 403);
      return true;
    });
  });

  it("encodes ids and posts JSON bodies", async () => {
    const calls = [];
    const client = new commerce.CommerceClient({
      baseUrl: "http://api",
      fetchFn: async (url, init) => {
        calls.push([url, init]);
        return jsonResponse({ invite: { token: "t", expires_at: 0 } });
      },
    });
    await client.inviteMember("o/1", "b@x.co", "member");
    assert.equal(calls[0][0], "http://api/api/orgs/o%2F1/invites");
    assert.deepEqual(JSON.parse(calls[0][1].body), {
      email: "b@x.co",
      role: "member",
    });
  });

  it("requests usage with a period", async () => {
    let url = "";
    const client = new commerce.CommerceClient({
      baseUrl: "http://api",
      fetchFn: async (u) => {
        url = u;
        return jsonResponse({ fix_runs_used: 0 });
      },
    });
    await client.getUsage("o1", "month");
    assert.equal(url, "http://api/api/orgs/o1/usage?period=month");
  });

  it("default fetch delegates to global fetch (browser-safe)", async () => {
    // Regression: a bare `fetch` reference detached from window throws
    // "Illegal invocation" in browsers; the client must call it bound.
    const seen = [];
    const realFetch = globalThis.fetch;
    globalThis.fetch = async (...args) => {
      seen.push(args);
      return jsonResponse({ orgs: [] });
    };
    try {
      const client = new commerce.CommerceClient({ baseUrl: "http://api" });
      await client.listOrgs();
    } finally {
      globalThis.fetch = realFetch;
    }
    assert.equal(seen.length, 1);
    assert.equal(seen[0][0], "http://api/api/orgs");
  });
});

describe("blockedReasons", () => {
  const base = {
    fix_runs_used: 3, fix_runs_limit: 30,
    cost_used_usd: 1.2, cost_ceiling_usd: 25.0,
    systems_used: 1, systems_limit: 3,
    devices_used: 1, devices_limit: 5,
    by_language: {},
  };
  it("is empty inside the allowance", () => {
    assert.deepEqual(commerce.blockedReasons(base), []);
  });
  it("names each exhausted dimension (cost mirrored, no prices)", () => {
    const reasons = commerce.blockedReasons({
      ...base, fix_runs_used: 30, devices_used: 5,
    });
    assert.deepEqual(reasons, [
      "Free allowance reached: 30/30 fix runs",
      "Free allowance reached: 5/5 devices",
    ]);
    assert.ok(reasons.join(" ").match(/upgrade|checkout|price/i) === null);
  });
  it("blocks on the cost ceiling like the backend", () => {
    const reasons = commerce.blockedReasons({
      ...base, cost_used_usd: 25.0,
    });
    assert.deepEqual(reasons, [
      "Free allowance reached: $25.00/$25.00 estimated cost",
    ]);
  });
});

describe("MockCommerceApi", () => {
  let api;
  beforeEach(() => {
    api = new mockMod.MockCommerceApi();
  });

  it("lists orgs, members, devices", async () => {
    assert.equal((await api.listOrgs()).orgs.length, 2);
    assert.equal((await api.listMembers("org_acme")).members.length, 3);
    assert.equal((await api.listDevices("org_acme")).devices.length, 1);
  });

  it("viewer cannot invite, remove or revoke (403)", async () => {
    api.role = "viewer";
    for (const call of [
      () => api.inviteMember("org_acme", "x@y.co", "member"),
      () => api.removeMember("org_acme", "usr_3"),
      () => api.revokeDevice("org_acme", "dev_1"),
      () => api.deleteOrg("org_acme"),
    ]) {
      await assert.rejects(call, (err) => err.status === 403);
    }
  });

  it("admin cannot remove owners or invite owners", async () => {
    api.role = "admin";
    await assert.rejects(api.removeMember("org_acme", "usr_1"),
      (err) => err.status === 403);
    await assert.rejects(api.inviteMember("org_acme", "x@y.co", "owner"),
      (err) => err.status === 403);
  });

  it("pair validates the label and claim validates the code", async () => {
    await assert.rejects(api.pairDevice("org_acme", "  "),
      (err) => err.status === 400);
    const pair = await api.pairDevice("org_acme", "Pixel");
    assert.match(pair.code, /^\d{3}-\d{3}$/);
    await assert.rejects(api.claimDevice("nope"),
      (err) => err.status === 400);
    const claim = await api.claimDevice("123-456");
    assert.equal(claim.org_id, "org_acme");
  });

  it("404s unknown orgs, members and devices", async () => {
    await assert.rejects(api.listMembers("nope"), (err) => err.status === 404);
    await assert.rejects(api.removeMember("org_acme", "nope"),
      (err) => err.status === 404);
    await assert.rejects(api.revokeDevice("org_acme", "nope"),
      (err) => err.status === 404);
    await assert.rejects(api.acceptInvite("nope"), (err) => err.status === 404);
  });

  it("revoke sticks and usage has the §8.4 shape", async () => {
    await api.revokeDevice("org_acme", "dev_1");
    assert.equal((await api.listDevices("org_acme")).devices[0].revoked, true);
    const usage = await api.getUsage("org_acme");
    for (const key of ["fix_runs_used", "fix_runs_limit", "systems_used",
      "systems_limit", "devices_used", "devices_limit", "by_language"]) {
      assert.ok(key in usage, key);
    }
  });
});
