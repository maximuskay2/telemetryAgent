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

  it("judged path works fully signed out", () => {
    // /welcome → /start → /start/setup → /start/phone → /?tour=1 →
    // WrapUp → /incidents/:id must never need an account (Clerk dev
    // limits must not be able to break the judged demo).
    for (const file of [
      "welcome/page.tsx",
      "start/page.tsx",
      "start/setup/page.tsx",
      "start/phone/page.tsx",
      "mission/Tour.tsx",
      "mission/WrapUp.tsx",
      "mission/FirstVisitGate.tsx",
      "incidents/[id]/page.tsx",
    ]) {
      const src = read(file);
      for (const token of [
        "useSession",
        "getSessionAuth",
        "sessionAuthHeaders",
        "RequireAuth",
        "signInHref",
      ]) {
        assert.ok(!src.includes(token), `${file} must not use ${token}`);
      }
    }
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
      "dashboard/page.tsx",
      "keys/page.tsx",
      "members/page.tsx",
      "devices/page.tsx",
      "usage/page.tsx",
    ]) {
      const text = read(page);
      assert.ok(text.includes("RequireAuth"), page);
    }
  });

  it("sign-in returns to next, defaulting to /dashboard, not Mission Control", () => {
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

  it("mission control loads connected production systems", () => {
    const systems = read("hooks/useSystems.ts");
    assert.ok(systems.includes("getSessionAuth"), "lists with the session");
    assert.ok(systems.includes("X-Org-Id"), "org-scoped list");
    const left = read("mission/LeftPane.tsx");
    assert.ok(left.includes("ProdTile"), "renders production tiles");
    assert.ok(left.includes("DEMO_SYSTEM_IDS"), "demo tiles stay demo-only");
    const tile = read("mission/ProdTile.tsx");
    assert.ok(tile.includes("/connect?system="), "links connections");
    assert.ok(tile.includes("/setup?system="), "links setup");
  });

  it("mission control streams and reads with the session", () => {
    const stream = read("hooks/useAgentStream.ts");
    assert.ok(stream.includes("?token="), "socket joins the org channel");
    assert.ok(stream.includes("demo=1"), "socket keeps the demo channel");
    const state = read("mission/state.tsx");
    assert.ok(
      state.includes("setSessionAuthProvider(getSessionAuth)"),
      "mission wires the shared session",
    );
    for (const file of [
      "mission/TracePane.tsx",
      "mission/IncidentDrawer.tsx",
      "hooks/useActions.ts",
      "mission/VetoRing.tsx",
      "hooks/useGate.ts",
    ]) {
      assert.ok(
        read(file).includes("sessionAuthHeaders()"),
        `${file} carries the session`,
      );
    }
  });

  it("connect runs hosting last among setup steps, before the promise", () => {
    // Canonical step lists live in connect/draft.ts (wizard + gate share).
    const draft = read("connect/draft.ts");
    const titles = draft.slice(
      draft.indexOf("SOFTWARE_STEP_TITLES"),
      draft.indexOf("APPLIANCE_STEP_TITLES"),
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

  it("connect keeps unfinished runs as resumable drafts", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("saveDraft(data, index)"), "persists progress");
    assert.ok(
      wizard.includes("clearDraft(data.systemId)"),
      "clears on finish",
    );
    assert.ok(wizard.includes("Continue setup"), "offers resume");
    assert.ok(wizard.includes("DraftPicker"), "picks a draft");
  });

  it("connect entry shows drafts first, not the create flow", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(
      wizard.includes("data == null && picking"),
      "picker gates on entry state",
    );
    assert.ok(
      wizard.includes("!showPicker && ("),
      "stepper hides while picking a draft",
    );
    assert.ok(
      wizard.indexOf("<DraftPicker") < wizard.indexOf("<StepName"),
      "drafts render before the create form",
    );
    assert.ok(
      wizard.includes("+ Start a new system"),
      "picker offers create-new as the explicit choice",
    );
  });

  it("connect teach step reads manuals or takes typed limits", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("Read a manual"), "upload block offered");
    assert.ok(
      wizard.includes('accept=".pdf,.png,.jpg,.jpeg,.txt,.md"'),
      "pdf, photo, md, text accepted",
    );
    assert.ok(
      wizard.includes("Or paste the working principle"),
      "paste path offered",
    );
    assert.ok(
      wizard.includes("uploadSystemDocuments(systemId"),
      "extracts through the documents endpoint",
    );
    assert.ok(
      wizard.includes("+ Add limit"),
      "hand-typed limits stay available",
    );
  });

  it("connect unifies browser drafts with account systems", () => {
    const wizard = read("connect/Wizard.tsx");
    assert.ok(wizard.includes("listSystems()"), "loads the account");
    assert.ok(
      wizard.includes("mergeResumeEntries(drafts, serverSystems)"),
      "merges drafts with server systems",
    );
    assert.ok(
      wizard.includes("resumeServer(entry.system)"),
      "server entries resume without re-creating",
    );
    assert.ok(
      wizard.includes("not armed yet"),
      "server entries show their status",
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
