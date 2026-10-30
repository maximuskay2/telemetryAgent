# TelemetryAgent language support

The production repo-fix pipeline — crash → locate → reproduce → patch →
prove → PR — works per language through one small *adapter* each. The
guarantee is the same everywhere: the repro test **fails** on the
original code, **passes** with the patch, and your suite shows **no new
failures** — or the run ends as a **draft PR** with the diagnosis.
Anything TelemetryAgent can't support yet gets alerts and rollback
only, never a half-proven fix.

Short version for onboarding: [USAGE.md §C.2](USAGE.md#c2-repo--let-us-open-prs).
This file is the full per-language guide: what each repo needs, how to
log, and the known limits.

## Support matrix

| Language | Detect | Test runner | Repro test | Status |
|---|---|---|---|---|
| Python | `requirements.txt` / `pyproject.toml` | `python -m pytest` | `tests/test_telemetry_agent_<fp>.py` | ✅ Live (proven in production) |
| JavaScript / TypeScript | `package.json` (`tsconfig.json` → TS) | Jest, Vitest, Mocha, `node --test` | `ta_repro_<fp>.test.<ext>` by repo convention | ✅ Live matrix PASS (29s) |
| Java | `pom.xml` / `build.gradle(.kts)` | Maven Surefire / Gradle | `src/test/java/<pkg>/TaRepro<Fp>Test.java` | ✅ Live matrix PASS (157s) |
| Kotlin | `build.gradle(.kts)` + `.kt` files | Maven / Gradle | `src/test/kotlin/<pkg>/TaRepro<Fp>Test.kt` | ✅ Live matrix PASS (206s) |
| Go | `go.mod` | `go test ./...` | `ta_repro_<fp>_test.go` next to the crash file | ✅ Live matrix PASS (74s) |
| Rust | `Cargo.toml` | `cargo test --offline` | `tests/ta_repro_<fp>.rs` (inline module if no lib target) | ✅ Live matrix PASS (24s) |
| PHP | `composer.json` | PHPUnit / Pest (`--log-junit`) | `tests/TaRepro<Fp>Test.php` | ✅ Live matrix PASS (38s) |

`<fp>` is the 12-char error fingerprint. Timings are the 30 Oct live
matrix (`scripts/lang_e2e.sh --live`, GitHub mocked, Baseten models);
`/connect` repo test always reports the live answer per repo.

## What each language needs

Applies to all: dependencies must install once **with** network
(`pip install`, `npm ci`, `mvn`, `go mod download`, `cargo fetch`,
`composer install`); afterwards the suite runs **offline** in the
sandbox. Frames must resolve to files in the repo (container paths
like `/app/src/x.js` match by suffix). Fixes fit in ≤ 3 files.

### Python

Nothing new: `requirements.txt` or equivalent, `pytest` suite,
uncaught tracebacks in the logs.

### JavaScript / TypeScript

- Run Node with source maps for TypeScript (`node --enable-source-maps`)
  and ship the maps; without them a `dist/*.js` frame may not resolve
  (we map `dist/` back to `src/` when the sources are in the repo).
- Don't strip `Error: …` heads or `at …` lines from logs. Minified
  client bundles can't be fixed — server code only.
- Lockfile decides the installer (`npm ci`, `pnpm i
  --frozen-lockfile`, `yarn install --frozen-lockfile`); the runner is
  detected from config (`jest`, `vitest`, mocha, `node --test`).

### Java / Kotlin

- Log **full** stack traces: `Exception in thread "…" …` plus every
  `at …` line and `Caused by:` chain. If you use Logback/Log4j, keep
  `%ex` full — `%ex{short}` cuts the frames we locate with.
- Maven or Gradle wrapper in the repo (the wrapper jar survives our
  snapshot filter). Multi-module builds locate by package path across
  `*/src/main/{java,kotlin}/…`.
- The repro test lands in the same package (`src/test/…`), so it can
  touch package-private code.

### Go

- Let panics print: `panic: …` + the `goroutine … [running]:` stack.
  If you `recover()`, log `debug.Stack()` — byte-identical to an
  unrecovered crash.
- Keep `go.mod` tidy; a vendored `vendor/` is kept (not stripped).
- The repro test goes in the same directory and package as the crash.

### Rust

- Run with **`RUST_BACKTRACE=1`**. Without it we still get the panic
  location (`thread '…' panicked at src/x.rs:L:C`), which is usually
  the bug — with it we get the full backtrace callers too.
- Both panic formats are supported, including pre-1.73
  (`panicked at 'msg', src/x.rs:L:C`) and current thread ids.
- `cargo fetch` runs at install; `cargo test --offline` proves.
  Crates without a lib target (or a crash inside `src/bin/`) get the
  repro as an inline `#[cfg(test)] mod ta_repro_<fp>` (counts toward
  the 3 files).

### PHP

- Log the engine's own errors: `display_errors=stderr`,
  `log_errors=On`. We parse `PHP Fatal error: Uncaught … in F.php:L`
  + `Stack trace:` + `#N …` frames, `Next …` chains (root cause
  first), and Laravel/Monolog `[stacktrace]` blocks.
- Monolog users: keep stack traces in the exception context
  (Laravel's default `LineFormatter` already does). The raw trace
  lines must reach the log — a formatter that drops newlines breaks
  frame parsing.
- PHPUnit (default) or Pest (detected via `tests/Pest.php`);
  results come from `--log-junit`, stdout is the fallback.

## Recommended log settings (copy-paste)

```bash
# Rust: full backtraces
RUST_BACKTRACE=1 ./your-service

# Node + TypeScript: resolve dist frames to src
node --enable-source-maps dist/server.js

# JVM (Logback): full stack, keep Caused-by chains
# <pattern>%d %-5level %logger - %msg%n%ex{full}</pattern>

# PHP (CLI / built-in server / FPM pool):
#   display_errors=stderr   (dev server)
#   log_errors=On  error_log=/var/log/php/errors.log   (FPM/CLI)

# Go: nothing to set — but if you recover(), log the stack:
#   if r := recover(); r != nil { log.Printf("panic: %v\n%s", r, debug.Stack()) }
```

## Proof apps

One tiny real service per language, each with the same drilled bug
(empty-cart checkout crashes) and a green suite that never tested it:

| App | Bug | Suite | Trigger |
|---|---|---|---|
| `examples/proof-app` (Python) | `ZeroDivisionError` | 20 | `trigger_bug.py` |
| `examples/proof-app-node` | V8 `TypeError` | 21 | `./trigger.sh` |
| `examples/proof-app-java` | `ArithmeticException` | 20 | `./trigger.sh` |
| `examples/proof-app-kotlin` | `ArithmeticException` | 20 | `./trigger.sh` |
| `examples/proof-app-go` | integer divide panic | 21 | `./trigger.sh` |
| `examples/proof-app-rust` | divide-by-zero panic | 21 | `./trigger.sh` |
| `examples/proof-app-php` | `DivisionByZeroError` | 20 | `./trigger.sh` |

Each `trigger.sh` starts its own server, POSTs `{"items": []}`,
prints the HTTP code and the **real** production trace. Servers bind
`127.0.0.1` by default, `HOST=0.0.0.0` for containers.

## End-to-end harness

`scripts/lang_e2e.sh [langs…] [--live]` runs the pipeline per proof
app in Docker with GitHub mocked. Default mode mocks the models too
(deterministic plumbing proof); `--live` uses the real models
(Baseten first, Wonder last attempt) with a 3-runs-per-language-per-day
budget, and prints `PASS`/`DRAFT` per language with timings:

```bash
./scripts/lang_e2e.sh                 # mocked matrix, all 7
./scripts/lang_e2e.sh rust php        # subset
./scripts/lang_e2e.sh rust --live     # real models, one language
```

The same matrix lives in `tests/test_lang_e2e.py` (skips cleanly
without Docker, without an adapter, or without canned outputs).

## Known limits

- **PHP-FPM** `PHP   N. …` frame lines: the throw site (`PHP Fatal
  error: … in F.php:L`) parses and locates; the numbered frames don't
  yet. CLI, built-in server, and Monolog shapes are fully parsed.
- **Rust backtrace frames** currently stop at the panic message in
  server-side ingest (the assembler completes a trace once head +
  message parse). Throw site + message always survive — proven
  sufficient for the fix loop — full caller frames arrive with the
  pending assembler message-line rule.
- **Minified/transpiled JS** without source maps may not locate;
  keyword fallback picks files instead.
- **Rust** binary-only crates and crashes in `src/bin/` use the
  inline-module repro (counts toward the 3 files). A non-default
  `[lib] path` in `Cargo.toml` isn't detected (assumes `src/lib.rs`).
- **Pest** repos are detected via `tests/Pest.php`; without that
  file the suite runs as PHPUnit.
- Suites that need **network after install** can't prove offline and
  end as drafts ("tests need network").
- Non-UTF8 paths and exotic layouts match best-effort by suffix;
  unmappable frames fall back to keyword file picking.
