# John status (languages)
Current block: L-N1 wired + proven in Docker — branch pushed, merge BLOCKED on James test flip (see BLOCKED)
Done: L-N1 (pure b00fb4f; wiring + node e2e, this branch), L-N2 (5cc0785, merged), L-N3 (13f3f70, merged), L-N4 (941288d, merged), L-N5 (e807af6, merged)
Blocks (acceptance check Oct 30):
- L-N1 DONE (wired): single ADAPTER (see Decisions), manifest hook, results.py delegation, 61 tests green + 1 documented skip; Docker e2e PASS on Jude's proof-app-node (real trigger.sh TypeError → located src/cart.js → baseline 21/21 → repro FAIL → guard patch → repro PASS → suite 22/22 clean, 3.1s, no models). LEFT: merge (BLOCKED below).
- L-N2 DONE: union rules all §1.1 formats, stdlib-only one file, 12 tests green, merged.
- L-N3 DONE: merged + LIVE-VERIFIED — real `check_repo` on telemetryAgent-demo returns `language`/`autofix` keys matching the TS type; error path omits them (renders nothing). Both UI branches proven.
- L-N4 DONE: merged. LEFT: live verify once a gated run carries language.
- L-N5 DONE: merged.
Doc review checklist (L-N5): every table row checked against roadmap §1.1 (markers, trace formats, install cmds, suite cmds) + §4 L-D5 log settings (source maps, RUST_BACKTRACE=1, full JVM traces, display_errors=stderr); Python row keeps prior meaning; armed + ≤3-files + suffix-match notes kept; unsupported-language line matches §1 unknown-language rule; README line honest (Python today, rest rolling out) with USAGE link.
Decisions:
- javascript.py holds pure functions only until lang-contracts-in lands
  (no ADAPTER yet — the ADAPTER discovery shape is James's L-J0 call, and
  8 names over 6 modules needs his answer; see Contract changes requested).
- parse_trace keeps node:internal/node_modules frames in `frames` (faithful
  parse); map_frame returns None for them ("skipped for location").
- parse_trace sniffs language from frame extensions (.ts/.tsx/.mts/.cts →
  "typescript", else "javascript"); adapter `name` follows the same rule
  once wired (tsconfig.json confirms TS at detect time).
- Runner detection uses config-file names in `paths` only (no file contents
  at the adapter boundary); Jest is the fallback. Single-file Mocha and
  node --test suites parse from stdout (spec summary / TAP), Jest/Vitest
  from their JSON output files.
Decisions (L-N1/L-N2 run-off):
- Suite/install commands detect the runner at RUNTIME from installed
  node_modules/.bin binaries (repos configure runners inside package.json,
  which the paths-only adapter boundary cannot see); node:test is the
  no-runner fallthrough. parse_results probes JSON files, then TAP, then
  Mocha spec; anything unreadable is errored (draft, never a false proof).
- parse_trace: FIRST error line wins (V8 prints outer before [cause]);
  location-less frames skipped; frameless parses return info (trigger
  still requires frames, mirroring Python).
- Forwarder uses UNION start/continue rules (it only decides *whether*
  to forward; the server re-parses). Python path byte-identical;
  is_traceback_end also ends on any new head. Pre-head code frames and
  the `Node.js vX` trailer drop (accepted, documented in tests).
- Monorepos (nested package.json): v1 emits root commands (will draft);
  custom `npm test` wrappers (CRA etc.) unsupported in v1. Both noted
  as known limits, not silent failures (errored → draft PR).
- Fixtures: 10 real captured traces (node×6, express, next, tsc±maps)
  + 1 real-format browser trace; result parsers verified against real
  jest/vitest/mocha/node-tap outputs (kept in /tmp, excerpts inline).
Decisions (L-N3/L-N4):
- Both coded to the §3 contract text before James's H0 lands; every new
  field is optional and renders nothing until the backend sends it
  (pre-H0 UI is byte-identical in behaviour).
- L-N3 shows "Detected: <Lang> · Auto-fix ✓" / "· alerts and rollback
  only"; the "(npm, Vitest)" detail in the acceptance example needs a
  contract addition (see requested) — not shown yet.
- L-N3 component test runs dependency-free: `node --test app/connect/`
  from apps/web (repo's own typescript + react-dom/server). Not in
  check.sh (not my file); web type-check rides the existing next build.
- L-N4 reads language from gate first (the §3 carrier), result fallback;
  runner was already in verifyLine, now also in the header meta.
Decisions (L-N1 wiring):
- Single `ADAPTER` named "javascript", NOT `ADAPTERS = [js, ts]`:
  `test_aliases_resolve` (committed) requires
  `by_name("typescript") is by_name("javascript")`, which a second
  adapter object would break. TS still flows: sniffed `info.language`
  + `refined_name` + the alias. (James's status prose says
  `ADAPTERS = [js, ts]` — the test wins; flagging, not editing.)
- Q2 adopted: `manifest_names`/`configure_manifests` implemented;
  `detect_runner` = manifest → config → "jest". The manifest hint
  orders the binary probe (matters when two runners are installed)
  and names the runner in `repro_rules`. Command fallthrough stays
  `node --test` (a runner-less repo can only run that offline; a
  Jest command there would just error → draft).
- Jest/Vitest counts+ids delegate to `results.parse_jest_json`; my
  suite-failed-to-run and empty→errored rules layer on top.
- TAP fix from real node 20 output: passing subtests carry NO
  `type:` line (only suites are tagged), so "no `type:`" now means
  test. Regression tests hold two captured node-20 transcripts.
- E2E used a local `tests/fixtures/node-proof/` repo (§6.2 allows)
  since `proof-app-node` is not merged yet; no models, no GitHub.
Contract changes requested:
- Q1/Q2 ANSWERED by L-J0 and adopted (above). Still open:
- (a) Flip `test_typescript_detected_not_autofixable_yet` to
  assertTrue (or gate on adapter presence): my landing makes TS
  autofixable, so it fails now. BLOCKS my merge (James's file).
- (b) Python parser claims every language: `parse_traceback`
  returns info for V8 text (exc line, zero frames), and python is
  first in `registry.parse` — so no V8/Java/Go/Rust/PHP trace
  will ever route until it requires the header or ≥1 frame
  (James's `python.py`/`traceback.py`). LIVE evidence 30 Oct:
  `registry.parse` routes Jude's proof-app-node trigger trace to
  `python`, so L-J2 `should_trigger` would fail the run early at
  the `detect` check (python scores 0 on node paths) — the JS
  pipeline cannot trigger at all until this is fixed. My routing
  test skips until then.
- L-N3 full string wants manager+runner detail, e.g. repo-test
  response carrying `stack_detail: "npm, Vitest"`. Optional.
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: —
BLOCKED: merge of L-N1 wiring to main waits on James (a): check.sh is
red on exactly that one test; everything else green.
