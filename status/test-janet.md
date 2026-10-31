# Janet status (tester)

Current block: T-E6 (T-E1–T-E5 done)
Environment: local API 127.0.0.1:8401 + shop 8402 + web localhost:3401 (2026-10-31; evidence below on origin/main 02d066b, branch rebased to 23bc080 at commit); Railway https://web-production-926b3.up.railway.app

Done:
- T-E1 PASS (local + Railway, all 5 checks)
- T-E2 PASS (local + Railway, both checks)
- T-E3 PASS (local, all 5 checks; 2 live runs used, see below)
- T-E4 PARTIAL (#1, #2, #4 PASS local + Railway spot-check; #3 BLOCKED — Clerk sign-in unavailable, see NEEDS)
- T-E1/T-E2 re-verified PASS on origin/main 9c487cf (welcome redesign + Get the app link)
- T-E5 BLOCKED (all 6 checks need a Clerk session; no test user — see NEEDS. Code observations recorded, nothing walked.)

Decisions:
- Stack runs with DATABASE_URL unset (worktree file store), GITHUB_TOKEN unset (no real PRs from test runs), FRIDGE_STREAM=1, SHOP_PORT=8402, CORS_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1):3401. No .env written; ../telemetry-agent/.env sourced into process env only.
- Interactive local walks use http://localhost:3401: Next.js dev `allowedDevOrigins` blocks client JS over 127.0.0.1 (dev-server-only artifact; SSR identical on both hosts; production/Railway unaffected). Method per walk is noted below.

Failures (end to end): none in T-E1–T-E3 (one live run failed on the known Modal flake; retried on the pinned local verifier — see T-E3 notes).

NEEDS FROM AKINGBADE:
- (cosmetic) Clerk sign-in form shows app name "Telementry" (typo for Telemetry?) — dashboard fix, not in repo (grep found nothing).
- (blocks T-E4#3 + T-E5) Clerk dev test user: verified email + password I can sign in with on localhost:3401. Headless signup stalls at Clerk bot protection ("Verifying your request"), and the local API only accepts real Clerk JWTs (RS256 via JWKS; no test issuer set). No credentials invented; nothing committed.

BLOCKED:
- T-E4#3 (lands on next page after sign-in) — needs a signed-in Clerk session.
- T-E5#1–#6 (all production-walkthrough checks) — needs a signed-in Clerk session.

Live runs (what · result · seconds · model):
- tour break-shop #1 (TA_VERIFY default/Modal) · FAILED at verify: Modal sandbox shut down mid-run, run crashed, veto never opened · spark diagnose + spark-open patch (run a85e71bb)
- tour break-shop #2 (TA_VERIFY=local) · veto opened, cancelled by tester · 105 s break→veto · spark diagnose (meta:muse-spark-1.3) + spark-open patch (baseten:meta-models/muse-spark-open-1026), run 93c24dce PASS (2/3 used)

## T-E1 · Home doors — PASS

Method: fresh-profile headless Chrome per walk (new user, signed out). Local interactive walks on localhost:3401 (see Decisions); SSR spot-checked on 127.0.0.1:3401 (same doors/hrefs). Railway walks on the production URL.

### Local (http://localhost:3401, SSR also 127.0.0.1:3401)

| # | Check | URL | Clicks | Expected | Got | Verdict |
|---|---|---|---|---|---|---|
| 1 | Home is only product + two doors | /welcome | none (land) | "Try the live demo" + "Connect your production", no How-to essay | Hero pitch + "Try the live demo →" (href /start) + "Connect your production" (href /signin?next=%2Fconnect); product cards only, no "Read the manuals"/"Door 1" essay | PASS |
| 2 | No skip | /welcome | none | No "Skip to Mission Control" | Absent from DOM + visible text | PASS |
| 3 | No Advanced setup door | /welcome | none | No link to /setup | No "/setup" in DOM | PASS |
| 4 | Menu | /welcome | none | How to → /guide, Support → /support | href="/guide" + href="/support" in header | PASS |
| 5a | / without walkthrough | / | none (fresh profile) | Lands on /welcome | Final URL http://localhost:3401/welcome, welcome hero rendered | PASS |
| 5b | /?skip=1 | /?skip=1 | none (fresh profile) | Lands on /welcome | Final URL http://localhost:3401/welcome | PASS |

### Railway (https://web-production-926b3.up.railway.app)

| # | Check | URL | Clicks | Expected | Got | Verdict |
|---|---|---|---|---|---|---|
| 1 | Home is only product + two doors | /welcome | none (land) | Same as local | Identical: both doors, hrefs /start and /signin?next=%2Fconnect, no essay | PASS |
| 2 | No skip | /welcome | none | No "Skip to Mission Control" | Absent | PASS |
| 3 | No Advanced setup door | /welcome | none | No link to /setup | Absent | PASS |
| 4 | Menu | /welcome | none | How to → /guide, Support → /support | Both hrefs present | PASS |
| 5a | / without walkthrough | / | none (fresh profile) | Lands on /welcome | Final URL …/welcome | PASS |
| 5b | /?skip=1 | /?skip=1 | none (fresh profile) | Lands on /welcome | Final URL …/welcome | PASS |

Notes:
- CORS_ORIGIN_REGEX is required for any non-:3000 local web port (repo default allows :3000 only; same convention as com-john status). Without it the demo door shows "Demo is waking up…" instead of "Try the live demo".
- 127.0.0.1 in dev: gate effect never runs because dev chunks are origin-blocked; not a product bug (localhost + Railway both redirect correctly). sha: origin/main 02d066b.
- origin/main moved to 23bc080 during T-E1 (4 web files, Suspense/build refactor, same rendered output; no API/shop change). /welcome re-walked on 23bc080: checks 1–4 still PASS.

## T-E2 · How to + Support — PASS

Method: fresh-profile headless Chrome per walk (new user, signed out). Local on localhost:3401, Railway on production URL.

### Local

| # | Check | URL | Clicks | Expected | Got | Verdict |
|---|---|---|---|---|---|---|
| 1 | /guide | /guide | none (land) | Own page; demo path + production path; Advanced setup only as step inside walkthroughs; link to Support | Title "How to use TelemetryAgent"; Door 1 demo steps + Door 2 production steps; "Advanced setup" appears 4× as plain text inside the two walkthrough notes ("On Read the manuals…" / "On the Teach step…"), zero hrefs to /setup; "Talk to support" href="/support" | PASS |
| 2 | /support | /support | none (land) | support@maxit.com.ng, 0803 695 4577 (tel:+2348036954577), link back to How to | mailto:support@maxit.com.ng; anchor tel:+2348036954577 with text "0803 695 4577"; "Read the how-to" href="/guide" | PASS |

### Railway

| # | Check | URL | Expected | Got | Verdict |
|---|---|---|---|---|---|
| 1 | /guide | /guide | Same as local | Same: demo + production paths, 4 plain-text Advanced setup mentions, 0 /setup hrefs, /support link | PASS |
| 2 | /support | /support | Same as local | Same: mailto + tel:+2348036954577 + /guide back-link | PASS |

## T-E3 · Demo walkthrough (no account) — PASS

Method: fresh-profile headless Chrome per walk (new user, signed out) on localhost:3401. Local only — the Railway demo world is shared/live, so no walkthrough or break-shop there. Base: origin/main 3d837c4 (API/shop unchanged since 02d066b).

| # | Check | URL | Clicks | Expected | Got | Verdict |
|---|---|---|---|---|---|---|
| 1 | /start | /start | land (card 1) → Card 3 tab | Three cards; last card has "Use the demo business" + "Connect my own system" (→ sign-in → /connect, not Advanced setup) | Card 1 "Your software and your equipment"; card 3 "Start with the demo business" with "Use the demo business" → /start/setup and "Connect my own system" → /signin?next=%2Fconnect; clicked the latter → landed on Clerk dev sign-in with next=/connect; zero /setup hrefs | PASS |
| 2 | /start/setup | /start/setup | "Set up my demo business" → "Read the manuals" → "Watch normal for 2 min" → "Start watching" | Four stages: meet → manuals → watch normal → start watching | Stage 1 both systems created (draft); stage 2 extracted facts with cites via saved readings; stage 3 baseline ready 100/learned after ~2 min; stage 4 "Start watching" → armed both → pushed to /?tour=1 | PASS |
| 3 | Advanced setup | /start/setup stage 2; /welcome | none | Appears on "Read the manuals", not on Home | "Advanced setup" href=/setup inside the stage-2 card ("…use Advanced setup — same teach-it-normal path"); /welcome has no /setup (T-E1) | PASS |
| 4 | Mission Control | /?tour=1 (before walkthrough; after) | "Break the shop" → Cancel at veto | Opens only after walkthrough; tour breaks shop; 20 s cancel window visible | Before arming: /?tour=1 bounced to /start/setup. After: Mission Control (both Watching) + tour 1/5; break → step 2 (8 s) → step 3 (13 s) → step 4 + veto "19s / Deploy the verified inventory patch to the shop / Cancel / Do it now" (105 s); Cancel → "Last: Cancelled — left for a human (dashboard)" | PASS |
| 5 | Still no login | all T-E3 walks | — | Never had to sign in | All walks fresh signed-out profiles; no auth wall on /start, /start/setup, /?tour=1; session stayed signed-out | PASS |

Notes:
- Run #1 crashed at verify (Modal sandbox shutdown mid-run; known flake per smoke_demo.sh comment). The run 500s instead of degrading to local Docker (fallback only covers ImportError/AuthError), and the tour shows no error — it just waits. Retried with TA_VERIFY=local (same pin as smoke_demo.sh); API restarted, demo world intact.
- Cancelled at the veto to avoid side effects (no fix applied, no PR — GITHUB_TOKEN unset anyway). Tour step 5 expects a PR link, unreachable here by design.
- sha: origin/main 3d837c4.

## Re-verify T-E1 + T-E2 on 9c487cf — PASS

origin/main moved (d51aad5 + 9c487cf: welcome redesign, "Get the app" menu, APK, docs). Re-walked fresh signed-out on localhost:3401: both doors + hrefs, no skip, no /setup, How to → /guide and Support → /support (new "Get the app" → /guide#phone also present, anchor exists), / and /?skip=1 → /welcome; /guide demo+production paths, 0 /setup hrefs, /support link; /support mailto + tel:+2348036954577 + /guide back-link. No T-E1/T-E2 regressions.

## T-E4 · Production gate — PARTIAL (#1, #2, #4 PASS; #3 BLOCKED)

Method: fresh-profile headless Chrome per walk (new user, signed out) on localhost:3401; Railway spot-checks read-only. Base 9c487cf.

| # | Check | URL | Clicks | Expected | Got | Verdict |
|---|---|---|---|---|---|---|
| 1 | Home Connect your production | /welcome | click "Connect your production" | Goes to /signin?next=/connect | Final URL /signin?next=%2Fconnect, Clerk dev sign-in shown | PASS |
| 2 | Direct production pages | /connect, /members, /devices, /usage | none (land each fresh) | Each redirects to /signin?next=<that page> | /connect → /signin?next=%2Fconnect; /members → …%2Fmembers; /devices → …%2Fdevices; /usage → …%2Fusage. Railway: /connect → /signin?next=%2Fconnect, /members → /signin?next=%2Fmembers | PASS |
| 3 | After sign-in | /members → sign-in | "Sign up" → fill email+password → Continue | Land on the next page, not demo Mission Control | BLOCKED: signup runs on Clerk hosted page (accounts.dev); submit stalls at "Verifying your request" bot protection headless. No verified test user available; local API accepts only real Clerk JWTs. Nothing invented or committed. | BLOCKED |
| 4 | Demo still public | /welcome | click "Try the live demo" while signed out | Demo reachable without sign-in | Landed on /start card 1 ("Your software and your equipment") | PASS |

## T-E5 · Production walkthrough — BLOCKED (all checks)

Per roadmap: cannot sign in → stop, NEEDS filed (see top). No Clerk dev/test session obtainable: headless signup stalls at Clerk bot protection, no verified test user exists, Google OAuth not usable headless, and the local API only accepts real Clerk JWTs (RS256 via JWKS). No credentials invented; no mock/dev-mode bypass used (NEXT_PUBLIC_COMMERCE_MOCK unset — the mock would not test the real Clerk path anyway). Base 041808e.

| # | Check | Verdict | Note |
|---|---|---|---|
| 1 | Sign-in creates / opens an org | BLOCKED | Needs sign-in. |
| 2 | /connect wizard steps | BLOCKED | Needs sign-in. Code (unwalked): SOFTWARE_TITLES = System → Logs → Repo → Hosting → Teach → Promise → Pair → Start; APPLIANCE_TITLES = System → Device → Teach → Promise → Pair → Start — matches the roadmap. |
| 3 | Teach hard limits + Advanced setup | BLOCKED | Needs sign-in. Code (unwalked): Teach step sets hard limits and links "Advanced setup" → /setup?system=… — matches. |
| 4 | Account chrome | BLOCKED | Needs sign-in. Code (unwalked): Connect/Members/Devices/Usage nav + How to + Get the app + Support + Live demo + org switcher + Sign out — matches (+ Get the app). |
| 5 | Signed-in Home | BLOCKED | Needs sign-in. Code (unwalked): DemoCta renders "Your production" → /connect when signed in; demo door unchanged. |
| 6 | Mission Control from production | BLOCKED | Needs sign-in. Code (unwalked): Wizard completion calls markOnboarded, which opens /. |

To unblock: one verified Clerk dev user (email + password) usable on localhost:3401, or an Akingbade-supervised live signup. Then re-walk T-E4#3 + T-E5#1–#6.
