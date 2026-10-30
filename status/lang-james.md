# James status (languages)
Current block: L-J3 next (L-J0 + L-J1 + L-J2 done, merging L-J2)
Done: L-J0 (8276c12, on main, tagged lang-contracts-in), L-J1 (c2c2d8a),
  L-J2 (this commit)
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
- L-J2 DONE (this commit): multi-language assembler (UNION start,
  python-legacy + generic completion, orphan handoff); registry parse in
  `assemble`; traceback-rule fallback + `language`/`autofix`/`autofix_note`
  in gate bodies; Sentry `platform` → native rendering + marker;
  `should_trigger` names the adapter, `_pipeline` enforces `detect`;
  adapter + `test_relpath` threaded; 737 green, `check.sh` green.
- L-J3 LEFT: not started — `lang/java.py` (JVM parser, package→path,
  Maven+Gradle, surefire/Gradle XML). Jude's proof-app-java/kotlin are on
  main (L-D1) — E2E unblocked.
- L-J4 LEFT: not started — `lang/go.py` (panic parser, module-path strip,
  `go test -json`). proof-app-go on main — E2E unblocked.
- L-J5 LEFT: not started — snapshot filter (`target/`, `build/`,
  `.gradle/`, PHP `vendor/` dropped; Go `vendor/` + wrapper jar kept) +
  `docs/production-backend.md` adapter section.
