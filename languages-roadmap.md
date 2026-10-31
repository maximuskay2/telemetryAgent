# 🌐 TelemetryAgent: Languages Roadmap (auto-fix beyond Python)

**Goal:** the production repo-fix pipeline (crash → locate → reproduce → patch → prove → PR) works for repos written in **JavaScript/TypeScript, Java, Kotlin, Go, Rust and PHP**, with the same guarantees it gives Python today: the repro test **fails** on the original code, **passes** with the patch, and the repo's own suite shows **no new failures** — or the run ends as a **draft PR** with the diagnosis. Python keeps working exactly as it does now.

**Team (three Meta Muse agents side by side):**
- **James — Core.** The language-adapter framework, the pipeline refactor, sandboxes, ingest; then **Java/Kotlin** and **Go**.
- **John — JavaScript/TypeScript + edges.** The **JS/TS** adapter, the log forwarder, the `/connect` and app changes.
- **Jude — Rust, PHP, proof apps (runs on Baseten, `BASETEN_API_KEY`).** The **Rust** and **PHP** adapters, one buggy example app per language, and the end-to-end test harness.

All three run the product's model calls through **Baseten (Muse Spark Open)** first, Muse Wonder on the last attempt — exactly the existing chain in `core/repo_fix/generate.py`. Baseten is what makes the matrix fast enough to run often.

**Starting point:** `main` @ `f3d17f5` (Oct 30). 627 Python tests pass. Production route proven in Python (proof run: live crash → merged PR).

> This file owns **language support for repo-fix**. `production-roadmap.md` owns connections, ingest, mitigations and devices; `commercial-roadmap.md` owns accounts and billing. Nothing here changes the gate, the veto rules, the uptime promise, the API shapes, or the simulation route.

---

## 0. Where Python is baked in today (audit)

| # | Where | What's Python-only | Becomes |
|---|---|---|---|
| 1 | `core/ingest/traceback.py` | `parse_traceback` + `TracebackAssembler` only know `Traceback (most recent call last):` and `File "x", line N, in f` | One parser + start/continue rules **per language** |
| 2 | `agent/ta_forward.py` | `wanted()` keeps traceback lines only after the Python header | Multi-language trace detection (stays stdlib-only, one file) |
| 3 | `core/ingest/pipeline.py` `_sentry_lines` | Rewrites Sentry frames into Python-style text | Structured frames + Sentry `platform` → language |
| 4 | `core/repo_fix/run.py` | `should_trigger` needs a Python parse; `PYTEST`, `parse_pytest`, `_install_deps` (pip), `repro_test_path` (`tests/test_ta_repro_*.py`) | Adapter calls |
| 5 | `core/repo_fix/generate.py` | `REPRO_SYSTEM` says "ONE pytest file"; `"def test_" in code` check; file list from `python_files()` | Prompt rules + test check from the adapter |
| 6 | `core/repo_fix/snapshot.py` | `python_files`, `has_requirements`, `has_packaging`; drop list misses `target/`, `build/`, `vendor/`; binary filter would drop `gradle/wrapper/gradle-wrapper.jar` | Language-aware filtering |
| 7 | `core/repo_fix/locate.py` | Suffix matching works for path frames; Java/Kotlin frames have only `Foo.java` + class name; TS frames may point at `dist/*.js` | Adapter `map_frame` hook |
| 8 | `core/verify/repo_sandbox.py` | One image: `python:3.11-slim` + pytest (Docker `telemetry-agent-sandbox`; Modal `debian_slim` + pytest). `write_file` runs `python -c` inside the sandbox. No `read_file` (JUnit XML reports live in files) | One image **per language**; portable `write_file`; new `read_file` |

Everything else (fingerprints, gate, one-PR-per-fingerprint, draft PRs, PR body, mitigations, phone) is language-neutral already.

---

## 1. Design: one adapter per language

```
production log / Sentry ─► ingest assembler ── asks every adapter: trace_start / trace_continues
                                 │ completed trace text
                                 ▼
                     registry.parse(text) ─► (adapter, TracebackInfo{language, exc_type, exc_value, frames})
                                 ▼
repo tree ─► adapter.detect(paths) confirms the repo ─► locate (adapter.map_frame) ─► diagnose (Spark)
        ─► snapshot (adapter-aware filter) ─► sandbox(image = adapter.image)
        ─► adapter.install_cmds ─► adapter.suite_cmd ─► adapter.parse_results  (baseline)
        ─► repro test at adapter.repro_test_path, prompt + adapter.repro_rules ─► must FAIL
        ─► patch (≤ 3 files) ─► repro PASSES ─► suite: no new failures ─► PR  (else draft)
```

**Unknown or unsupported language:** behaves like a non-Python error today — the candidate is recorded and alerted, **no fix run starts**, and the gate decision says `"auto-fix not supported for <language> yet"`.

**Choosing the adapter:** the trace format picks it (each parser only accepts its own format); `detect(paths)` must also be > 0 for the repo, otherwise no run (e.g. a Java trace forwarded from a Python repo's logs). Polyglot repos: the trace decides; tests run with that language's runner.

### 1.1 Per-language specifics (the adapter authors' checklist)

| | JS/TS (John) | Java · Kotlin (James) | Go (James) | Rust (Jude) | PHP (Jude) |
|---|---|---|---|---|---|
| Detect | `package.json` (+ `tsconfig.json` → TS) | `pom.xml` / `build.gradle(.kts)`; `.kt` files → Kotlin | `go.mod` | `Cargo.toml` | `composer.json` |
| Trace starts | `TypeError: x` / `Error: x` followed by `    at ` lines; `Uncaught`; Node `node:internal` frames skipped | `Exception in thread "…" a.b.FooException: msg`, or a bare `a.b.FooException: msg` followed by `\tat ` | `panic: …` then `goroutine N [running]:` | `thread '…' panicked at src/x.rs:L:C:` (Rust ≥1.73) and the older `panicked at 'msg', src/x.rs:L:C` | `PHP Fatal error:  Uncaught X: msg in /path/F.php:12` + `Stack trace:` `#0 /path/G.php(30): …`; Laravel/Monolog `[stacktrace]` blocks |
| Frames | `at fn (/app/src/a.ts:10:5)`, `at /app/src/a.js:10:5` | `at com.acme.Foo.bar(Foo.java:42)`, `Caused by:` chains (root cause wins), `... N more` | function line, then `\t/app/pkg/x.go:12 +0x1d` | `at ./src/x.rs:5:13` in `RUST_BACKTRACE=1` output; else just the panic location | `#N /path/F.php(L): fn()`, plus the `in F.php:L` head |
| `map_frame` | suffix match; `dist/x.js` → `src/x.ts` when it exists | package + file → `src/main/{java,kotlin}/com/acme/Foo.java` (also multi-module `*/src/main/…`) | strip module path (`github.com/acme/app/` → repo root) | suffix match | suffix match; strip `/var/www/html/` etc. |
| Install (network on) | lockfile decides: `npm ci` · `pnpm i --frozen-lockfile` · `yarn install --frozen-lockfile` | Maven: `mvn -B -q -DskipTests dependency:go-offline test-compile`; Gradle: `./gradlew --no-daemon testClasses` (wrapper jar must survive the snapshot filter) | `go mod download` (keep a vendored `vendor/`) | `cargo fetch` then `cargo test --no-run` (compile once) | `composer install --no-interaction --no-progress` |
| Suite (network off) | from `package.json`: Jest `npx jest --ci --json --outputFile=…`, Vitest `npx vitest run --reporter=json --outputFile=…`, Mocha/`node --test` with a JUnit/JSON reporter | `mvn -B -o test` → `target/surefire-reports/*.xml`; `./gradlew --offline test` → `build/test-results/test/*.xml` | `go test ./... -json` | `cargo test --offline --no-fail-fast` (parse `test result:` + `failures:`) | `vendor/bin/phpunit --log-junit …` (or `vendor/bin/pest --log-junit …`) |
| Repro test path | the repo's convention: `__tests__/`, `test/`, `tests/` or colocated `*.test.ts`; name `ta_repro_<fp12>.test.<ext>` | `src/test/{java,kotlin}/<same package>/TaRepro<Fp12>Test.{java,kt}` (package-private access) | same dir as the frame's file: `ta_repro_<fp12>_test.go` (same package) | `tests/ta_repro_<fp12>.rs`; binary-only crate or private fn → `#[cfg(test)] mod ta_repro_<fp12>` appended to the located file (counts toward the 3 files) | `tests/TaRepro<Fp12>Test.php` (autoload via Composer) |
| Single test cmd | runner + that file | Maven `-Dtest=TaRepro<Fp12>Test`; Gradle `--tests '*TaRepro<Fp12>Test'` | `go test ./<dir> -run 'TestTaRepro' -json` | `cargo test --offline --test ta_repro_<fp12>` (or `ta_repro_<fp12>` filter for the inline module) | `vendor/bin/phpunit tests/TaRepro<Fp12>Test.php` |
| Looks like a test | `test(`/`it(` + `expect`/`assert` | `@Test` | `func TestTaRepro` | `#[test]` | `extends TestCase` + `public function test` |
| Image | `node:20` + corepack (pnpm, yarn) | `eclipse-temurin:21` + Maven (Gradle via wrapper) | `golang:1.23` | `rust:1` (slim) | `php:8.3-cli` + Composer + `mbstring xml intl zip pdo_sqlite` |
| Timeouts (install / suite) | 300 s / 600 s | 900 s / 900 s | 300 s / 600 s | 900 s / 900 s | 300 s / 600 s |

Every image also needs `sh`, `tar`, `base64` (for the portable `write_file`), and nothing else from us — **no Python inside non-Python images**.

---

## 2. How the three work together (read first)

### 2.1 Rules
- **L-1 Contracts first (H0, James, ~half a day).** `core/repo_fix/lang/base.py` (the `LanguageAdapter` protocol, `SuiteResult`), the registry with **auto-discovery** (every module in `core/repo_fix/lang/` that defines `ADAPTER` is registered — nobody edits a shared list), `TracebackInfo.language` (additive, default `"python"`), `RepoSandbox.read_file`, portable `write_file`, the shared result parsers (`results.py`: JUnit XML, Jest/Vitest JSON, `go test -json`). James tags `lang-contracts-in` when pushed. John and Jude build parsers + fixtures against the protocol before that (pure functions; no dependency).
- **L-2 Own files only** (§2.2). Need a change in someone else's file → write it under *Contract changes requested* in your status file and keep going.
- **L-3 Additive only.** No renames, no changed response shapes; new fields optional with defaults.
- **L-4 Python never regresses.** The Python adapter is a pure refactor of today's behaviour; `tests/test_prod_repofix.py` and the full suite must stay green at every merge.
- **L-5 Branches + checkpoints.** `lang/james`, `lang/john`, `lang/jude`, each in its own worktree; after each block: rebase on `origin/main`, `./scripts/check.sh` green, fast-forward `main` (procedure in §6.0).
- **L-6 Never wait.** Before `lang-contracts-in`, code against the protocol text in §3 and unit-test your pure functions (parsers, path mapping, result parsing) with fixtures.

### 2.2 File ownership

| Area | **James (Core)** | **John (JS/TS + edges)** | **Jude (Rust · PHP · proof apps)** |
|---|---|---|---|
| Framework | `core/repo_fix/lang/{__init__,base,results,python}.py` | — | — |
| Adapters | `core/repo_fix/lang/{java,go}.py` (Java + Kotlin in `java.py`) | `core/repo_fix/lang/javascript.py` (JS + TS) | `core/repo_fix/lang/{rust,php}.py` |
| Pipeline | `core/repo_fix/{run,generate,locate,snapshot}.py` | — | — |
| Ingest | `core/ingest/*` (assembler uses the registry; Sentry structured frames) | — | — |
| Sandbox | `core/verify/repo_sandbox.py`, `docker/sandbox/*` (all `Dockerfile.<lang>` written at H0 from §1.1), `scripts/build-sandbox-image.sh` | image changes → request in status | image changes → request in status |
| Connections | `core/connections/github.py` (repo test reports detected language), `core/schemas/production.py` (`ConnectionTest.language`, `ConnectionTest.autofix` — H0) | — | — |
| Forwarder | — | `agent/ta_forward.py` (stdlib-only, still one file) | — |
| Web / app | — | `apps/web/app/connect/*`, `apps/web/app/types/production.ts`, `apps/mobile/**` | — |
| Example apps | — | — | `examples/proof-app-{node,java,kotlin,go,rust,php}/**` |
| E2E harness | — | — | `scripts/lang_e2e.sh`, `tests/test_lang_e2e.py` |
| Tests + fixtures | `tests/test_lang_core.py`, `tests/test_lang_{python,java,go}.py`, `tests/fixtures/traces/{python,java,kotlin,go}/` | `tests/test_lang_javascript.py`, `tests/test_forwarder_langs.py`, `tests/fixtures/traces/{javascript,typescript}/` | `tests/test_lang_{rust,php}.py`, `tests/fixtures/traces/{rust,php}/` |
| Docs | `docs/production-backend.md` (adapter section) | `docs/USAGE.md` §C.2 "What your repo needs" → per-language table | `docs/languages.md` (new: per-language guide + recommended log settings) |
| Status | `status/lang-james.md` | `status/lang-john.md` | `status/lang-jude.md` |

**Frozen for all three:** the simulation route (`apps/api/main.py`, `core/agent/loop.py`, `core/setup/*`, `core/watch/*`, `core/simulate/*`, `demo/**`, the demo web pages), `core/actions/*`, `core/devices/*`, `apps/api/routes/*` (James may add the language fields to the repo test response only).

---

## 3. Contracts (H0 — James commits these first; then frozen)

```python
# core/repo_fix/lang/base.py
@dataclass
class SuiteResult:
    total: int
    passed: int
    failed: int
    failed_ids: List[str]          # stable ids (e.g. "tests/a.test.ts > adds", "com.acme.FooTest.bar")
    errored: bool = False          # runner/compile error before any test ran

class LanguageAdapter(Protocol):
    name: str                      # "python" | "javascript" | "typescript" | "java" | "kotlin" | "go" | "rust" | "php"
    image: str                     # key into repo_sandbox images: "python" | "node" | "jvm" | "go" | "rust" | "php"
    install_timeout_s: int
    suite_timeout_s: int

    def detect(self, paths: List[str]) -> int: ...                       # 0 = not this repo; higher = stronger
    def trace_start(self, line: str) -> bool: ...                        # first line of a trace in a log stream
    def trace_continues(self, line: str) -> bool: ...                    # still inside the trace
    def parse_trace(self, text: str) -> Optional[TracebackInfo]: ...     # None unless it's this language's format
    def map_frame(self, frame_file: str, func: str, paths: List[str]) -> Optional[str]: ...  # repo path or None
    def source_files(self, paths: List[str]) -> List[str]: ...           # shown to the model as the layout
    def install_cmds(self, paths: List[str]) -> List[List[str]]: ...     # run with network on, in order
    def suite_cmd(self, paths: List[str]) -> List[str]: ...              # network off
    def single_test_cmd(self, test_relpath: str, paths: List[str]) -> List[str]: ...
    def parse_results(self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]) -> SuiteResult: ...
    def repro_test_path(self, fingerprint: str, paths: List[str], located: List[str]) -> str: ...
    def repro_rules(self) -> str: ...                                    # appended to the repro system prompt
    def looks_like_test(self, code: str) -> bool: ...

# module-level in each adapter file:
ADAPTER: LanguageAdapter = ...

# core/repo_fix/lang/__init__.py
def all_adapters() -> List[LanguageAdapter]: ...                         # auto-discovered, python first
def parse(text: str) -> Optional[Tuple[LanguageAdapter, TracebackInfo]]: ...
def by_name(name: str) -> Optional[LanguageAdapter]: ...
def detect_repo(paths: List[str]) -> List[Tuple[str, int]]: ...          # for the /connect repo test
```

Other H0 changes (all additive):
- `TracebackInfo.language: str = "python"`; `Frame` unchanged (`file`, `line`, `func`).
- `RepoSandbox.read_file(relpath) -> Optional[str]` (Docker: read from the workdir; Modal: `cat` via exec).
- `write_file` uses `sh -c 'mkdir -p "$(dirname "$1")" && base64 -d > "$1"'` — no Python needed in the image.
- `open_repo_sandbox(snapshot, image="python")` picks `telemetry-agent-sandbox-<image>` (Docker) / the matching Modal image.
- `ConnectionTest.language: Optional[str] = None`, `ConnectionTest.autofix: Optional[bool] = None` — filled by the GitHub repo test from `detect_repo` (John shows them in `/connect`).
- Gate decision body may carry `language` (optional).

---

## 4. Build blocks

### 👷 James: Core

| Block | Work | Acceptance (automated unless noted) |
|---|---|---|
| **L-J0** H0 contracts | §3 files + registry auto-discovery + result parsers (JUnit XML, Jest/Vitest JSON, `go test -json`) + all `Dockerfile.<lang>` from §1.1 + `build-sandbox-image.sh <lang>` + tag `lang-contracts-in` | Registry finds a dummy adapter dropped in the package; JUnit/JSON parsers pass fixture reports; full suite green |
| **L-J1** Python adapter | Move today's behaviour into `lang/python.py`; `run.py` / `generate.py` / `snapshot.py` / `locate.py` call the adapter only (no `PYTEST`, `parse_pytest`, pip, `python_files` left in the pipeline) | `tests/test_prod_repofix.py` + the live Docker sandbox tests unchanged and green; proof-app Python run still PASS |
| **L-J2** Ingest | `TracebackAssembler` uses every adapter's `trace_start`/`trace_continues`; `should_trigger` uses `registry.parse` + `detect`; Sentry → structured frames with `platform` → language; unsupported language → decision `"auto-fix not supported for <lang> yet"` | Mixed-language log stream → one candidate per trace, right language each; Python ingest tests unchanged |
| **L-J3** Java + Kotlin | `lang/java.py`: JVM trace parser (`Caused by` root cause, `... N more`), package→path mapping incl. multi-module, Maven + Gradle detection, offline test runs, surefire/Gradle XML results | ≥ 8 real traces parsed; Jude's `proof-app-java` and `proof-app-kotlin` go repro FAIL → patch → PASS in Docker (mocked GitHub) |
| **L-J4** Go | `lang/go.py`: panic + goroutine parser, module-path stripping, `go test -json` | ≥ 6 real traces; `proof-app-go` end-to-end in Docker |
| **L-J5** Snapshot + docs | Drop `target/`, `build/`, `.gradle/`, PHP `vendor/`, `dist/` caches; keep Go `vendor/` and `gradle/wrapper/gradle-wrapper.jar`; adapter section in `docs/production-backend.md` | Snapshot tests for each rule |

### 👷 John: JS/TS + edges

| Block | Work | Acceptance |
|---|---|---|
| **L-N1** JS/TS adapter | `lang/javascript.py` (`name` reports `typescript` when `tsconfig.json`): V8 stack parser, `node:internal`/`node_modules` frames skipped for location, `dist→src` mapping, package-manager + runner detection, Jest/Vitest/Mocha/`node --test` commands + result parsing, repro path by convention | ≥ 10 real traces (Node, Express, Next.js API route, TS with and without source maps); `proof-app-node` end-to-end in Docker |
| **L-N2** Forwarder | `ta_forward.py` forwards whole traces for every §1.1 format (start + continuation rules copied in, stdlib-only, one file); `is_traceback_end` generalised | Fixture log per language → every trace line forwarded once, in order, nothing else above the level filter dropped; existing forwarder tests green |
| **L-N3** `/connect` | Repo step shows "Detected: TypeScript (npm, Vitest) · Auto-fix ✓" or "Detected: C# · alerts and rollback only" from `ConnectionTest.language/autofix` | Web type-check + a component test with both cases |
| **L-N4** App | Report screen shows the language + test runner of a run; "auto-fix not supported" incidents read clearly | `flutter test` green, new widget test |
| **L-N5** Docs | `docs/USAGE.md` §C.2 per-language "What your repo needs" table (from §1.1) + `README.md` language line | Doc review checklist in status |

### 👷 Jude: Rust · PHP · proof apps (Baseten)

| Block | Work | Acceptance |
|---|---|---|
| **L-D1** Proof apps (first — others need them) | `examples/proof-app-{node,java,kotlin,go,rust,php}`: tiny real service per language, **one real bug** each (empty-list average, off-by-one, null map lookup…), ≥ 10 passing tests, a `trigger` script that prints the **real** production trace, README; the same shape as `examples/proof-app` | Each app's suite passes in its sandbox image; each trigger prints a trace the matching parser accepts |
| **L-D2** Rust adapter | `lang/rust.py`: both panic formats + `RUST_BACKTRACE=1` frames, Cargo detection, `cargo fetch` + offline test, result parsing, integration-test-or-inline-module repro rule | ≥ 6 real traces; `proof-app-rust` end-to-end in Docker |
| **L-D3** PHP adapter | `lang/php.py`: CLI fatal + `Stack trace:` + Laravel/Monolog formats, Composer install, PHPUnit/Pest JUnit results | ≥ 6 real traces; `proof-app-php` end-to-end in Docker |
| **L-D4** E2E harness | `scripts/lang_e2e.sh [lang…] [--live]`: for each language, run the pipeline against its proof app in Docker with **mocked GitHub**; `--live` uses the real models (Baseten → Wonder) and prints PASS/draft per language with timings | `tests/test_lang_e2e.py` runs the mocked matrix (skips when Docker is missing); one `--live` run per language recorded in status |
| **L-D5** Docs | `docs/languages.md`: support matrix, what each language needs, recommended log settings (`RUST_BACKTRACE=1`, `node --enable-source-maps`, full JVM stack traces, PHP `display_errors=stderr`), known limits | Linked from USAGE and DOCUMENTATION |

### 🤝 Together

| Block | Work | Acceptance |
|---|---|---|
| **T-L1** Matrix | Jude runs `scripts/lang_e2e.sh --live` for all 7 languages (Python included) on `main` after everyone's last merge | All 7 PASS or a justified draft; timings + Baseten usage in §7 |
| **T-L2** Live proof (NEEDS Akingbade) | Push 1–2 proof apps (suggest `node` + `java`) as repos, deploy on Railway, run the real crash → PR like the Python proof run | PR links in §7 |

---

## 5. Schedule (nobody waits)

```
James  L-J0 contracts ──► L-J1 Python refactor ──► L-J2 ingest ──► L-J3 Java/Kotlin ──► L-J4 Go ──► L-J5
John   L-N1 JS/TS parser + fixtures (pure) ──► (after tag) adapter end-to-end ──► L-N2 forwarder ──► L-N3 ──► L-N4 ──► L-N5
Jude   L-D1 proof apps (all 6) ──► L-D2 Rust ──► L-D3 PHP ──► L-D4 harness ──► L-D5 ──► T-L1 matrix
```

Rough size with three agents: **3–4 working days**. The order of value: JS/TS and Java first (biggest market), then Go, PHP, Kotlin, Rust.

---

## 6. Agent instructions

They can't talk to each other or to a human while working. They coordinate **only through git** (`origin/main`, the `lang-contracts-in` tag, their status files) and this roadmap.

### 6.0 Shared operating rules (all three)

| | James | John | Jude |
|---|---|---|---|
| Worktree | `../telemetry-agent-james` | `../telemetry-agent-john` | `../telemetry-agent-jude` |
| Branch | `lang/james` | `lang/john` | `lang/jude` |
| API port | 8101 | 8201 (web 3201) | 8301 |
| Data dir | `TA_DATA_DIR=/tmp/ta-james` | `TA_DATA_DIR=/tmp/ta-john` | `TA_DATA_DIR=/tmp/ta-jude` |
| Status file | `status/lang-james.md` | `status/lang-john.md` | `status/lang-jude.md` |

- Fresh worktree: `git fetch origin && git worktree add ../telemetry-agent-<name> -b lang/<name> origin/main`. James and John already have worktrees: `git -C ../telemetry-agent-<name> fetch origin && git -C ../telemetry-agent-<name> switch -c lang/<name> origin/main` (their old changes are already on `main`).
- Python: `../telemetry-agent/venv/bin/python`. Docker Desktop must be running for sandbox tests; build images with `./scripts/build-sandbox-image.sh <lang>` (after L-J0).
- **Never** use ports 8001, 8002, 3000 (Akingbade's live demo) or another agent's ports; never stop processes you didn't start.
- Secrets: `set -a; . ../telemetry-agent/.env; set +a`. The product's generation uses `BASETEN_API_KEY` first. Never print, log, echo, commit or paste a secret; never write `.env`.
- **Model budget:** unit tests mock every model and GitHub call. Live model runs only through `scripts/lang_e2e.sh --live`, at most **3 live runs per language per agent per day**.

**Merge procedure (each checkpoint; your own branch only):**
```bash
git fetch origin
git rebase origin/main            # conflict in a file you don't own → git rebase --abort, note it under BLOCKED, keep working
./scripts/check.sh                # must exit 0
git push --force-with-lease origin HEAD:lang/<name>
git push origin HEAD:main         # fast-forward only; if rejected, start again from git fetch
```
- Never `--force` to `main`. Keep the configured git identity; **no `Co-authored-by` or AI trailers**; prefix messages with the block id (`L-J1: python adapter …`).
- Real GitHub writes only to `maximuskay2/telemetryAgent-demo`; close any PR you open while testing. No Railway deploys, no new repos, no publishing — list them under NEEDS.

**Status file (`status/lang-<name>.md`, yours only; commit at every checkpoint):**
```markdown
# <Name> status (languages)
Current block: …
Done: L-?1 (sha), …
Decisions: …
Contract changes requested: …
Live runs (lang · result · seconds · model): …
NEEDS FROM AKINGBADE: …
BLOCKED: …
```

**Working style:** autonomous to the end of your list; ambiguity → choose what fits this roadmap (safety first, then §2 rules), note it under *Decisions*, continue. Test-first for each acceptance row. **Done** = your acceptance rows pass, `check.sh` green on `main`, status complete, docs written.

### 6.1 Prompt for James (Core)

```text
You are James, an autonomous backend engineer (Meta Muse) in the TelemetryAgent repo at
/Users/maximusinfotechservices/Documents/META/telemetry-agent. Two other agents work AT THE SAME TIME
in their own worktrees: John (JS/TS adapter, forwarder, web, app) and Jude (Rust + PHP adapters,
proof apps, e2e harness). You cannot talk to them or to a human; coordinate only through git, the
tag lang-contracts-in, and status files.

Read languages-roadmap.md completely first (§0 audit, §1 design + §1.1 table, §2 rules + ownership,
§3 contracts, §6.0 operating rules), then docs/production-backend.md and core/repo_fix/*.

Your blocks, in order: L-J0, L-J1, L-J2, L-J3, L-J4, L-J5 (§4 "James").
- L-J0 FIRST and fast: everyone depends on §3. Commit it, push to main, tag lang-contracts-in, push the tag.
- L-J1 is a pure refactor: Python behaviour must not change; every existing test stays green.
- Edit only files in your column of §2.2. Mock GitHub and models in tests; Docker sandbox tests are real.
- Merge after each block with the §6.0 procedure. Update status/lang-james.md at every checkpoint.
Work autonomously until all your blocks meet their acceptance rows.
```

### 6.2 Prompt for John (JS/TS + edges)

```text
You are John, an autonomous engineer (Meta Muse) in the TelemetryAgent repo at
/Users/maximusinfotechservices/Documents/META/telemetry-agent. Two other agents work AT THE SAME TIME:
James (core framework, Java/Kotlin, Go) and Jude (Rust, PHP, proof apps, e2e harness). You cannot talk
to them or to a human; coordinate only through git, the tag lang-contracts-in, and status files.

Read languages-roadmap.md completely first (§1.1 JS/TS column, §2 rules + ownership, §3 contracts,
§6.0 operating rules).

Your blocks, in order: L-N1, L-N2, L-N3, L-N4, L-N5 (§4 "John").
- Before lang-contracts-in exists: write the V8/TS trace parser, path mapping and result parsing as
  pure functions with fixtures in tests/fixtures/traces/{javascript,typescript}/, coded to the §3
  protocol text. After the tag: rebase, wire them into core/repo_fix/lang/javascript.py (ADAPTER),
  and prove proof-app-node end-to-end in Docker (Jude creates the app in L-D1; until then use a
  local fixture repo under tests/fixtures/).
- agent/ta_forward.py stays stdlib-only and one file.
- Edit only files in your column of §2.2. Merge after each block (§6.0). Update status/lang-john.md.
Work autonomously until all your blocks meet their acceptance rows.
```

### 6.3 Prompt for Jude (Rust · PHP · proof apps — Baseten)

```text
You are Jude, an autonomous engineer (Meta Muse, running on Baseten) in the TelemetryAgent repo at
/Users/maximusinfotechservices/Documents/META/telemetry-agent. Two other agents work AT THE SAME TIME:
James (core framework, Java/Kotlin, Go) and John (JS/TS adapter, forwarder, web, app). You cannot talk
to them or to a human; coordinate only through git, the tag lang-contracts-in, and status files.

Create your worktree: git fetch origin && git worktree add ../telemetry-agent-jude -b lang/jude origin/main
Read languages-roadmap.md completely first (§1.1 Rust + PHP columns, §2 rules + ownership, §3
contracts, §4 "Jude", §6.0 operating rules), then examples/proof-app/ (the Python model to copy).

Your blocks, in order: L-D1, L-D2, L-D3, L-D4, L-D5, then T-L1 (§4).
- L-D1 FIRST: the six proof apps unblock James and John. Each: one real bug, >= 10 passing tests,
  a trigger script printing the REAL production trace, README. Commit and merge them early.
- Rust + PHP adapters: parsers and fixtures as pure functions first; wire ADAPTER after lang-contracts-in.
- scripts/lang_e2e.sh: mocked-GitHub matrix by default; --live uses real models (Baseten first,
  Wonder last attempt), max 3 live runs per language per day.
- Edit only files in your column of §2.2. Merge after each block (§6.0). Update status/lang-jude.md.
Work autonomously until all your blocks meet their acceptance rows.
```

**Starting Jude on Baseten** (from the main checkout; the hackathon key only works with `meta-models/muse-spark-open-1026`):
```bash
./scripts/muse-baseten.sh check                        # → Baseten OK (meta-models/muse-spark-open-1026)
git fetch origin && git worktree add ../telemetry-agent-jude -b lang/jude origin/main
./scripts/muse-baseten.sh --worktree existing --worktree-existing ../telemetry-agent-jude
# then paste the §6.3 prompt
```

### 6.4 Akingbade's checklist while they run
- Docker Desktop running; `BASETEN_API_KEY` and `MODEL_API_KEY` in `.env`; Modal optional.
- Watch `status/lang-*.md` for **NEEDS** and **BLOCKED**.
- T-L2: create `maximuskay2/telemetryAgent-proof-<lang>` repos from the proof apps and deploy them when asked.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| Rust/JVM builds are slow → timeouts | Compile during install (`cargo test --no-run`, `testClasses`); 900 s caps; draft PR on timeout, never a crash |
| Tests need network after install (Docker `--network none`) | Fetch everything in the install step; if the suite still needs network, draft PR with "tests need network" |
| Modal sandboxes always have network | Same commands; note it in the PR body's verification line |
| Minified / transpiled JS frames | Prefer source maps (`--enable-source-maps`); `dist→src` mapping; no match → keyword file picking (exists) |
| Private Rust functions not reachable from `tests/` | Inline `#[cfg(test)]` module rule (§1.1) |
| JVM repo with dozens of modules | Locate by package path across `*/src/main/*`; run only the module's tests when the full build exceeds the cap |
| Model writes a test for the wrong runner | `repro_rules()` names the runner + file path; `looks_like_test()` rejects; feedback loop already retries |
| Baseten rate limits with three agents | Mocked tests by default; live-run cap per §6.0; Wonder fallback on the final attempt |

---

## 8. Log (fill in while building)

| When | Who | What |
|---|---|---|
| | | |
