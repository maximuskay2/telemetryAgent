import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appDir = join(dirname(fileURLToPath(import.meta.url)), "..");

function read(rel) {
  return readFileSync(join(appDir, rel), "utf8");
}

describe("gated product flow", () => {
  it("welcome has two doors: public demo and signed-in production", () => {
    const cta = read("welcome/DemoCta.tsx");
    assert.ok(cta.includes('href="/start"'), "demo stays public");
    assert.ok(cta.includes("signInHref(\"/connect\")"), "production goes through sign-in");
    assert.ok(!cta.includes('href="/connect"') || cta.includes('status === "signed-in"'));
  });

  it("welcome has no skip-to-Mission-Control shortcut", () => {
    const welcome = read("welcome/page.tsx");
    assert.ok(!welcome.includes("Skip to Mission Control"));
    assert.ok(!welcome.includes("skip=1"));
    const gate = read("mission/FirstVisitGate.tsx");
    assert.ok(!gate.includes('skip") === "1"') && !gate.includes("skip=1"));
  });

  it("advanced setup lives on the teach-it-normal walkthrough steps", () => {
    const welcome = read("welcome/page.tsx");
    assert.ok(!welcome.includes('href="/setup"'), "home is not a door into /setup");
    const demoTeach = read("start/setup/page.tsx");
    assert.ok(demoTeach.includes('href="/setup"'));
    assert.ok(demoTeach.includes("Read the manuals"));
    const prodTeach = read("connect/Wizard.tsx");
    assert.ok(prodTeach.includes("/setup?system="));
    assert.ok(prodTeach.includes("StepTeach"));
  });

  it("how-to and support are their own menu pages, not on home", () => {
    const welcome = read("welcome/page.tsx");
    assert.ok(!welcome.includes("HowTo"));
    assert.ok(!welcome.includes("support@maxit.com.ng"));
    const guide = read("guide/page.tsx");
    assert.ok(guide.includes("HowTo"));
    const howTo = read("welcome/HowTo.tsx");
    assert.ok(howTo.includes("Try the live demo"));
    assert.ok(howTo.includes("Connect your production"));
    assert.ok(howTo.includes('href="/support"'));
    const header = read("welcome/WelcomeHeader.tsx");
    assert.ok(header.includes('href="/guide"'));
    assert.ok(header.includes('href="/support"'));
    const support = read("support/page.tsx");
    assert.ok(support.includes("support@maxit.com.ng"));
    assert.ok(support.includes("tel:+2348036954577"));
    assert.ok(support.includes("0803 695 4577"));
  });

  it("production pages require auth", () => {
    for (const page of [
      "connect/page.tsx",
      "members/page.tsx",
      "devices/page.tsx",
      "usage/page.tsx",
    ]) {
      const text = read(page);
      assert.ok(text.includes("RequireAuth"), page);
    }
  });

  it("sign-in returns to next, defaulting to /connect, not Mission Control", () => {
    const signin = read("signin/[[...rest]]/page.tsx");
    assert.ok(signin.includes("safeNext"));
    assert.ok(!signin.includes('forceRedirectUrl="/"'));
    assert.ok(!signin.includes('router.push("/")'));
  });

  it("demo Mission Control does not embed members/devices/usage icons", () => {
    const nav = read("commerce/AccountNav.tsx");
    assert.ok(nav.includes("Connect production") || nav.includes("Your production"));
    assert.ok(!nav.includes('href="/members"'));
    assert.ok(!nav.includes('href="/devices"'));
    assert.ok(!nav.includes('href="/usage"'));
  });
});
