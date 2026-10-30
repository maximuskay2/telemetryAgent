// L-N3: component test for DetectedLine (both acceptance cases).
// Dependency-free: transpiles the real .tsx with the repo's own typescript
// and renders it with react-dom/server. Run: node --test app/connect/
import { after, describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, mkdtempSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");

// Compile the real component into a temp dir *inside* apps/web so that
// react/jsx-runtime resolves from the project's own node_modules.
const workdir = mkdtempSync(join(here, "..", "..", ".test-tmp-"));
after(() => rmSync(workdir, { recursive: true, force: true }));

const source = readFileSync(join(here, "DetectedLine.tsx"), "utf8");
const compiled = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.CommonJS,
    target: ts.ScriptTarget.ES2020,
    jsx: ts.JsxEmit.ReactJSX,
  },
}).outputText;
const compiledPath = join(workdir, "DetectedLine.cjs");
writeFileSync(compiledPath, compiled);
const { DetectedLine } = require(compiledPath);

const render = (props) =>
  renderToStaticMarkup(React.createElement(DetectedLine, props));

describe("DetectedLine", () => {
  it("supported language shows Auto-fix ✓", () => {
    const html = render({ language: "typescript", autofix: true });
    assert.match(html, /Detected: TypeScript · Auto-fix ✓/);
  });

  it("unsupported language reads alerts and rollback only", () => {
    const html = render({ language: "c#", autofix: false });
    assert.match(html, /Detected: c# · alerts and rollback only/);
  });

  it("renders nothing until the backend sends a language", () => {
    assert.equal(render({}), "");
    assert.equal(render({ language: null, autofix: null }), "");
  });

  it("shows the language alone when autofix is unknown", () => {
    const html = render({ language: "go", autofix: null });
    assert.match(html, /Detected: Go/);
    assert.doesNotMatch(html, /Auto-fix|rollback/);
  });
});
