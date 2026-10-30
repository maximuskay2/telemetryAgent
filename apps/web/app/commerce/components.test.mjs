// C-N3/C-N5: commerce component states (mocked data, no server).
// Run: node --test app/commerce/  (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, "..");
const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const workdir = mkdtempSync(join(appDir, "..", ".test-tmp-"));
process.on("exit", () => rmSync(workdir, { recursive: true, force: true }));

function compileTs(sourcePath) {
  const source = readFileSync(sourcePath, "utf8");
  return ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
}

{
  writeFileSync(
    join(workdir, "commerce-stub.cjs"),
    compileTs(join(appDir, "lib/commerce.ts")),
  );
  writeFileSync(
    join(workdir, "api-stub.cjs"),
    compileTs(join(appDir, "lib/api.ts")),
  );
  writeFileSync(
    join(workdir, "ui-stub.cjs"),
    "const React = require('react');" +
      "exports.Card = ({ title, children }) => React.createElement('section', null," +
      " React.createElement('h3', null, title), children);",
  );
  const Module = require("module");
  const original = Module._resolveFilename;
  Module._resolveFilename = function (request, ...rest) {
    if (request === "../lib/commerce") {
      return join(workdir, "commerce-stub.cjs");
    }
    if (request === "./api") return join(workdir, "api-stub.cjs");
    if (request === "../ui") return join(workdir, "ui-stub.cjs");
    return original.call(this, request, ...rest);
  };
}

writeFileSync(
  join(workdir, "components.cjs"),
  compileTs(join(here, "components.tsx")),
);
const ui = require(join(workdir, "components.cjs"));
const commerce = require(join(workdir, "commerce-stub.cjs"));
const render = (element) => renderToStaticMarkup(element);

const MEMBERS = [
  { user_id: "u1", email: "ada@acme.co", name: "Ada", role: "owner" },
  { user_id: "u2", email: "bob@acme.co", name: "Bob", role: "member" },
];

describe("MemberList", () => {
  it("shows members with roles and owner-only actions", () => {
    const html = render(
      React.createElement(ui.MemberList, {
        members: MEMBERS, selfId: "u1", canManage: true,
        onRemove: () => {}, onTransfer: () => {},
      }),
    );
    assert.match(html, /Ada/);
    assert.match(html, /bob@acme\.co/);
    assert.match(html, /owner/);
    assert.match(html, /Remove/);
    assert.match(html, /Make owner/);
  });

  it("hides actions for the viewer case", () => {
    const html = render(
      React.createElement(ui.MemberList, {
        members: MEMBERS, selfId: "u9", canManage: false,
        onRemove: () => {}, onTransfer: () => {},
      }),
    );
    assert.doesNotMatch(html, /Remove/);
    assert.doesNotMatch(html, /Make owner/);
  });
});

describe("ApiErrorView", () => {
  it("401 prompts sign-in", () => {
    const html = render(
      React.createElement(ui.ApiErrorView, {
        error: new commerce.CommerceError(401, "Signed out"),
      }),
    );
    assert.match(html, /Sign in required/);
    assert.match(html, /href="\/signin"/);
  });

  it("403 explains roles", () => {
    const html = render(
      React.createElement(ui.ApiErrorView, {
        error: new commerce.CommerceError(403, "API returned 403"),
      }),
    );
    assert.match(html, /Not allowed/);
    assert.match(html, /Ask an admin/);
  });
});

describe("DeviceList", () => {
  const DEVICES = [
    { id: "d1", label: "Pixel", created_at: 0, last_used_at: 0, revoked: false },
    { id: "d2", label: "Old", created_at: 0, last_used_at: 0, revoked: true },
  ];
  it("marks active vs revoked and gates revoke", () => {
    const html = render(
      React.createElement(ui.DeviceList, {
        devices: DEVICES, canManage: true, onRevoke: () => {},
      }),
    );
    assert.match(html, /active/);
    assert.match(html, /revoked/);
    assert.match(html, /Revoke/);
    const viewer = render(
      React.createElement(ui.DeviceList, {
        devices: DEVICES, canManage: false, onRevoke: () => {},
      }),
    );
    assert.doesNotMatch(viewer, /Revoke/);
  });
});

describe("UsageView", () => {
  const USAGE = {
    fix_runs_used: 30, fix_runs_limit: 30,
    cost_used_usd: 24.5, cost_ceiling_usd: 25.0,
    systems_used: 1, systems_limit: 3,
    devices_used: 1, devices_limit: 5,
    by_language: { python: { fix_runs: 30, cost_usd: 24.5 } },
  };
  it("shows allowance with why-blocked and no prices", () => {
    const html = render(React.createElement(ui.UsageView, { usage: USAGE }));
    assert.match(html, /30 of 30 free/);
    assert.match(html, /Free allowance reached: 30\/30 fix runs/);
    assert.match(html, /python/);
    assert.match(html, /30 runs/);
    assert.doesNotMatch(html, /\$/);
    assert.doesNotMatch(html, /cost/i);
    assert.doesNotMatch(html, /usd/i);
    assert.doesNotMatch(html, /24\.5/);
  });
});

describe("OrgSwitcher", () => {
  it("lists orgs with roles and hides when empty", () => {
    const html = render(
      React.createElement(ui.OrgSwitcher, {
        orgs: [
          { id: "o1", name: "Acme", role: "owner" },
          { id: "o2", name: "Demo", role: "viewer" },
        ],
        activeId: "o1",
        onSwitch: () => {},
      }),
    );
    assert.match(html, /Acme \(owner\)/);
    assert.match(html, /Demo \(viewer\)/);
    const empty = render(
      React.createElement(ui.OrgSwitcher, {
        orgs: [], activeId: null, onSwitch: () => {},
      }),
    );
    assert.equal(empty, "");
  });
});
