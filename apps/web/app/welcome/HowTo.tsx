import Link from "next/link";

const DEMO = [
  {
    title: "Start the walkthrough",
    text: "Click Try the live demo. Three short cards explain what it watches and how it stays safe. Then choose Use the demo business.",
  },
  {
    title: "Set up the shop and the freezer",
    text: "Four steps, about two minutes: meet the business, let it read the manuals, watch thirty seconds of normal traffic, then start watching.",
  },
  {
    title: "Break something and watch it work",
    text: "Mission Control opens with a short tour. Break the shop (later you can open the freezer door). The agent finds the cause, writes a fix with a test, and waits 20 seconds before it acts. Approve it, cancel it, or let the countdown finish.",
  },
];

const PRODUCTION = [
  {
    title: "Sign in",
    text: "Click Connect your production. Signing in creates your organization. The demo stays open from Home — you do not need an account for that.",
  },
  {
    title: "Walk through Connect",
    text: "Name the system. For software, attach logs, the GitHub repo, and hosting. For equipment, attach the device. Then teach it what normal looks like, accept the uptime promise, pair your phone, and start watching.",
  },
  {
    title: "Stay in your account",
    text: "After that you use Connect, Members, Devices, and Usage. Invite teammates, pair phones for approvals, and see what you have used against the free allowance.",
  },
];

export default function HowTo() {
  return (
    <section aria-labelledby="how-to-title" className="mx-auto max-w-4xl">
      <div className="text-center">
        <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
          How to use it
        </p>
        <h1 id="how-to-title" className="mt-2 text-2xl font-semibold">
          A short guide
        </h1>
        <p className="mx-auto mt-2 max-w-xl text-sm text-text-muted">
          Two doors on Home. The demo needs no account. Production starts
          after you sign in. Mission Control only opens when a walkthrough
          finishes.
        </p>
      </div>

      <div className="mt-8 grid gap-3 lg:grid-cols-2">
        <article className="rounded-lg border border-border bg-surface p-5">
          <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
            Door 1 · No account
          </p>
          <h3 className="mt-1 text-base font-semibold">Try the live demo</h3>
          <p className="mt-2 text-xs text-text-muted">
            A live parts shop (AutoParts Lagos) and a cold-chain freezer are
            already running. About five minutes, start to first fix.
          </p>
          <ol className="mt-4 list-none space-y-3 p-0">
            {DEMO.map((step, i) => (
              <li key={step.title}>
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <span
                    aria-hidden
                    className="flex size-5 items-center justify-center rounded-full bg-brand text-[11px] tabular-nums text-on-brand"
                  >
                    {i + 1}
                  </span>
                  {step.title}
                </p>
                <p className="mt-1 ps-7 text-xs leading-relaxed text-text-muted">
                  {step.text}
                </p>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs leading-relaxed text-text-muted">
            On <span className="font-medium text-text">Read the manuals</span>,
            you can open Advanced setup if you want to upload your own
            documents or review every field the agent learned. The guided
            demo already does this for you with our copies.
          </p>
        </article>

        <article className="rounded-lg border border-border bg-surface p-5">
          <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
            Door 2 · Sign in
          </p>
          <h3 className="mt-1 text-base font-semibold">Connect your production</h3>
          <p className="mt-2 text-xs text-text-muted">
            Point the same agent at your software or your equipment. Free
            for now.
          </p>
          <ol className="mt-4 list-none space-y-3 p-0">
            {PRODUCTION.map((step, i) => (
              <li key={step.title}>
                <p className="flex items-center gap-2 text-sm font-semibold">
                  <span
                    aria-hidden
                    className="flex size-5 items-center justify-center rounded-full bg-brand text-[11px] tabular-nums text-on-brand"
                  >
                    {i + 1}
                  </span>
                  {step.title}
                </p>
                <p className="mt-1 ps-7 text-xs leading-relaxed text-text-muted">
                  {step.text}
                </p>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs leading-relaxed text-text-muted">
            On the <span className="font-medium text-text">Teach</span> step,
            set hard limits in the wizard, or open Advanced setup to upload
            manuals and review the extracted profile for that system.
          </p>
        </article>
      </div>

      <section
        id="phone"
        aria-labelledby="phone-title"
        className="mt-3 rounded-lg border border-border bg-surface p-5"
      >
        <p className="text-xs font-medium tracking-wide text-brand-cyan uppercase">
          Phone
        </p>
        <h3 id="phone-title" className="mt-1 text-base font-semibold">
          Download the Android app
        </h3>
        <p className="mt-2 text-xs leading-relaxed text-text-muted">
          One APK for both doors. Install it, then pair it to the demo
          shop or to your production system. Android only for now. Your
          phone may warn that the file is from outside the Play Store —
          that is expected.
        </p>
        <a
          href="/downloads/telemetry-agent.apk"
          className="mt-4 inline-flex items-center justify-center gap-2 rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-on-brand outline-none hover:bg-brand/90 focus-visible:ring-2 focus-visible:ring-brand"
        >
          Download APK
        </a>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div>
            <p className="text-sm font-semibold">Pair to the live demo</p>
            <ol className="mt-2 list-decimal space-y-1.5 ps-5 text-xs leading-relaxed text-text-muted">
              <li>Finish the demo walkthrough so Mission Control opens.</li>
              <li>Tap <span className="font-medium text-text">Pair</span> in the top bar and scan the QR.</li>
              <li>If the app asks for a token, leave it blank on the public demo, or type the token the person running a local API gave you.</li>
              <li>The phone shows the same report. Approve, cancel, or do nothing — if no one answers, it acts because you already gave permission.</li>
            </ol>
          </div>
          <div>
            <p className="text-sm font-semibold">Pair to production</p>
            <ol className="mt-2 list-decimal space-y-1.5 ps-5 text-xs leading-relaxed text-text-muted">
              <li>Sign in. Open <span className="font-medium text-text">Devices</span>.</li>
              <li>Label the phone and tap <span className="font-medium text-text">Get pairing code</span> (10 minutes).</li>
              <li>In the app, enter the API URL if asked, then claim that code.</li>
              <li>The phone is now tied to your organization. Revoke it on Devices to stop approvals at once.</li>
            </ol>
          </div>
        </div>
      </section>

      <div className="mt-3 rounded-lg border border-border bg-surface p-5">
        <h3 className="text-sm font-semibold">What you will see on Mission Control</h3>
        <ul className="mt-3 list-disc space-y-1.5 ps-5 text-xs leading-relaxed text-text-muted">
          <li>Each system as Watching, learning, or not set up yet.</li>
          <li>
            A live trace when something looks wrong — notice, diagnose, prove,
            then a 20-second cancel window.
          </li>
          <li>
            Nothing deploys on its own without that window. You stay in
            charge.
          </li>
          <li>
            Home and Live demo stay one click away. Pair the Android app
            (Download APK above) to see the same report on your phone.
          </li>
        </ul>
      </div>

      <p className="mt-6 text-center text-sm text-text-muted">
        Stuck, or something looks off?{" "}
        <Link
          href="/support"
          className="rounded font-medium text-brand-cyan underline outline-none hover:text-text focus-visible:ring-2 focus-visible:ring-brand"
        >
          Talk to support
        </Link>
        .
      </p>
    </section>
  );
}
