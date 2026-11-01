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

  it("sign-in breaks the Clerk-signed-in/API-rejected redirect loop", () => {
    const signin = read("signin/[[...rest]]/page.tsx");
    assert.ok(signin.includes("useAuth"), "reads the Clerk session");
    assert.ok(
      signin.includes('isSignedIn && status === "signed-out"'),
      "detects stuck sessions instead of re-rendering <SignIn/>",
    );
    assert.ok(signin.includes("Try again"), "offers a way out");
  });

  it("connect repo step explains where the GitHub token comes from", () => {
    const steps = read("connect/ConnSteps.tsx");
    assert.ok(steps.includes("github.com/settings/personal-access-tokens"));
    assert.ok(steps.includes("Contents = Read and write"));
    assert.ok(steps.includes("Pull requests = Read"));
  });

  it("connect runs hosting last among setup steps, before the promise", () => {
    const wizard = read("connect/Wizard.tsx");
    const titles = wizard.slice(
      wizard.indexOf("SOFTWARE_TITLES"),
      wizard.indexOf("APPLIANCE_TITLES"),
    );
    const order = ["System", "Logs", "Repo", "Teach", "Hosting", "Promise"];
    const positions = order.map((title) => titles.indexOf(`"${title}"`));
    assert.ok(
      positions.every((pos) => pos >= 0),
      "all setup steps listed",
    );
    assert.deepEqual(
      [...positions].sort((a, b) => a - b),
      positions,
      "hosting comes after teach, before the promise",
    );
  });

  it("connect hosting step guides webhooks and can be skipped", () => {
    const steps = read("connect/ConnSteps.tsx");
    assert.ok(steps.includes("X-Telemetry-Signature"), "signing contract");
    assert.ok(steps.includes("whsec_"), "secret is user-invented");
    assert.ok(steps.includes('onSkip={() => onDone("", "")}'), "skippable");
    assert.ok(
      steps.includes("work without hosting"),
      "says what works without it",
    );
  });

  it("demo Mission Control does not embed members/devices/usage icons", () => {
    const nav = read("commerce/AccountNav.tsx");
    assert.ok(nav.includes("Connect production") || nav.includes("Your production"));
    assert.ok(!nav.includes('href="/members"'));
    assert.ok(!nav.includes('href="/devices"'));
    assert.ok(!nav.includes('href="/usage"'));
  });
});
