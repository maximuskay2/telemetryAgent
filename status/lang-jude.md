# Jude status (languages)

Current block: T-L1 (6/7 live PASS; waiting on James L-J4 Go adapter for the last cell)

Blocks: L-D1 DONE (f78fe7f); L-D2 DONE (3f0e7fc); L-D3 DONE (901ab0b); L-D4 DONE (f84e974); L-D5 DONE (77ee810); T-L1 LEFT (go only)

Done: L-D1 (six proof apps), L-D2 (Rust adapter), L-D3 (PHP adapter), L-D4 (harness), L-D5 (docs/languages.md + 2 link lines)

L-D1 verification (Oct 30, stock §1.1 base images): node 21/21 + V8 TypeError trace; java 20/20 (online then offline) + ArithmeticException; kotlin 20/20 + ArithmeticException at Cart.kt:48; go 21/21 + panic/goroutine trace; rust 21/21 + panicked-at/backtrace; php 20/20 + fatal/Stack trace. No suite covers the empty cart; every app answers 500 and keeps serving.

L-D2 Rust adapter (core/repo_fix/lang/rust.py, ADAPTER; tests/test_lang_rust.py, 34 tests; 11 fixtures in tests/fixtures/traces/rust/):
- Parses both panic formats incl. current-rustc ` (ThreadId)` (`thread 'w' (164) panicked at …`), 9 real traces (7 generated panics + proof-app trigger + an observed empty-backtrace run) + the documented pre-1.73 one-liner.
- Frames are throw-site-first (panic location leads, then backtrace locations).
- E2E in telemetry-agent-sandbox-rust against proof-app-rust: install cmds ok, baseline 21/21, repro at tests/ta_repro_….rs FAILS (exit 101, id parsed), guard fix → repro PASSES → suite 22 green, no new failures.

L-D3 PHP adapter (core/repo_fix/lang/php.py, ADAPTER; tests/test_lang_php.py, 31 tests; 9 fixtures in tests/fixtures/traces/php/):
- Parses CLI fatals (incl. `[date]` SAPI prefixes, `Next` chains, shutdown repeat), Parse errors, and real Laravel/Monolog `[stacktrace]` blocks (generated via LogManager + LineFormatter with Laravel's settings).
- PHPUnit primary via --log-junit (nested-XML normalized), stdout fallback; Pest supported (runner, JUnit, stdout shapes all real-captured).
- E2E in a local php-image variant (James's Dockerfile.php doesn't build yet — request 4): composer install ok, baseline 20/20, repro at tests/TaRepro…Test.php FAILS (error parsed), guard fix → repro PASSES → suite 21 green, no new failures.

L-D4 harness (scripts/lang_e2e.sh + tests/test_lang_e2e.py; this commit also fixes PHP single_test_cmd — see Decisions):
- Mocked matrix (GitHub mocked, Docker real, canned repro+patch): python PASS 23s, rust PASS 6s, php PASS 10-16s; javascript/java/kotlin/go SKIP (no adapter yet). Full run 39s.
- --live (real Baseten→Wonder models, GitHub still mocked), one run each 30 Oct: python PASS 35s, rust PASS 34s, php PASS 52s (models wrote working repro+patch from the traces first try; per-run model labels weren't captured — the harness now prints model_used).
- Usage: ./scripts/lang_e2e.sh [langs…] [--live]; live budget enforced (3/lang/day in ~/.cache/ta-lang-e2e).

Decisions:
- Locks committed (Cargo.lock, composer.lock): proof apps are deployable services. Zero-dep apps have no lockfile. Added proof-app-go/.gitignore (was missing).
- Trigger method where no local toolchain exists: server in the sandbox image + HOST=0.0.0.0 + port map, curl from host, trace from docker logs.
- Status file is status/lang-jude.md per roadmap §6.0 (peers' status/<name>.md predate the languages roadmap).
- Rust + PHP frames are throw-site-first (head location leads); `/rustc/…` and `vendor/…` frames never map to repo paths.
- Rust message = first line after a new-format head (the forwarder takes one line too); legacy head carries its message inline.
- PHP first head wins: PHP prints the root cause first, then `Next <outer>` (verified with a real chained trace) — matches Java's root-cause-wins.
- PHP tolerates SAPI `[date]` prefixes (the dev server prefixes the fatal line; verified in the proofshop fixture).
- Pest detected from paths (`tests/Pest.php` ⇒ pest); both adapters are stateless (no manifest hook — avoids shared-ADAPTER races across concurrent runs).
- PHPUnit nests JUnit XML (config > suite > class); the adapter rewraps leaf suites before the shared parser (see request 3).
- Crate name / test namespace for repro prompts: repro_rules tells the model where to look (Cargo.toml [package] name; neighbouring tests' namespace); see request 6.
- L-D4 caught a real adapter bug: PHP single_test_cmd left the baseline's ta-results.xml in place, so a failing repro parsed as failed=0 → "could not write a test that fails" draft. single_test_cmd now overwrites the report (--log-junit ta-results.xml); stdout-only runners (cargo/pytest) are immune.
- The harness passes the image explicitly (sandbox_factory → open_repo_sandbox(tar, image=adapter.image)) because _pipeline doesn't thread it yet; see request 8.
- E2E traces: rust/php read the adapter fixtures; the other five are verbatim trigger captures inlined in tests/test_lang_e2e.py (their trace dirs belong to James/John, so no new fixture files there).
- L-D5 link lines (2): docs/USAGE.md §C.2 + docs/DOCUMENTATION.md doc list. Both files are outside my column, but the L-D5 acceptance row requires these links and their owners are done — minimal additive one-liners, logged here per John's Merge-1 precedent.

Contract changes requested:
1. James (Maven install): ADOPTED (his status: L-J3 uses `mvn -B -q -DskipTests test`).
2. James (python claims all traces): FIXED in 3a65e68, verified (rust→rust, php→php, incl. legacy + monolog shapes; ClaimGateTest pins it).
3. James (results.py): `parse_junit_xml` sums nested suites — real PHPUnit XML counts 3× (66 vs 22) and triplicates failed ids. Suggest counting leaf `<testsuite>` only (flat Surefire/Gradle reports unaffected). My adapter normalizes locally until then.
4. James (Dockerfile.php): does not build — needs `libonig-dev libxml2-dev libsqlite3-dev` added to the apt line (mbstring/xml/pdo_sqlite extensions). Verified with a local variant image (tag jude-php-proof, uncommitted).
5. James (L-J2 assembler `_feed_generic`): a Rust trace completes at the message line (head+message already parses), so backtrace frames become plain lines — the run keeps throw site + message (sufficient; proven in e2e) but loses callers. Request: an additive optional hook (e.g. message-line count after a colon-head) or the forwarder's `_prev_rust_head` rule in the assembler.
6. James (generate.py): repro prompt shows the file list only — the model cannot see the Rust crate name (Cargo.toml [package]) or the PHP test namespace (neighbouring tests/composer.json). Request: append manifest text for adapters that need it.
7. John (ta_forward.py, his file): the Rust head regex misses current rustc thread ids (`thread 'w' (164) panicked at …`) — head + message lines drop at default level (only `stack backtrace:` recovers). Also, Monolog `"exception":"[object] (…)"` lines never start a trace, so `[stacktrace]` blocks are dropped (the continue rule exists but no trace is open).
8. James (_pipeline): pass `adapter.image` to `open_repo_sandbox` (currently always the python image) and wire per-language Modal images (his L-J0 note says "when the adapters land" — rust/php have landed). The L-D4 harness works around it via sandbox_factory.

Live runs (lang · result · seconds · model): all via lang_e2e.sh --live, GitHub mocked, 30 Oct.
- Round 1 (L-D4): python PASS 35s live-chain; rust PASS 34s live-chain; php PASS 52s live-chain (model labels not captured; harness fixed since).
- Round 2 (T-L1 partial, 6/7): python PASS 37s baseten:muse-spark-open-1026; javascript PASS 29s baseten:muse-spark-open-1026; java PASS 157s baseten:muse-spark-open-1026; kotlin PASS 206s baseten:muse-spark-open-1026; rust PASS 24s baseten:muse-spark-open-1026; php PASS 38s baseten:muse-spark-open-1026; go SKIP (no adapter). Total 490s. Budget used: python/rust/php 2 of 3, js/java/kotlin 1 of 3.

NEEDS FROM AKINGBADE: none

BLOCKED: none
