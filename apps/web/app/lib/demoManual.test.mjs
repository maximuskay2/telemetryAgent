// Visitor manuals in the guided demo: own-manual upload per side plus
// hints wherever profile rows are typed by hand.
// Run: node --test app/lib/ (from apps/web)
import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const appDir = join(here, "..");

function read(rel) {
  return readFileSync(join(appDir, rel), "utf8");
}

describe("profile section hints", () => {
  it("covers normal, behaviours, modes, failures, hard limits", () => {
    const table = read("setup/ReviewTable.tsx");
    for (const section of [
      "normal_ranges",
      "expected_behaviours",
      "modes",
      "failure_definitions",
      "hard_limits",
    ]) {
      assert.ok(table.includes(section), section);
    }
    assert.ok(table.includes("SECTION_HINTS"));
    assert.ok(table.includes("hint={SECTION_HINTS[section]}"));
  });

  it("shows the hints on the editable setup review", () => {
    const setup = read("setup/page.tsx");
    assert.ok(setup.includes("SECTION_HINTS"));
    for (const section of [
      "normal_ranges",
      "expected_behaviours",
      "modes",
      "failure_definitions",
      "hard_limits",
    ]) {
      assert.ok(
        setup.includes(`hint={SECTION_HINTS.${section}}`),
        section,
      );
    }
  });
});

describe("demo own-manual upload", () => {
  it("offers files plus a pasted note per demo system", () => {
    const page = read("start/setup/page.tsx");
    assert.ok(page.includes("Use your own manual"));
    assert.ok(page.includes('accept=".pdf,.png,.jpg,.jpeg,.txt,.md"'));
    assert.ok(page.includes("Or paste the working principle"));
    assert.ok(page.includes("Upload & extract"));
  });

  it("extracts through the systems documents endpoint", () => {
    const api = read("lib/setupApi.ts");
    assert.ok(api.includes("uploadSystemDocuments"));
    assert.ok(api.includes("/api/systems/${encodeURIComponent(systemId)}/documents"));
    assert.ok(api.includes("new FormData()"));
    const page = read("start/setup/page.tsx");
    assert.ok(page.includes("uploadSystemDocuments(systemId"));
  });
});
