// Commercial sales-ready look: toggle + attribution render.
// Run: node --test app/components/  (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

const workdir = mkdtempSync(join(here, "..", "..", ".test-tmp-"));
process.on("exit", () => rmSync(workdir, { recursive: true, force: true }));

function loadComponent(name) {
  const source = readFileSync(join(here, `${name}.tsx`), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
      jsx: ts.JsxEmit.ReactJSX,
    },
  }).outputText;
  const out = join(workdir, `${name}.cjs`);
  writeFileSync(out, compiled);
  return require(out).default;
}

// ThemeToggle imports ../lib/theme (TS): compile it alongside so the
// component test exercises the real module boundary.
{
  const source = readFileSync(join(here, "..", "lib/theme.ts"), "utf8");
  const compiled = ts.transpileModule(source, {
    compilerOptions: {
      module: ts.ModuleKind.CommonJS,
      target: ts.ScriptTarget.ES2020,
    },
  }).outputText;
  writeFileSync(join(workdir, "theme-stub.cjs"), compiled);
  // lucide-react ships ESM-first; require() interop hands back
  // non-component objects, so stub the two icons as plain svg.
  writeFileSync(
    join(workdir, "lucide-stub.cjs"),
    "const React = require('react');" +
      "const icon = (n) => (p) => React.createElement('svg', { ...p, 'data-icon': n });" +
      "module.exports = { Moon: icon('moon'), Sun: icon('sun') };",
  );
  const Module = require("module");
  const original = Module._resolveFilename;
  Module._resolveFilename = function (request, ...rest) {
    if (request === "../lib/theme") return join(workdir, "theme-stub.cjs");
    if (request === "lucide-react") return join(workdir, "lucide-stub.cjs");
    return original.call(this, request, ...rest);
  };
}

const ThemeToggle = loadComponent("ThemeToggle");
const Attribution = loadComponent("Attribution");

describe("ThemeToggle", () => {
  it("renders a dark-mode switch with an accessible label", () => {
    const html = renderToStaticMarkup(React.createElement(ThemeToggle, {}));
    assert.match(html, /aria-label="Switch to dark mode"/);
    assert.match(html, /title="Switch to dark mode"/);
    assert.match(html, /<svg/);
  });
});

describe("Attribution", () => {
  it("says Built with Muse Spark and nothing brand-like", () => {
    const html = renderToStaticMarkup(React.createElement(Attribution, {}));
    assert.match(html, /Built with Muse Spark/);
    assert.doesNotMatch(html, /Meta TelemetryAgent|by Meta|Facebook|<svg|<img/);
  });
});
