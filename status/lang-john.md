# John status (languages)
Current block: ALL BLOCKS DONE (L-N1..L-N5 merged; N4 live-verified; js matrix leg handed to Jude)
Done: L-N1 (pure b00fb4f; wiring + node e2e, this branch), L-N2 (5cc0785, merged), L-N3 (13f3f70, merged), L-N4 (941288d, merged), L-N5 (e807af6, merged)
Blocks (acceptance check Oct 30):
- L-N1 DONE (merged): single ADAPTER, manifest hook, results.py delegation, 62 tests green; Docker e2e PASS on Jude's proof-app-node (real trigger.sh TypeError → located src/cart.js → baseline 21/21 → repro FAIL → guard patch → repro PASS → suite 22/22 clean, 3.1s, no models); real should_trigger names adapter=javascript. Matrix javascript leg: PROVEN locally (full run_repo_fix PASS, mock PR, 4s) then REVERTED from main per Akingbade (Jude owns the file and is editing it) — canned code handed to Jude below; he merges it into his version. No --live run (T-L1 is Jude's, after everyone's last merge).
- L-N2 DONE: union rules all §1.1 formats, stdlib-only one file, 12 tests green, merged.
- L-N3 DONE: merged + LIVE-VERIFIED — real `check_repo` on telemetryAgent-demo returns `language`/`autofix` keys matching the TS type; error path omits them (renders nothing). Both UI branches proven.
- L-N4 DONE: merged + LIVE-VERIFIED — real L-J2 gate body for the proof-app-node trace (decision observe, language javascript, autofix True) embedded in the widget test; badge + verdict + reason render, no unavailable card. 6 flutter tests green.
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
Decisions (matrix leg):
- 3c3eb93 enabled the javascript matrix leg, then Akingbade ruled
  Jude's file is his while he's editing it: reverted the
  `test_lang_e2e.py` hunk from main (forward revert, no history
  rewrite) and moved the code to a handoff below. My leg was green
  when reverted; Jude merges it into his version.
Contract changes requested:
- Q1/Q2 ANSWERED by L-J0 and adopted (above). Still open:
- (a) RESOLVED by James 3a65e68 (test now gates on adapter presence).
- (b) RESOLVED by James 3a65e68 (python claims only python traces;
  V8 routes to javascript; skip guard removed).
- L-N3 full string wants manager+runner detail, e.g. repo-test
  response carrying `stack_detail: "npm, Vitest"`. Optional.
- HANDOFF FOR JUDE (javascript matrix leg — merge into your
  `tests/test_lang_e2e.py`; proven green here before my revert):
  add after `_php_repro_for`, and flip LANGS["javascript"] None →
  `_javascript_canned`:
  ```python
  JAVASCRIPT_REPRO = """import { describe, it } from "node:test";
  import assert from "node:assert/strict";
  import { summary } from "../src/cart.js";

  describe("ta repro: empty-cart summary", () => {
    it("does not throw on an empty cart", () => {
      assert.doesNotThrow(() => summary([]));
    });
  });
  """
  JAVASCRIPT_BUG = "export function summary(items) {\n"
  JAVASCRIPT_FIX = """export function summary(items) {
    if (items.length === 0) {
      return {
        lines: 0,
        subtotal: 0,
        discount: 0,
        total: 0,
        average_item_price: 0.0,
        currency: "USD",
      };
    }
  """
  def _javascript_canned(appdir):
      cart = appdir / "src" / "cart.js"
      content = cart.read_text()
      assert JAVASCRIPT_BUG in content, "javascript BUG anchor moved"
      return JAVASCRIPT_REPRO, [
          {"path": "src/cart.js", "content": content.replace(
              JAVASCRIPT_BUG, JAVASCRIPT_FIX, 1)}
      ]
  ```
Live runs (lang · result · seconds · model): —
NEEDS FROM AKINGBADE: —
BLOCKED: —
