# John status (commercial)
Current block: C-N9 done, rebased on 4a3373d, merge still BLOCKED (upstream smoke red)
BLOCKED (not mine): check.sh RED on smoke_demo — pre-existing,
identical on base. smoke_demo.sh sources .env (now has
DATABASE_URL) → hosted() true → C-J4 gating 401s
/api/systems/.../profile/sample ("sign-in required"; verified:
same steps pass with DATABASE_URL unset). Fix belongs to
James/Akingbade: unset DATABASE_URL in smoke_demo.sh (demo
route is self-hosted) or send a test token. My areas all PASS
(python/web/flutter). Rebased clean onto d51aad5, 9c487cf, then 4a3373d (APK,
welcome copy, Baseten/Meta model fixes; no conflicts, my hunks
intact) and re-gated: same single RED (smoke_demo dies at the
same sample step — upstream .env/DATABASE_URL 401, unaffected
by the new /shop-api whitelist), so still not merging. My
areas PASS (python/web/flutter). All drill servers stopped;
lsof 8201 empty; PG container removed; drill Clerk users
deleted; stale screenshot probe killed.
C-N9 DRILL RECORD (hosted, real Clerk, own PG, demo repo):
- Sign-up/org/invite/pair/claim/system/arm: all 200 in ~6 s API
  time. Two Clerk users, 3 orgs, per-user phone pairing.
- Crash 1 (genuine demo traceback) → run de2cae84187d PASS +
  PR maximuskay2/telemetryAgent-demo#12 (<17 min). No phone
  window: repo-PR runs don't ask (by design, no hosting yet).
- Crash 2 → run 7994f896a7f0 PASS (repeat). Crash 3 → run
  0ed601fa2c93 NO_ACTION (repeat dedupe on PR#12).
- Crash 4 + webhook hosting: rollback option executed from the
  phone flow → signed rollback POST received (run 13a856e6ca67).
- Crash 5 (post-C-J4b code): fix_runs 6, cost $0.0033 present.
- Usage reached state verified live (6/6 + banner, TA_FREE_*=6).
- Isolation as org B: UI 5/5 (members/devices/usage Rival-only,
  10 API bodies scanned, no org-A data) + API 4/4 (member invite
  403, cross-org device reads 403, legit reads 200). No C-J4
  failures from the edges.
Contract mismatches → James:
- C-N9-1: hosted POST /api/connections 500s (last_seen None
  fails response validation AFTER insert; shown-once key lost).
- C-N9-2: mitigate.decide() has zero callers — rollback windows
  open+audit but are invisible to /api/actions and unapprovable;
  options/execute bypasses windows. Wire decide or drop windows.
Fixed in my files: UsageView + blockedReasons now mirror the
cost dimension (backend blocks on it, §D promises it); tests 53/53.
Shelved: my RequireAuth Suspense fix — Akingbade fixed it himself
in 23bc080 (window.location); verified his build green 17/17.
8201 discipline (Akingbade note): my drill API held 8201 for 2h and
blocked James's merge gate (test_devices_e2e binds 8201) — it was
killed. Rule from now on: stop any server I start on 8201 before I
finish a session. Complying: drill API runs only while drilling.
PERMANENT FIX (Akingbade order): tests/test_devices_e2e.py no
longer binds fixed 8201 — runtime free-port probe + 5-attempt bind
retry. Proven: passes standalone AND with 8201 squatted.
Session-end rule adopted: `lsof -nP -iTCP:8201 -sTCP:LISTEN` must
show nothing of mine before I stop.
Drill moved to 8221 (free, nobody's) so the gate and the drill
never share a port again.
Done: C-N9a Clerk sessions headless (ticket+sign-in flow, tokens to
0600 files); C-N9b partial — org/invite/pair/claim/system/arm all
200 with real Clerk JWTs, genuine demo crash ingested, real fix run
de2cae84187d PASS with PR maximuskay2/telemetryAgent-demo#12.
Decisions (C-N9 so far):
- Clerk session JWTs live ~60s: drill re-mints per phase.
- Product routes need X-Org-Id for session callers (documented);
  my edges unaffected (commerce uses path org, app uses device).
- BUG for James (C-N9-1): hosted POST /api/connections 500s —
  Connection.last_seen None fails response validation AFTER the row
  inserts (ingest key lost, shown-once). Same crash likely breaks
  GET /api/connections. Workaround: in-process store create.
- Repo-PR runs open no phone window without hosting (by design);
  drill adds a webhook hosting connection for the approve step.
- Live dart probe polled /api/actions 16+ min clean (parse OK),
  then deleted per instruction (throwaway, never committed).
Done: C-N3..C-N7 merged; C-N8 audited James C-J3 (c89c60e, rebased
clean, zero shared files)
Decisions (C-N8):
- C-J3 changes nothing my edges consume: §8.4 routes untouched, app
  is HTTP-only (WS token join doesn't affect it), device Bearer
  still resolves org+role with owner passing role guards.
- Proved the deferred org-run approve chain at HTTP level (own PG,
  RLS-enforced ta_test role, seeded org run): device lists own
  action, cross-org invisible, cross-org disapprove 403, anonymous
  401, own-org disapprove 200 with decided_by, repeat 409. 6/6.
  No app or web changes needed.
Decisions (C-N7):
- @clerk/nextjs 7.9.23; session splits into Mock/Clerk/Token
  providers (stable hooks each). Clerk mode hydrates orgs from
  getToken(), refreshes the short-lived JWT every 50 s, signs out
  through Clerk; a pasted test token still overrides for local dev.
- Importing @clerk/nextjs in the server layout crashes prerender
  (a.startsWith), so ClerkProvider lives in a client ClerkShell.
  No clerkMiddleware: public simulation stays public; pages own
  their signed-out states.
- /signin renders Clerk <SignIn/> (brand blue, Optimistic stack)
  in clerk mode; the mock and connecting variants are unchanged.
- Proof: mock CDP 6/6 (rewritten mock provider), Clerk CDP 6/6
  (component mounts, email step, override, live members, no JS
  errors), JWKS live (1 RSA key). Interactive Clerk login (email
  code) is a human step — not headlessly provable.
Tag: James C-J1+C-J2 on main (cd2c809) adopted; rebased clean.
Decisions (C-N6):
- Real mode signs in with a pasted test JWT (local-dev <details> on
  /signin, stored as ta-token, display-only payload decode; backend
  verifies). No UI change needed for Clerk later: signInToken takes
  any session JWT.
- Fixed bare-`fetch` "Illegal invocation" (arrow wrapper) + regression
  test; web suite 40/40.
- Live proof vs real backend (own Postgres ta-pg-john:5439, file
  data dir, test issuer): 18/18 API loop (orgs/members/invite+accept/
  pair/claim/devices/revoke/usage + negatives) and 5/5 CDP (token
  sign-in, members, org-switch to devices, usage, no JS errors);
  *-live.png screenshots committed.
- Env note: installed James's pinned PyJWT/psycopg/cryptography into
  the shared gate venv (his tests can't run without them); commerce
  auth requires DATABASE_URL (file mode bypasses it); CORS default
  allows :3000 only, so local proofs set CORS_ORIGIN_REGEX.
Waiting on: Clerk dev keys for hosted sign-in (test-token hatch is
local-only); app approve vs org runs when James's C-J3 token join lands.
Done: C-N1+C-N2 sales look (merged 0c63127), C-N3 Phase 1 web (7fcb766),
C-N4 Phase 1 app (2506910), C-N5 Usage page + USAGE.md §D (c6fbedf)
Tag: commercial-contracts-in adopted — rebased clean on origin/main
(4820876, Jude usage/allowance). No /api/orgs routes on main yet
(James C-J1 still on com/james), so mocks stay; verified my Usage
type matches Jude's usage_summary keys exactly (incl. by_language).
Freed port 8201 (stopped my API) — James's C-J1 merge unblocked.
§8 confirmation (for C-J0): read and accepted — building web/app against the frozen §8.4 JSON with mocks per C-6. No contract issues so far.
Decisions:
- Tokens: light `:root` default (FB wash #F0F2F5, white cards, #050505,
  #0866FF primary + white labels), dark `[data-theme=dark]` (#18191A,
  #242526, same blue). First visit with no saved choice opens light
  (spec; OS preference intentionally ignored); choice in localStorage,
  applied pre-paint by an inline script.
- Dark link/text blue is #2D88FF while primary fills stay #0866FF both
  modes: #0866FF text on #18191A is unreadable (~2.9:1), so text-only
  accents use Meta's own dark-surface blue. Documented in tokens.css.
- Status WORDS untouched (ui/Badge.tsx); light ok/warn/crit darkened
  for contrast on white, dark keeps legible values.
- Danger buttons use a fixed #D61C1C + white both modes (mode-varying
  crit can't take one label color); Buy/Apply/Veto-confirm are blue
  primaries (Meta style), `text-on-brand` labels everywhere.
- Fonts: UI `Optimistic, Helvetica, Arial, sans-serif` (CSS only —
  no Optimistic files committed, verified by test); GeistSans
  dropped (web import + mobile asset removed); GeistMono kept for
  code/logs/IDs. Mono audited: 46→26 web sites, 3 mobile
  conversions; the rest are code/logs/IDs/keys/URLs.
- `.legacy` (classic, out of scope) pinned to its dark values so the
  light default can't alter it.
- Attribution "Built with Muse Spark" (plain text, no link) on
  welcome + Mission Control web, settings screen on phone. No Meta
  or Facebook logos, names, or ownership claims anywhere (test scans
  web + mobile sources and asset filenames).
- Phone: Riverpod ThemeMode + shared_preferences persistence,
  settings switch, mode-aware palette getters (50 `const` drops,
  mechanical, analyzer-clean).
- Done-when evidence: 23 node tests + 7 flutter theme tests green;
  headless-Chrome CDP proof (fresh=light, toggle→dark, dark
  survives reload, cleared→light, 9/9) + 3 screenshots in
  docs/screenshots/ (welcome-light, mission-light, mission-dark),
  visually reviewed. Full check.sh green at merge.
Decisions (C-N3):
- No @clerk/nextjs this round: unverifiable without keys, so the
  SessionProvider exposes an AuthClient seam (dev mock now, Clerk
  later). Dev mock behind NEXT_PUBLIC_COMMERCE_MOCK=1 only; real
  mode calls §8.4 HTTP with a session JWT and degrades to honest
  401/403/empty states. Fake dev tokens can never authenticate
  (backend verifies Clerk JWT).
- Sign-in without keys shows the form disabled with a "being
  connected" notice; with the mock flag it's a working dev sign-in.
- Presentational commerce components take props (mocked render
  tests); pages are thin session wiring. OrgSwitcher is a native
  select in the TopBar account cluster + members/devices headers.
Decisions (C-N4):
- Mobile keeps both auth shapes: `ta_dev_*` device tokens go in
  `Authorization: Bearer`, legacy shared tokens stay on
  `X-Mobile-Token`. Org id persists in secure storage alongside the
  connection. Pair screen claims a short code (`claimAndConnect`);
  any 401 marks unauthorized, shows "re-pair" copy, and Pair again
  disconnects back to the Pair screen. 11 flutter tests green
  (incl. lazy-list scroll fix: scrollUntilVisible before tapping
  Pair again).
Decisions (C-N5):
- `/usage` is thin session wiring over the tested getUsage +
  UsageView (counts vs free allowance, by-language runs, no cost
  shown anywhere). USAGE.md gains §D (accounts/orgs/members/
  devices/usage help); the two stale "no user accounts" lines now
  point at §D. Screenshot usage.png, CDP 5/5 incl. no JS errors.
Contract changes requested: —
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: nothing (Clerk dev keys received; old
publishable-key NEEDS satisfied by C-N7).
BLOCKED: —
