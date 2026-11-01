// Signed-in hub: systems, drafts, recent runs, destinations — and no
// demo nudges on account chrome.
// Run: node --test app/dashboard/ (from apps/web)
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

describe("user dashboard", () => {
  it("is the signed-in hub behind auth", () => {
    const page = read("dashboard/page.tsx");
    assert.ok(page.includes("RequireAuth"));
    assert.ok(page.includes("AccountChrome"));
    assert.ok(page.includes("Your dashboard"));
    assert.ok(page.includes("markOnboarded"));
  });

  it("covers systems, drafts, runs, and destinations", () => {
    const page = read("dashboard/page.tsx");
    assert.ok(page.includes("useSystems"));
    assert.ok(page.includes("mergeResumeEntries"));
    assert.ok(page.includes("/api/runs"));
    assert.ok(page.includes("/incidents/"));
    for (const href of [
      'href="/"',
      'href="/connect"',
      'href="/members"',
      'href="/devices"',
      'href="/usage"',
      'href="/support"',
    ]) {
      assert.ok(page.includes(href), href);
    }
  });

  it("keeps demo nudges off signed-in chrome", () => {
    const chrome = read("commerce/AccountChrome.tsx");
    assert.ok(!chrome.includes("Live demo"));
    assert.ok(chrome.includes("Mission Control"));
    assert.ok(chrome.includes('href="/dashboard"'));
    for (const file of [
      "commerce/AccountNav.tsx",
      "welcome/DemoCta.tsx",
      "welcome/WelcomeHeader.tsx",
    ]) {
      assert.ok(
        read(file).includes('"/dashboard"'),
        `${file} points production at the hub`,
      );
    }
  });
});
