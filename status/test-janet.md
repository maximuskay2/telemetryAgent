# Janet status (tester)

Current block: T-E3 (T-E1, T-E2 done)
Environment: local API 127.0.0.1:8401 + shop 8402 + web localhost:3401 (2026-10-31; evidence below on origin/main 02d066b, branch rebased to 23bc080 at commit); Railway https://web-production-926b3.up.railway.app

Done:
- T-E1 PASS (local + Railway, all 5 checks)
- T-E2 PASS (local + Railway, both checks)

Decisions:
- Stack runs with DATABASE_URL unset (worktree file store), GITHUB_TOKEN unset (no real PRs from test runs), FRIDGE_STREAM=1, SHOP_PORT=8402, CORS_ORIGIN_REGEX=http://(localhost|127\.0\.0\.1):3401. No .env written; ../telemetry-agent/.env sourced into process env only.
- Interactive local walks use http://localhost:3401: Next.js dev `allowedDevOrigins` blocks client JS over 127.0.0.1 (dev-server-only artifact; SSR identical on both hosts; production/Railway unaffected). Method per walk is noted below.

Failures (end to end): none in T-E1–T-E2.

NEEDS FROM AKINGBADE: —

BLOCKED: —

Live runs (what · result · seconds · model): none (0/3 used)

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
