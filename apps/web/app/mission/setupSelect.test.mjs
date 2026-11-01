// Mission gate: draft selection (guided + manual) comes before Mission
// Control until a system is armed and watching.
// Run: node --test app/mission/ (from apps/web)
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

describe("mission gate", () => {
  it("shows draft selection while nothing is armed", () => {
    const panes = read("mission/Panes.tsx");
    assert.ok(panes.includes("SetupSelect"));
    assert.ok(panes.includes('s.status === "armed"'));
    assert.ok(panes.includes("systemsLoaded"));
  });

  it("lists guided and manual drafts side by side", () => {
    const select = read("mission/SetupSelect.tsx");
    assert.ok(select.includes("Guided setup drafts"));
    assert.ok(select.includes("Manual setup drafts"));
    assert.ok(select.includes("/connect?resume="));
    assert.ok(select.includes("/setup?system="));
    assert.ok(select.includes("STEP_LABELS"));
  });

  it("unifies drafts with the account's server systems", () => {
    const select = read("mission/SetupSelect.tsx");
    assert.ok(select.includes("mergeResumeEntries"));
    assert.ok(select.includes("not armed yet"));
    const panes = read("mission/Panes.tsx");
    assert.ok(
      panes.includes("<SetupSelect systems={systems} />"),
      "gate feeds server systems to the selector",
    );
  });

  it("keeps the tour bounce to the guided setup", () => {
    const select = read("mission/SetupSelect.tsx");
    assert.ok(select.includes('get("tour") === "1"'));
    assert.ok(select.includes('router.replace("/start/setup")'));
  });

  it("deep-resumes wizard drafts from the gate", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes('get("resume")'));
    assert.ok(wizard.includes("resumeDraft(local)"));
    assert.ok(wizard.includes("resumeServer(server)"));
  });

  it("persists manual setup progress as drafts", () => {
    const setup = read("setup/page.tsx");
    assert.ok(setup.includes("saveSetupDraft"));
    assert.ok(setup.includes("clearSetupDraft"));
    assert.ok(setup.includes("loadSetupDrafts"));
  });
});
