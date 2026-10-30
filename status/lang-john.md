# John status (languages)
Current block: L-N1..L-N5 code DONE (N1 pure + N2 merged; N3/N4/N5 coded to §3, merging) — tag watch for ADAPTER wiring
Done: L-N1 (pure, b00fb4f), L-N2 (5cc0785, merged to main)
Blocks (acceptance check Oct 30):
- L-N1 DONE (pure): 11 fixtures, 28 pure fns, tests green, merged. LEFT: ADAPTER wiring after lang-contracts-in; proof-app-node e2e (needs Jude L-D1).
- L-N2 DONE: union rules all §1.1 formats, stdlib-only one file, 12 tests green, merged.
- L-N3 DONE (coded to §3): DetectedLine + optional type fields; 4 node --test cases (supported/unsupported/absent/unknown-autofix); tsc clean. LEFT: live verify once James ships repo-test language/autofix.
- L-N4 DONE (coded to §3): gate.language model + header badge + runner meta + AUTO-FIX UNAVAILABLE card; 6 flutter tests; analyze clean. LEFT: live verify once gate carries language.
- L-N5 DONE: USAGE.md §C.2 table + README line (see doc checklist). LEFT: none.
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
Contract changes requested:
- How does one module (javascript.py, java.py) serve TWO adapter names?
  ADAPTER is singular but names are 8 ("javascript"+"typescript",
  "java"+"kotlin"). Options: ADAPTER may be a list, or discovery reads
  another symbol too. Blocking only the final wiring, not the pure code.
- suite_cmd/single_test_cmd get `paths` only: repos that configure their
  runner inside package.json (no config file) are undetectable. OK to
  default to Jest, or will run.py pass manifest content?
- L-N3 full string wants manager+runner detail, e.g. repo-test response
  carrying `stack_detail: "npm, Vitest"`. Optional; UI works without it.
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: —
BLOCKED: —
