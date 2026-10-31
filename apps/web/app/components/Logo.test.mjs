// Brand mark render: tile color, pulse path, size prop.
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

const Logo = loadComponent("Logo");

describe("Logo", () => {
  it("renders the brand tile with the pulse-check path", () => {
    const html = renderToStaticMarkup(React.createElement(Logo));
    assert.match(html, /<svg/);
    assert.match(html, /fill="#0866FF"/);
    assert.match(html, /M7 37 H20 L26 49/);
    assert.match(html, /aria-hidden="true"/);
  });

  it("respects the size prop and stays square", () => {
    const html = renderToStaticMarkup(
      React.createElement(Logo, { size: 44 })
    );
    assert.match(html, /width="44"/);
    assert.match(html, /height="44"/);
  });
});
