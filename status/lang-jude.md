# Jude status (languages)

Current block: L-D2/L-D3 (Rust + PHP parsers as pure functions + fixtures; waiting on `lang-contracts-in` to wire ADAPTER)

Blocks: L-D1 DONE (this commit); L-D2 LEFT; L-D3 LEFT; L-D4 LEFT; L-D5 LEFT; T-L1 LEFT (needs everyone's last merge)

Done: L-D1 (six proof apps, all suites green in sandbox images, all triggers print real traces)

L-D1 verification (run Oct 30, stock §1.1 base images — James's Dockerfiles not on main yet):
- node: 21/21 `node --test` locally AND in `node:20`; `./trigger.sh` → HTTP 500 + real V8 `TypeError ... currency` stack
- java: 20/20 `mvn test` in `maven:3-eclipse-temurin-21` (online, then `--offline` re-run green); trigger → HTTP 500 + real `ArithmeticException: / by zero` at `Cart.summary(Cart.java:58)`
- kotlin: 20/20 `mvn test` in `maven:3-eclipse-temurin-21`; trigger → HTTP 500 + real `ArithmeticException` at `Cart.summary(Cart.kt:48)`
- go: 21/21 `go test ./...` in `golang:1.23`; trigger → HTTP 500 + real `panic: runtime error: integer divide by zero` + `goroutine [running]` stack into `shop/cart.go:70`
- rust: 21/21 `cargo test` in `rust:1-slim`; trigger → HTTP 500 + real `thread 'proof-shop-worker' panicked at src/cart.rs:70:19` + `RUST_BACKTRACE=1` backtrace
- php: 20/20 phpunit locally (PHP 8.5) AND in `php:8.3-cli`; `./trigger.sh` → HTTP 500 + real `PHP Fatal error: Uncaught DivisionByZeroError` + `Stack trace:` from `src/Cart.php:62`
- No suite covers the empty cart (only comments mention it); every app answers 500 and keeps serving after the crash.

Decisions:
- Locks committed (`Cargo.lock`, `composer.lock`): proof apps are deployable services (T-L2), so reproducible installs win. Zero-dep apps (node, go) have no lockfile.
- Added `proof-app-go/.gitignore` (was missing): ignores a stray `proofshop` binary, `*.test`, `coverage.out`.
- Trigger method where no local toolchain exists (go/rust/java/kotlin): server in the sandbox image + `HOST=0.0.0.0` + port map, health-check and POST from the host, trace from `docker logs` — same server code path `trigger.sh` drives.
- Status file is `status/lang-jude.md` per roadmap §6.0 (peers' `status/<name>.md` predate the languages roadmap).

Contract changes requested:
- For James (L-J3 install cmds): the roadmap's Maven install `dependency:go-offline test-compile` does NOT prefetch surefire providers, so a later `mvn -o test` fails resolving `surefire-junit-platform:3.2.5`. Verified on proof-app-java: after one full online `mvn test`, offline `mvn -o test` is green (20/20). Suggest the JVM install step run `mvn -B -q -DskipTests test` (full lifecycle, tests skipped) instead of bare `dependency:go-offline`.

Live runs (lang · result · seconds · model): (none — L-D1 needs no model calls)

NEEDS FROM AKINGBADE: (none)

BLOCKED: (none — `lang-contracts-in` tag not present yet; parsers proceed tag-free per L-6)
