// Commercial sales-ready look: theme logic, tokens, fonts, brand rule.
// Run: node --test app/lib/  (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
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

const theme = loadTs("lib/theme.ts");

function runInitScript({ stored, throws = false }) {
  const calls = [];
  const document = {
    documentElement: {
      dataset: {},
      setAttribute: (k, v) => calls.push(["set", k, v]),
    },
  };
  const storage = throws
    ? { getItem: () => { throw new Error("denied"); } }
    : { getItem: () => stored };
  new Function("document", "localStorage", theme.THEME_INIT_SCRIPT)(
    document,
    storage,
  );
  return calls;
}

describe("theme choice", () => {
  it("defaults to light without a saved choice", () => {
    assert.equal(theme.resolveTheme(null), "light");
    assert.equal(theme.resolveTheme(undefined), "light");
    assert.equal(theme.resolveTheme(""), "light");
    assert.equal(theme.resolveTheme("light"), "light");
    assert.equal(theme.resolveTheme("garbage"), "light");
  });

  it("honors a saved dark choice", () => {
    assert.equal(theme.resolveTheme("dark"), "dark");
  });

  it("persists under a stable key", () => {
    assert.equal(theme.THEME_STORAGE_KEY, "ta-theme");
  });

  it("init script applies saved dark before paint", () => {
    assert.deepEqual(runInitScript({ stored: "dark" }), [
      ["set", "data-theme", "dark"],
    ]);
  });

  it("init script leaves first visits in light", () => {
    assert.deepEqual(runInitScript({ stored: null }), []);
    assert.deepEqual(runInitScript({ stored: "light" }), []);
  });

  it("init script never throws (private mode)", () => {
    assert.deepEqual(runInitScript({ stored: "dark", throws: true }), []);
  });
});

describe("surface tokens", () => {
  const tokens = readFileSync(join(appDir, "tokens.css"), "utf8");
  const root = tokens.split('[data-theme="dark"]')[0];
  const dark = tokens.split('[data-theme="dark"]')[1];

  it("light is the default root", () => {
    for (const [name, hex] of [
      ["--bg", "#f0f2f5"],
      ["--surface", "#ffffff"],
      ["--text", "#050505"],
      ["--brand", "#0866ff"],
      ["--on-brand", "#ffffff"],
    ]) {
      assert.match(root, new RegExp(`${name}:\\s*${hex}`, "i"), name);
    }
    assert.match(root, /color-scheme:\s*light/);
  });

  it("dark keeps Facebook charcoal with the same blue", () => {
    assert.ok(dark, "missing [data-theme=dark] block");
    for (const [name, hex] of [
      ["--bg", "#18191a"],
      ["--surface", "#242526"],
      ["--brand", "#0866ff"],
      ["--on-brand", "#ffffff"],
    ]) {
      assert.match(dark, new RegExp(`${name}:\\s*${hex}`, "i"), name);
    }
    assert.match(dark, /color-scheme:\s*dark/);
  });

  it("classic stays pinned to its dark look", () => {
    const legacy = readFileSync(join(appDir, "styles.css"), "utf8");
    assert.match(legacy, /\.legacy \{[^}]*--bg: #0b0e10[^}]*--text: #e7eeea/s);
  });
});

describe("Meta fonts", () => {
  it("UI type is Optimistic, then Helvetica / Arial", () => {
    const tailwind = readFileSync(join(appDir, "tailwind.css"), "utf8");
    assert.ok(
      tailwind.includes("--font-sans: Optimistic, Helvetica, Arial, sans-serif;"),
    );
    assert.ok(
      tailwind.includes("font-family: Optimistic, Helvetica, Arial, sans-serif;"),
    );
  });

  it("monospace stays for code, logs and IDs", () => {
    const tailwind = readFileSync(join(appDir, "tailwind.css"), "utf8");
    assert.ok(tailwind.includes("--font-mono:"));
  });

  it("never ships Optimistic font files", () => {
    const hits = [];
    const walk = (dir) => {
      for (const entry of readdirSync(dir)) {
        if (entry === "node_modules" || entry === ".next") continue;
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          walk(full);
        } else if (/optimistic/i.test(entry)) {
          hits.push(full);
        }
      }
    };
    walk(join(appDir, ".."));
    assert.deepEqual(hits, []);
    const css = readFileSync(join(appDir, "tailwind.css"), "utf8") +
      readFileSync(join(appDir, "tokens.css"), "utf8") +
      readFileSync(join(appDir, "styles.css"), "utf8");
    assert.ok(!/@font-face/i.test(css), "no local @font-face expected");
  });
});

describe("status words", () => {
  it("are unchanged", () => {
    const badge = readFileSync(join(appDir, "ui/Badge.tsx"), "utf8");
    for (const word of [
      "Healthy",
      "Normal · ignored",
      "Observing",
      "Incident",
      "Hard limit",
      "Agent",
      "Learning",
      "Setup needed",
    ]) {
      assert.ok(badge.includes(`word: "${word}"`), word);
    }
  });
});

describe("brand rule", () => {
  const BANNED = [
    /\bby Meta\b/,
    /Meta TelemetryAgent/,
    /TelemetryAgent by Meta/,
    /\bfrom Meta\b/,
    /\ba Meta (product|app|company)\b/,
    /\bFacebook\b/,
  ];

  function* sourceFiles(dir, exts) {
    for (const entry of readdirSync(dir)) {
      if (entry === "node_modules" || entry === ".next") continue;
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        yield* sourceFiles(full, exts);
      } else if (
        exts.some((ext) => entry.endsWith(ext)) &&
        !entry.includes(".test.")
      ) {
        yield full;
      }
    }
  }

  function stripComments(text) {
    return text
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/(^|\n)\s*\/\/.*$/gm, "$1");
  }

  it("no Meta/Facebook logos or ownership claims in web UI", () => {
    const hits = [];
    for (const file of sourceFiles(appDir, [".tsx", ".ts", ".css"])) {
      const text = stripComments(readFileSync(file, "utf8"));
      for (const pattern of BANNED) {
        if (pattern.test(text)) hits.push(`${file}: ${pattern}`);
      }
    }
    assert.deepEqual(hits, []);
  });

  it("no Meta/Facebook logos or ownership claims in the phone app", () => {
    const mobileLib = join(appDir, "..", "..", "mobile", "lib");
    const hits = [];
    for (const file of sourceFiles(mobileLib, [".dart"])) {
      const text = stripComments(readFileSync(file, "utf8"));
      for (const pattern of BANNED) {
        if (pattern.test(text)) hits.push(`${file}: ${pattern}`);
      }
    }
    assert.deepEqual(hits, []);
  });

  it("no logo asset files", () => {
    const hits = [];
    for (const root of [join(appDir, ".."), join(appDir, "..", "..", "mobile")]) {
      const walk = (dir) => {
        for (const entry of readdirSync(dir)) {
          if (["node_modules", ".next", "build", ".dart_tool"].includes(entry)) {
            continue;
          }
          const full = join(dir, entry);
          if (statSync(full).isDirectory()) {
            walk(full);
          } else if (/meta[-_ ]?logo|facebook[-_ ]?logo|fb[-_ ]?logo/i.test(entry)) {
            hits.push(full);
          }
        }
      };
      walk(root);
    }
    assert.deepEqual(hits, []);
  });

  it("attribution is present on welcome and Mission Control", () => {
    const attribution = readFileSync(
      join(appDir, "components/Attribution.tsx"),
      "utf8",
    );
    assert.ok(attribution.includes("Built with Muse Spark"));
    for (const page of ["welcome/page.tsx", "page.tsx"]) {
      const text = readFileSync(join(appDir, page), "utf8");
      assert.ok(text.includes("Attribution"), page);
    }
  });
});
