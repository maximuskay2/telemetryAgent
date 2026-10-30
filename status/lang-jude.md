# Jude status (languages)

Current block: L-D4 (harness; L-D1/L-D2/L-D3 on main)

Blocks: L-D1 DONE (f78fe7f); L-D2 DONE (3f0e7fc); L-D3 DONE (this commit); L-D4 LEFT; L-D5 LEFT; T-L1 LEFT (needs James's python-parser fix + everyone's last merge)

Done: L-D1 (six proof apps, all suites green in sandbox images, all triggers print real traces), L-D2 (Rust adapter), L-D3 (below)

L-D1 verification (Oct 30, stock §1.1 base images): node 21/21 + V8 TypeError trace; java 20/20 (online then offline) + ArithmeticException; kotlin 20/20 + ArithmeticException at Cart.kt:48; go 21/21 + panic/goroutine trace; rust 21/21 + panicked-at/backtrace; php 20/20 + fatal/Stack trace. No suite covers the empty cart; every app answers 500 and keeps serving.

L-D2 Rust adapter (core/repo_fix/lang/rust.py, ADAPTER; tests/test_lang_rust.py, 34 tests; 11 fixtures in tests/fixtures/traces/rust/):
- Parses both panic formats incl. current-rustc ` (ThreadId)` (`thread 'w' (164) panicked at …`), 9 real traces (7 generated panics + proof-app trigger + an observed empty-backtrace run) + the documented pre-1.73 one-liner.
- Frames are throw-site-first (panic location leads, then backtrace locations).
- E2E in telemetry-agent-sandbox-rust against proof-app-rust: install cmds ok, baseline 21/21, repro at tests/ta_repro_….rs FAILS (exit 101, id parsed), guard fix → repro PASSES → suite 22 green, no new failures.

L-D3 PHP adapter (core/repo_fix/lang/php.py, ADAPTER; tests/test_lang_php.py, 31 tests; 9 fixtures in tests/fixtures/traces/php/):
- Parses CLI fatals (incl. `[date]` SAPI prefixes, `Next` chains, shutdown repeat), Parse errors, and real Laravel/Monolog `[stacktrace]` blocks (generated via LogManager + LineFormatter with Laravel's settings).
- PHPUnit primary via --log-junit (nested-XML normalized), stdout fallback; Pest supported (runner, JUnit, stdout shapes all real-captured).
- E2E in a local php-image variant (James's Dockerfile.php doesn't build yet — request 4): composer install ok, baseline 20/20, repro at tests/TaRepro…Test.php FAILS (error parsed), guard fix → repro PASSES → suite 21 green, no new failures.

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

Contract changes requested:
1. James (Maven install, L-J3): `dependency:go-offline test-compile` does NOT prefetch surefire providers — later `mvn -o test` fails on surefire-junit-platform:3.2.5. Suggest `mvn -B -q -DskipTests test` in the install step (verified: offline suite green after one full online run).
2. James (ingest, DONE in L-J2? re-check): `parse_traceback` claims any `X: …` text (python-first registry order), so Rust traces (`note: …` line) and JS traces route to python. Akingbade 30 Oct: James is fixing; re-check routing after his merge (T-L1 needs it).
3. James (results.py): `parse_junit_xml` sums nested suites — real PHPUnit XML counts 3× (66 vs 22) and triplicates failed ids. Suggest counting leaf `<testsuite>` only (flat Surefire/Gradle reports unaffected). My adapter normalizes locally until then.
4. James (Dockerfile.php): does not build — needs `libonig-dev libxml2-dev libsqlite3-dev` added to the apt line (mbstring/xml/pdo_sqlite extensions). Verified with a local variant image (tag jude-php-proof, uncommitted).
5. James (L-J2 assembler `_feed_generic`): a Rust trace completes at the message line (head+message already parses), so backtrace frames become plain lines — the run keeps throw site + message (sufficient; proven in e2e) but loses callers. Request: an additive optional hook (e.g. message-line count after a colon-head) or the forwarder's `_prev_rust_head` rule in the assembler.
6. James (generate.py): repro prompt shows the file list only — the model cannot see the Rust crate name (Cargo.toml [package]) or the PHP test namespace (neighbouring tests/composer.json). Request: append manifest text for adapters that need it.
7. John (ta_forward.py, his file): the Rust head regex misses current rustc thread ids (`thread 'w' (164) panicked at …`) — head + message lines drop at default level (only `stack backtrace:` recovers). Also, Monolog `"exception":"[object] (…)"` lines never start a trace, so `[stacktrace]` blocks are dropped (the continue rule exists but no trace is open).

Live runs (lang · result · seconds · model): none yet (unit + Docker proofs only; live runs start at L-D4 --live)

NEEDS FROM AKINGBADE: none

BLOCKED: none
