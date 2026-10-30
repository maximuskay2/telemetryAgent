# James status (languages)
Current block: L-J1 next (L-J0 done, merging)
Done: L-J0 (this commit)
Decisions:
- L-J0: `core/repo_fix/lang/` = protocol (`base.py`), registry
  (`__init__.py`), shared parsers (`results.py`). Sandbox `read_file`
  (Docker: workdir; Modal: direct `cat`, untruncated — §3 says "via exec"
  but the exec wrapper truncates at 20k, which would corrupt reports).
  Modal `write_file` is sh+base64 (equivalent to the §3 sketch, complete).
  `open_repo_sandbox(image=)` selects Docker images; python keeps the
  established `telemetry-agent-sandbox` name (§3's interpolation would
  rename it). GitHub repo test fills language/autofix from `detect_repo`
  on the tree (rollup fallback); autofix=True only when an adapter exists.
  Fixture seed is python-only; John/Jude add their own dirs.
- L-J0 includes `lang/python.py` as the reference adapter (wired in L-J1):
  `test_lang_core.py`'s python-autofix case and `/connect` language need
  `detect_repo`/`by_name` to know Python; the pipeline still uses the
  legacy helpers until L-J1, so behaviour is unchanged.
- John's Q1 (two names, one module): YES — the registry accepts
  `ADAPTERS = [...]` (list) as well as `ADAPTER` singular.
  `javascript.py` defines `ADAPTERS = [js, ts]`, `java.py` defines
  `ADAPTERS = [java, kotlin]`; single-language modules keep `ADAPTER`.
  First registration wins on duplicates; python sorts first. (`base.py`
  docs, `__init__.py`, `test_plural_adapters_are_discovered`.)
- John's Q2 (runner inside package.json): default to Jest, plus an
  optional manifest hook. Adapters MAY define `manifest_names()` and
  `configure_manifests(manifests)`; `run.py` (L-J1) fetches each named
  manifest from the repo tree (None when absent) and calls the hook once
  before any command method. Adapters that omit both get no manifests.
  JavaScript defaults to Jest when no runner is detectable.
- L-J1 (code written, next commit): pure refactor — Python behaviour moved
  to `lang/python.py`; `run.py`/`generate.py`/`locate.py` go through the
  adapter; `PYTEST` and `parse_pytest` stay as shims (frozen tests import
  them). `install_cmds` keeps the §3 `(paths)` shape: Docker exec sets
  `PIP_TARGET=/work/.deps` (proven live: pip+import six in the sandbox
  image). Repro prompt is `REPRO_BASE + adapter.repro_rules()` per §3.
  `_draft` still derives its repro path from the adapter with empty
  context — L-J2 threads the real located path (Go needs it). PR "sandbox
  pytest" heading + "Pytest output" feedback stay python-worded until a
  second adapter needs them. `run.py` also wires the manifest hook
  (fetch + `configure_manifests` when the adapter defines it).
- Sandbox clamp (30 Oct ~13:17 UTC, RESOLVED): all paths outside this
  worktree denied with EPERM, incl. shared `.git` and
  `../telemetry-agent/{venv,.env}`. Built `.venv-local` inside the worktree
  (network OK). Git restored 30 Oct; merging now. `.venv-local/` is
  git-ignored and never committed.
Contract changes requested: none (§3 implemented + John's two answers, both additive)
Live runs (lang · result · seconds · model): none yet
NEEDS FROM AKINGBADE: none
BLOCKED: none

## Per-block vs §4 acceptance (30 Oct, L-J0 commit)
- L-J0 DONE: registry discovers `ADAPTER` + `ADAPTERS`; JUnit/Jest/go
  parsers pass fixtures; Dockerfiles node/jvm/go/rust/php from §1.1
  (node corepack, php mbstring/xml/intl/zip/pdo_sqlite);
  `build-sandbox-image.sh <lang>`; `read_file` + portable `write_file` +
  `image=`; `TracebackInfo.language`; `ConnectionTest.language/autofix`;
  full suite green (`check.sh`).
- L-J1 LEFT: code written, uncommitted — `run.py`/`generate.py`/`locate.py`
  wiring + `tests/test_lang_python.py` + `tests/fixtures/traces/python/`.
  Next: commit, `check.sh`, push.
- L-J2 LEFT: not started — assembler uses every adapter's
  `trace_start`/`trace_continues`; `should_trigger` via `registry.parse` +
  `detect`; Sentry `platform` → language; unsupported → decision
  `"auto-fix not supported for <lang> yet"`.
- L-J3 LEFT: not started — `lang/java.py` (JVM parser, package→path,
  Maven+Gradle, surefire/Gradle XML). E2E needs Jude's proof-app-java/kotlin.
- L-J4 LEFT: not started — `lang/go.py` (panic parser, module-path strip,
  `go test -json`). E2E needs Jude's proof-app-go.
- L-J5 LEFT: not started — snapshot filter (`target/`, `build/`,
  `.gradle/`, PHP `vendor/` dropped; Go `vendor/` + wrapper jar kept) +
  `docs/production-backend.md` adapter section.
