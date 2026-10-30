# James status (languages)
Current block: L-J5 next (L-J4 done, merging)
Done: L-J0 (8276c12, on main, tagged lang-contracts-in), L-J1 (c2c2d8a),
  L-J2 (31ad582), checkpoint (3a65e68), L-J3 (3aed4f1), L-J4 (this commit)
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
- L-J1: pure refactor — Python behaviour moved to `lang/python.py`;
  `run.py`/`generate.py`/`locate.py` go through the adapter; `PYTEST` and
  `parse_pytest` stay as shims (frozen tests import them). `install_cmds`
  keeps the §3 `(paths)` shape: Docker exec sets `PIP_TARGET=/work/.deps`.
  Repro prompt is `REPRO_BASE + adapter.repro_rules()` per §3. `run.py`
  wires the manifest hook (`_configure_adapter`; no-op for Python).
- L-J2: assembler start = UNION of `trace_start`; starter remembered.
  Python completes byte-identically (greedy to the exc line); others
  collect while `trace_continues`, then complete with/without the closing
  line by which parses, re-feeding the line (orphans become their own
  entry — a closing ERROR line must not vanish). `assemble` parses via
  the registry. `process_lines`: parsed-with-frames (or Sentry-hinted)
  entries without a rule hit become `rule="traceback"` candidates
  (`rules.py` is frozen and only knows the Python header + ERROR);
  gate bodies carry `language` + `autofix`, and
  `"auto-fix not supported for <lang> yet"` when unsupported.
- L-J2 `detect` placement: `should_trigger` stays sync (frozen tests call
  it directly) and does `registry.parse` + repo resolve; the `detect>0`
  repo check runs in `_pipeline` right after the tree fetch (no extra
  network) and FAILs the run early with a mismatch reason — no sandbox,
  no PR. Adapter threaded `run_repo_fix(adapter_name)` → `_run` →
  `_pipeline` → `_verify_and_fix`/`_install_deps`/`_draft`; `_draft`
  takes the real `test_relpath` (Go needs it) with legacy fallback.
- L-J2 Sentry: `platform` → language (missing → python legacy,
  byte-identical; unknown passes through verbatim); non-Python renders
  its §1.1 shape behind a `ta-language:` marker line that `assemble`
  strips for sentry keys (no route change — routes are frozen). Verified
  the JS rendering parses with John's pure `parse_trace` (2 frames).
  Known limits: Sentry-vs-log fingerprints for one bug may differ
  (rendered vs real columns/trailers); pre-adapter Sentry frame lines
  are skipped, the head line carries the candidate.
- Checkpoint (30 Oct, Akingbade): (1) python claims a trace only with
  the `Traceback` header or ≥1 Python frame — V8/Go/JVM/Rust/PHP heads
  no longer route to python (John's (b)); `ClaimGateTest` locks all five
  + header-only Python. (2) `test_typescript_autofix_follows_adapter`
  gates on adapter presence (John's (a) option) — green before and after
  his wiring lands. (3) `.gitignore` gains bare `venv` (`venv/` never
  matched the `venv` → `.venv-local` symlink check.sh uses).
- L-J3: single JVM `ADAPTER` (name "java"); `.kt` frames / `kotlin.*`
  exceptions preset `kotlin` (aliases + `refined_name` cover the rest —
  the `ADAPTERS` shape stays available but one object suffices).
  `trace_start` needs a qualified head (bare words swallowed log lines);
  parse takes the root cause, skips `... N more`, rejects tail junk.
  Maven install is a full failure-tolerant online `test` (Jude's
  `-DskipTests` variant did NOT prefetch surefire providers under this
  image's Maven — verified live). Docker exec pins
  `MAVEN_OPTS=-Dmaven.repo.local=/work/.m2` + `GRADLE_USER_HOME`
  (throwaway runs share only /work; go/rust add theirs later). Assembler:
  a foreign-language head flushes the open buffer (no swallowed traces).
  Modal images per language + portable (sh) snapshot upload for
  non-python guests (UNVERIFIED live — no Modal creds here); python
  Modal path byte-identical.
- L-J3 E2E (mocked GitHub + mocked models, real Docker `jvm` image):
  proof-app-java PASS (~3 min, cold Maven), proof-app-kotlin PASS
  (~4 min). No committed Docker E2E: Jude's L-D4 harness owns the
  matrix (a 10-min gate tax for all three agents is his call); the
  re-runnable scratch runs live at /tmp/e2e_java.py + /tmp/e2e_kotlin.py.
  Gradle path implemented per §1.1 + unit-tested, E2E-unproven (no
  Gradle proof app exists).
- L-J4: recovered panics (`log.Printf` + `debug.Stack`) carry a timestamp
  and keep the `goroutine` line — both tolerated; `fatal error:` (no
  panic line) stays unsupported, noted limit. proof-app-go E2E PASS
  (~2 min, zero-dep). `test_rollup_fallback_when_tree_empty` now gates
  `autofix` on adapter presence (same as the TS flip).
- Tag race (30 Oct): `lang-contracts-in` was pushed pointing at the
  pre-rebase L-J0 (9da95a5) when John's L-N3..N5 landed mid-merge and the
  first main push rejected. Deleted the remote tag, rebased L-J0 onto
  John's main, re-verified green, pushed main (8276c12), re-tagged.
  No force-push to main; the old commit survives on `lang/james` history.
- Sandbox clamp (30 Oct ~13:17 UTC, RESOLVED): all paths outside this
  worktree denied with EPERM, incl. shared `.git` and
  `../telemetry-agent/{venv,.env}`. Built `.venv-local` inside the worktree
  (network OK). Git restored 30 Oct; merging now. `.venv-local/` is
  git-ignored and never committed.
Contract changes requested: none (§3 implemented + John's two answers, both additive)
Live runs (lang · result · seconds · model): none yet
NEEDS FROM AKINGBADE: none
BLOCKED: none

## Per-block vs §4 acceptance (30 Oct, L-J2 commit)
- L-J0 DONE (8276c12, main, tagged): registry discovers `ADAPTER` +
  `ADAPTERS`; JUnit/Jest/go parsers pass fixtures; Dockerfiles
  node/jvm/go/rust/php from §1.1; `build-sandbox-image.sh <lang>`;
  `read_file` + portable `write_file` + `image=`; 705 green at merge.
- L-J1 DONE (c2c2d8a, main): `run.py`/`generate.py`/`locate.py` call the
  adapter only (`PYTEST`/`parse_pytest` shims kept);
  `tests/test_lang_python.py` + `tests/fixtures/traces/python/`;
  `test_prod_repofix.py` untouched green; 722 green at merge.
- L-J2 DONE (31ad582, main): multi-language assembler (UNION start,
  python-legacy + generic completion, orphan handoff); registry parse in
  `assemble`; traceback-rule fallback + `language`/`autofix`/`autofix_note`
  in gate bodies; Sentry `platform` → native rendering + marker;
  `should_trigger` names the adapter, `_pipeline` enforces `detect`;
  adapter + `test_relpath` threaded; 737 green at merge.
- Checkpoint DONE (this commit): python claim gate + `ClaimGateTest`
  (node/go/java/rust/php), TS autofix test gated, `venv` ignored;
  743 green, `check.sh` green. Unblocks John's L-N1 wiring merge.
- L-J3 DONE (3aed4f1, main): `lang/java.py` (JVM parser, package→path
  incl. multi-module, Maven+Gradle, surefire XML + stdout fallbacks);
  8 real fixtures (6 java + 2 kotlin); Modal images + image threading;
  proof-app-java + proof-app-kotlin E2E PASS in Docker (mocked GitHub).
- L-J4 DONE (this commit): `lang/go.py` (panic + goroutine parser with
  `log.Printf` timestamp tolerance, module-path stripping, `go test`
  JSON); 6 real fixtures; `GOMODCACHE`/`GOCACHE` (+ preemptive
  `CARGO_HOME` for Jude) pinned to /work; proof-app-go E2E PASS in
  Docker (mocked GitHub, /tmp/e2e_go.py); 919 green, `check.sh` green.
- L-J4 LEFT: not started — `lang/go.py` (panic parser, module-path strip,
  `go test -json`). proof-app-go on main — E2E unblocked.
- L-J5 LEFT: not started — snapshot filter (`target/`, `build/`,
  `.gradle/`, PHP `vendor/` dropped; Go `vendor/` + wrapper jar kept) +
  `docs/production-backend.md` adapter section.
