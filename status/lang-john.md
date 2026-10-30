# John status (languages)
Current block: L-N1 DONE (pure, b00fb4f) + L-N2 DONE (forwarder) — pushing lang/john, tag watch
Done: L-N1 (pure, b00fb4f)
Blocks (acceptance check Oct 30):
- L-N1 DONE: 11 fixtures (node×6, express, next, tsc+sourcemap, tsc-sourcemap, browser), 28 pure fns, 40 tests green. LEFT: ADAPTER wiring after lang-contracts-in; proof-app-node e2e (needs Jude L-D1).
- L-N2 DONE: union start/continue rules for all §1.1 formats, stdlib-only one file, 12 tests green, Python path byte-identical. LEFT: merge to main (needs check.sh green).
- L-N3 LEFT: needs James L-J0 (ConnectionTest.language/autofix); web not started.
- L-N4 LEFT: mobile not started.
- L-N5 LEFT: USAGE.md table not started.
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
Contract changes requested:
- How does one module (javascript.py, java.py) serve TWO adapter names?
  ADAPTER is singular but names are 8 ("javascript"+"typescript",
  "java"+"kotlin"). Options: ADAPTER may be a list, or discovery reads
  another symbol too. Blocking only the final wiring, not the pure code.
- suite_cmd/single_test_cmd get `paths` only: repos that configure their
  runner inside package.json (no config file) are undetectable. OK to
  default to Jest, or will run.py pass manifest content?
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: —
BLOCKED: —
