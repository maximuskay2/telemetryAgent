"""JavaScript/TypeScript language adapter (L-N1, wired at `lang-contracts-in`).

One `ADAPTER` named `"javascript"`; TypeScript resolves through the
registry alias (`by_name("typescript")`) and the repo refinement
(`refined_name` → `"typescript"` when `tsconfig.json` is present) — the
executable contract in `tests/test_lang_core.py::test_aliases_resolve`
requires alias identity, so this module deliberately does NOT define a
second `typescript` adapter object. `parse_trace` still sniffs
`"typescript"` from `.ts` frames and the registry keeps that stamp.

Runner detection order (§1.1 + James's Q2 answer): configured manifest
(`configure_manifests`) → config file → "jest" default. The suite
commands additionally probe the installed `node_modules/.bin` binaries
at runtime (ground truth after install); `node --test` is the final
fallthrough because a runner-less repo can only run that offline.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import Callable, Dict, List, Optional, Tuple

from core.ingest.traceback import Frame, TracebackInfo
from core.repo_fix.lang import results as shared_results
from core.repo_fix.lang.base import SuiteResult

#: §1.1 row "Image" / "Timeouts".
IMAGE = "node"
INSTALL_TIMEOUT_S = 300
SUITE_TIMEOUT_S = 600

JEST_RESULTS_FILE = "ta-jest-results.json"
VITEST_RESULTS_FILE = "ta-vitest-results.json"

_JS_EXTS = (".js", ".mjs", ".cjs", ".jsx")
_TS_EXTS = (".ts", ".tsx", ".mts", ".cts")
_SOURCE_EXTS = _JS_EXTS + _TS_EXTS

_SKIP_DIRS = ("node_modules/", "dist/", "build/", "coverage/", ".git/")


# --------------------------------------------------------------------------
# Trace detection (trace_start / trace_continues)


#: `TypeError: msg`, `AssertionError [ERR_X]: msg`, optional ⨯ / Uncaught.
#: The name must start uppercase: lowercase `page:` / `errno:` / `https:`
#: lines are log noise, and single letters reject `C:\...` drive paths.
_ERROR_HEAD_RE = re.compile(
    r"^(?:[⨯×]\s*)?(?:Uncaught\s+)?"
    r"([A-Z][\w$]*(?:\.[A-Za-z_$][\w$]*)*)"
    r"(?:\s+\[[^\]\n]+\])?\s*:\s?(.*)$"
)

#: `[Error: ENOENT: ..., open 'x'] {` — inspected error objects.
_OBJECT_ERROR_RE = re.compile(
    r"^\[([A-Z][\w$]*)\s*:\s?(.*)\]\s*\{?\s*$"
)

#: `[cause]: SyntaxError: ...` — continues a trace, never starts one.
_CAUSE_RE = re.compile(r"^\s*\[cause\]:\s?")

#: `    at fn (/a/b.js:1:2)` — any frame-shaped line continues.
_AT_RE = re.compile(r"^\s*at\s+")

#: `... 6 lines matching cause stack trace ...`
_ELISION_RE = re.compile(r"^\s*\.\.\.")

#: `Node.js v26.12.1` trailer.
_TRAILER_RE = re.compile(r"^Node\.js v\d")

#: Next.js code-frame gutters: `  1 | code`, `> 3 | code`, `    |   ^`.
_GUTTER_RE = re.compile(r"^\s*>?\s*\d*\s*\|")

#: Lone braces of an inspected error / cause object.
_BRACE_RE = re.compile(r"^\s*[\{\}]\s*$")


def trace_start(line: str) -> bool:
    """True when `line` opens a V8 stack trace in a log stream."""
    stripped = line.strip()
    if not stripped:
        return False
    if _CAUSE_RE.match(stripped):
        return False
    if _OBJECT_ERROR_RE.match(stripped):
        return True
    match = _ERROR_HEAD_RE.match(stripped)
    if not match:
        return False
    return len(match.group(1)) >= 2


def trace_continues(line: str) -> bool:
    """True when `line` belongs to the open V8 trace (never the head)."""
    stripped = line.strip()
    if not stripped:
        return False
    if _AT_RE.match(line):
        return True
    if _CAUSE_RE.match(stripped):
        return True
    if _ELISION_RE.match(stripped):
        return True
    if _TRAILER_RE.match(stripped):
        return True
    if _GUTTER_RE.match(line):
        return True
    if _BRACE_RE.match(stripped):
        return True
    return False


# --------------------------------------------------------------------------
# Trace parsing (parse_trace)


#: `    at fn (/a/b.js:1:2)` — parens, func and async/[as ...] optional;
#: `file://` ESM frames, bare `node:internal/...` and trailing `{` (cause).
_FRAME_RE = re.compile(
    r"^\s*at\s+(?:(.+?)\s+)?\(?([^\s()]+):(\d+):(\d+)\)?\s*\{?\s*$"
)


def _split_head(stripped: str) -> Tuple[str, str]:
    """(exc_type, exc_value) for a `trace_start` line."""
    found = _OBJECT_ERROR_RE.match(stripped)
    if found:
        return found.group(1), found.group(2).strip()
    found = _ERROR_HEAD_RE.match(stripped)
    if not found:  # pragma: no cover — trace_start already accepted it
        return "", ""
    return found.group(1), (found.group(2) or "").strip()


def _clean_frame(match: "re.Match[str]") -> Optional[Frame]:
    func = (match.group(1) or "").strip()
    if func.startswith("async "):
        func = func[len("async "):]
    file = match.group(2)
    if file.startswith("file://"):
        file = file[len("file://"):]
    try:
        lineno = int(match.group(3))
    except ValueError:
        return None
    return Frame(file=file, line=lineno, func=func)


def sniff_language(frames: List[Frame]) -> str:
    """`typescript` when any frame already points at TS sources."""
    for frame in frames:
        if frame.file.endswith(_TS_EXTS):
            return "typescript"
    return "javascript"


def parse_trace(text: str) -> Optional[TracebackInfo]:
    """Parse joined V8 text; None unless it opens with an error head.

    The FIRST error line wins (V8 prints the thrown error before its
    `[cause]` chain); cause frames are still collected. Frames without a
    `path:line:col` location (`at JSON.parse (<anonymous>)`) are skipped:
    they can never locate code.
    """
    exc_type = ""
    exc_value = ""
    frames: List[Frame] = []
    found_head = False
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\n")
        if not found_head:
            if trace_start(line):
                exc_type, exc_value = _split_head(line.strip())
                found_head = True
            continue
        if _CAUSE_RE.match(line.strip()):
            continue  # the outer error stays the exception
        match = _FRAME_RE.match(line)
        if match:
            frame = _clean_frame(match)
            if frame is not None:
                frames.append(frame)
    if not found_head:
        return None
    return TracebackInfo(
        exc_type=exc_type, exc_value=exc_value, frames=frames,
        raw=text, language=sniff_language(frames),
    )


# --------------------------------------------------------------------------
# Repo matching (detect / map_frame / source_files)


def _basenames(paths: List[str]) -> set:
    return {path.rsplit("/", 1)[-1] for path in paths}


def detect(paths: List[str]) -> int:
    """> 0 when the repo is JS/TS (package.json required to run anything)."""
    names = _basenames(paths)
    if "package.json" not in names:
        return 0
    score = 10
    if "tsconfig.json" in names:
        score += 5
    return score


def is_typescript_repo(paths: List[str]) -> bool:
    """True when the repo carries a tsconfig.json (adapter `name`)."""
    return "tsconfig.json" in _basenames(paths)


def _strip_build_dir(norm: str) -> Optional[str]:
    """`app/dist/x.js` -> `x.js`; None outside known build dirs."""
    for build in ("/dist/", "/build/", "/out/", "/lib/"):
        if build in norm:
            return norm.split(build, 1)[1]
    return None


def map_frame(
    frame_file: str, func: str, paths: List[str]
) -> Optional[str]:
    """Map a V8 frame file to a repo path, or None.

    `node:*` internals, `node_modules`, remote URLs and anonymous frames
    never locate. `dist/x.js` remaps to `src/x.ts` (any TS/JS extension)
    when the sources exist in the snapshot.
    """
    candidate = frame_file.strip()
    if candidate.startswith("file://"):
        candidate = candidate[len("file://"):]
    if not candidate:
        return None
    if candidate.startswith(("node:", "<", "evalmachine")):
        return None
    if "://" in candidate:
        return None
    norm = candidate.replace("\\", "/")
    if "node_modules/" in norm:
        return None
    best: Optional[str] = None
    for path in paths:
        if norm == path or norm.endswith("/" + path):
            if best is None or len(path) > len(best):
                best = path
    if best is not None:
        return best
    tail = _strip_build_dir(norm)
    if tail is not None:
        stem = tail.rsplit(".", 1)[0]
        for ext in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts"):
            for path in paths:
                if path == f"src/{stem}{ext}" or path.endswith(
                    f"/src/{stem}{ext}"
                ):
                    return path
        # Build output whose sources live outside `src/` (e.g. tsc
        # `rootDir: tsrc`): unique basename match only, never a guess.
        base = stem.rsplit("/", 1)[-1]
        cands = [
            path
            for path in paths
            if path.rsplit("/", 1)[-1] in (f"{base}.ts", f"{base}.tsx")
        ]
        if len(cands) == 1:
            return cands[0]
    return None


def source_files(paths: List[str]) -> List[str]:
    """JS/TS sources shown to the model as the repo layout."""
    kept = []
    for path in paths:
        lowered = path.lower()
        if any(part in lowered for part in _SKIP_DIRS):
            continue
        if lowered.endswith(_SOURCE_EXTS):
            kept.append(path)
    return kept


# --------------------------------------------------------------------------
# Install + test commands (install_cmds / suite_cmd / single_test_cmd)


def _project_names(paths: List[str]) -> set:
    return _basenames(paths)


def install_cmds(paths: List[str]) -> List[List[str]]:
    """Install with the repo's lockfile (§1.1); run with network on."""
    names = _project_names(paths)
    if "package-lock.json" in names:
        return [["npm", "ci"]]
    if "pnpm-lock.yaml" in names:
        return [["corepack", "enable"], ["pnpm", "i", "--frozen-lockfile"]]
    if "yarn.lock" in names:
        return [["corepack", "enable"], ["yarn", "install", "--frozen-lockfile"]]
    return [["npm", "install", "--no-audit", "--no-fund"]]


def _runner_from_manifest(text: Optional[str]) -> Optional[str]:
    """Runner named by a package.json, or None (never raises)."""
    if not text:
        return None
    try:
        manifest = json.loads(text)
    except ValueError:
        return None
    if not isinstance(manifest, dict):
        return None
    if isinstance(manifest.get("jest"), dict):
        return "jest"
    scripts = manifest.get("scripts")
    test_script = ""
    if isinstance(scripts, dict):
        test_script = str(scripts.get("test") or "")
    deps: List[str] = []
    for key in ("dependencies", "devDependencies"):
        section = manifest.get(key)
        if isinstance(section, dict):
            deps.extend(str(name) for name in section)
    blob = test_script + "\n" + "\n".join(deps)
    for runner in ("vitest", "jest", "mocha"):
        if runner in blob:
            return runner
    if "node --test" in test_script or "node:test" in test_script:
        return "node:test"
    return None


def _runner_from_config(paths: List[str]) -> Optional[str]:
    """Runner named by a config file in `paths`, or None."""
    names = _basenames(paths)
    for name in names:
        if name.startswith("vitest.config.") or name.startswith(
            "vite.config."
        ):
            return "vitest"
    for name in names:
        if name.startswith("jest.config."):
            return "jest"
    for name in names:
        if name == ".mocharc" or name.startswith(".mocharc."):
            return "mocha"
    return None


def detect_runner(
    paths: List[str], manifest: Optional[str] = None
) -> str:
    """Best-known runner: manifest → config file → "jest" (Q2 default)."""
    hint = _runner_from_manifest(manifest)
    if hint is not None:
        return hint
    hint = _runner_from_config(paths)
    if hint is not None:
        return hint
    return "jest"


#: Probe order for the suite scripts: the hinted binary runner first,
#: the rest in the default order, `node --test` always last (it is the
#: only thing a runner-less repo can run offline).
_DEFAULT_BINARY_ORDER = ("vitest", "jest", "mocha")


def _probe_order(first: Optional[str]) -> Tuple[str, ...]:
    if first in _DEFAULT_BINARY_ORDER:
        rest = [name for name in _DEFAULT_BINARY_ORDER if name != first]
        return (first,) + tuple(rest)
    return _DEFAULT_BINARY_ORDER


_SUITE_TAIL = {
    "vitest": (
        "node_modules/.bin/vitest run "
        f"--reporter=json --outputFile={VITEST_RESULTS_FILE}"
    ),
    "jest": (
        "node_modules/.bin/jest --ci --json "
        f"--outputFile={JEST_RESULTS_FILE} --coverage=false --forceExit"
    ),
    "mocha": "node_modules/.bin/mocha --reporter spec --no-colors",
}

_SINGLE_TAIL = {
    "vitest": (
        'node_modules/.bin/vitest run "$F" '
        f"--reporter=json --outputFile={VITEST_RESULTS_FILE}"
    ),
    "jest": (
        "node_modules/.bin/jest --ci --json "
        f"--outputFile={JEST_RESULTS_FILE} --coverage=false --forceExit "
        '--runTestsByPath "$F"'
    ),
    "mocha": 'node_modules/.bin/mocha --reporter spec --no-colors "$F"',
}


def _probe_chain(order: Tuple[str, ...], tails: Dict[str, str]) -> str:
    lines = []
    for index, runner in enumerate(order):
        keyword = "if" if index == 0 else "elif"
        lines.append(f"{keyword} [ -x node_modules/.bin/{runner} ]; then")
        lines.append(f"  {tails[runner]}")
    return "\n".join(lines)


def _suite_script(first: Optional[str] = None) -> str:
    return (
        f"rm -f {JEST_RESULTS_FILE} {VITEST_RESULTS_FILE}\n"
        + _probe_chain(_probe_order(first), _SUITE_TAIL)
        + "\nelse\n  node --test --test-reporter=tap\nfi"
    )


def _single_script(test_relpath: str, first: Optional[str] = None) -> str:
    return (
        f"rm -f {JEST_RESULTS_FILE} {VITEST_RESULTS_FILE}\n"
        f"F={shlex.quote(test_relpath)}\n"
        + _probe_chain(_probe_order(first), _SINGLE_TAIL)
        + '\nelse\n  node --test --test-reporter=tap "$F"\nfi'
    )


def suite_cmd(
    paths: List[str], first: Optional[str] = None
) -> List[str]:
    """Network-off suite; binaries probed at runtime, `first` runner first.

    Stale result files are removed first so a crashed run can never
    parse the previous run's JSON.
    """
    _ = paths
    return ["sh", "-c", _suite_script(first)]


def single_test_cmd(
    test_relpath: str, paths: List[str], first: Optional[str] = None
) -> List[str]:
    """Run one test file (the repro proof); same detection as the suite."""
    _ = paths
    return ["sh", "-c", _single_script(test_relpath, first)]


# --------------------------------------------------------------------------
# Result parsing (parse_results)


def _parse_jest_like(data: object) -> SuiteResult:
    """Jest/Vitest `--json` report (both share the shape).

    Counts + ids come from the shared `results.parse_jest_json`; two
    stricter rules stay here: a suite that died before any test ran
    (compile error) counts as a failure, and a report with zero tests
    is `errored` — a broken run can never read as "no new failures".
    """
    if not isinstance(data, dict):
        return SuiteResult(0, 0, 0, [], True)
    try:
        base = shared_results.parse_jest_json(json.dumps(data))
    except (TypeError, ValueError):
        return SuiteResult(0, 0, 0, [], True)
    if base.errored:
        return base
    failed_ids = list(base.failed_ids)
    failed = base.failed
    suites = data.get("testResults") or []
    if isinstance(suites, list):
        for suite in suites:
            if not isinstance(suite, dict):
                continue
            if suite.get("assertionResults"):
                continue
            name = str(suite.get("name") or "")
            if str(suite.get("status") or "") == "failed" and name:
                failed_ids.append(f"{name} > suite failed to run")
                failed += 1
    total = base.passed + failed
    if total == 0:
        return SuiteResult(0, 0, 0, failed_ids, True)
    return SuiteResult(total, base.passed, failed, failed_ids, False)


def _extract_json(text: str) -> Optional[object]:
    """Best-effort JSON blob out of mixed runner output (jest --json)."""
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except ValueError:
        return None


_TAP_RESULT_RE = re.compile(r"^(not )?ok \d+ - (.*)$")


def _looks_like_tap(stdout: str) -> bool:
    head = "\n".join(stdout.splitlines()[:5])
    if "TAP version" in head:
        return True
    return any(
        _TAP_RESULT_RE.match(line.strip()) for line in stdout.splitlines()
    )


def _tap_blocks(lines: List[str]) -> List[Tuple[bool, str, List[str]]]:
    """(failed, name, yaml lines) per TAP result line."""
    found: List[Tuple[int, bool, str]] = []
    for index, line in enumerate(lines):
        match = _TAP_RESULT_RE.match(line.strip())
        if match:
            found.append((index, bool(match.group(1)), match.group(2)))
    blocks = []
    for pos, (index, failed, name) in enumerate(found):
        stop = found[pos + 1][0] if pos + 1 < len(found) else len(lines)
        blocks.append((failed, name, lines[index + 1:stop]))
    return blocks


def _tap_block_type(yaml: List[str]) -> Optional[str]:
    """The TAP diagnostic `type:` of a result block, if it has one."""
    for entry in yaml:
        found = re.match(r"\s*type:\s*['\"]?(\w+)", entry)
        if found:
            return found.group(1)
    return None


def _parse_tap(stdout: str) -> SuiteResult:
    """`node --test --test-reporter=tap` output.

    Suite summaries (`type: 'suite'`) never count; every other result
    line is a test. (Real node 20 output has no `type: 'test'` lines at
    all — only suites are tagged — so absence of `type:` means "test",
    which also keeps foreign TAP working.)
    """
    lines = stdout.splitlines()
    blocks = _tap_blocks(lines)
    total = 0
    failed = 0
    failed_ids: List[str] = []
    for is_fail, name, yaml in blocks:
        if _tap_block_type(yaml) not in (None, "test"):
            continue  # suite summary line, not a test
        total += 1
        if not is_fail:
            continue
        failed += 1
        location = ""
        for entry in yaml:
            found = re.search(r"location:\s*['\"]?([^'\"\s]+)", entry)
            if found:
                location = found.group(1)
                location = re.sub(r":\d+:\d+$", "", location)
                break
        failed_ids.append(
            f"{location} > {name}" if location else name
        )
    if total == 0:
        return SuiteResult(0, 0, 0, [], True)
    return SuiteResult(total, total - failed, failed, failed_ids, False)


_MOCHA_PASSING_RE = re.compile(r"(\d+)\s+passing")
_MOCHA_FAILING_RE = re.compile(r"(\d+)\s+failing")
_MOCHA_DETAIL_RE = re.compile(r"^\s*\d+\)\s+(.+):\s*$")


def _looks_like_mocha(stdout: str) -> bool:
    return bool(
        _MOCHA_PASSING_RE.search(stdout) or _MOCHA_FAILING_RE.search(stdout)
    )


def _parse_mocha(stdout: str) -> SuiteResult:
    """Mocha `spec` reporter output (counts + numbered failures)."""
    lines = stdout.splitlines()
    passed = 0
    failed = 0
    found = _MOCHA_PASSING_RE.search(stdout)
    if found:
        passed = int(found.group(1))
    found = _MOCHA_FAILING_RE.search(stdout)
    if found:
        failed = int(found.group(1))
    failed_ids: List[str] = []
    for index, line in enumerate(lines):
        detail = _MOCHA_DETAIL_RE.match(line)
        if not detail:
            continue
        title = detail.group(1).strip()
        source = ""
        for follow in lines[index + 1:]:
            if _MOCHA_DETAIL_RE.match(follow):
                break
            frame = _FRAME_RE.match(follow)
            if frame:
                candidate = frame.group(2)
                if "node:" not in candidate and "node_modules" not in candidate:
                    source = candidate
                    break
        failed_ids.append(f"{source} > {title}" if source else title)
    total = passed + failed
    if total == 0:
        return SuiteResult(0, 0, 0, failed_ids, True)
    return SuiteResult(total, passed, failed, failed_ids, False)


def parse_results(
    stdout: str,
    stderr: str,
    read_file: Callable[[str], Optional[str]],
) -> SuiteResult:
    """SuiteResult from any runner my commands produce.

    Probes in order: the Jest/Vitest JSON output files, a `--json` blob
    on stderr, TAP on stdout, Mocha spec on stdout. Anything else —
    including an empty run — is `errored` (the pipeline drafts rather
    than claim a proof it cannot read).
    """
    for name in (JEST_RESULTS_FILE, VITEST_RESULTS_FILE):
        try:
            raw = read_file(name)
        except Exception:
            raw = None
        if raw:
            try:
                return _parse_jest_like(json.loads(raw))
            except ValueError:
                return SuiteResult(0, 0, 0, [], True)
    blob = _extract_json(stderr)
    if isinstance(blob, dict) and "numTotalTests" in blob:
        return _parse_jest_like(blob)
    if _looks_like_tap(stdout):
        return _parse_tap(stdout)
    if _looks_like_mocha(stdout):
        return _parse_mocha(stdout)
    return SuiteResult(0, 0, 0, [], True)


# --------------------------------------------------------------------------
# Repro tests (repro_test_path / repro_rules / looks_like_test)


_TEST_DIRS = ("__tests__", "test", "tests")


def _repro_ext(paths: List[str], located: List[str]) -> str:
    if located:
        suffix = "." + located[0].rsplit(".", 1)[-1].lower()
        if suffix in _SOURCE_EXTS:
            return suffix
    if is_typescript_repo(paths):
        return ".ts"
    return ".js"


def repro_test_path(
    fingerprint: str, paths: List[str], located: List[str]
) -> str:
    """`ta_repro_<fp12>.test.<ext>` in the repo's own test convention."""
    name = f"ta_repro_{fingerprint[:12]}.test{_repro_ext(paths, located)}"
    best: Optional[str] = None
    best_tests = -1
    for entry in _TEST_DIRS:
        members = [
            path for path in paths
            if path == entry or path.startswith(entry + "/")
        ]
        if not members:
            continue
        count = sum(
            1 for path in members
            if ".test." in path.rsplit("/", 1)[-1]
            or ".spec." in path.rsplit("/", 1)[-1]
        )
        if count > best_tests:
            best = entry
            best_tests = count
    if best is not None:
        return f"{best}/{name}"
    if located and "/" in located[0]:
        return f"{located[0].rsplit('/', 1)[0]}/{name}"
    return f"tests/{name}"


_RUNNER_LABELS = {
    "vitest": "Vitest",
    "jest": "Jest",
    "mocha": "Mocha",
    "node:test": "node:test",
}


def repro_rules(runner: Optional[str] = None) -> str:
    """Appended to the repro system prompt; names `runner` when known."""
    survey = (
        "Match the neighbouring tests' runner and style (see the file "
        "list): Jest/Vitest use test()/it() with expect(); Mocha uses "
        "describe()/it() with assert or expect; node:test imports "
        "{ describe, it } from 'node:test' with node:assert. Import the "
        "buggy module with a relative path from the test file. TypeScript "
        "repos: typed test code. The test MUST fail on the current code "
        "and pass once the bug is fixed; no network, no timers, "
        "deterministic."
    )
    if runner in _RUNNER_LABELS:
        label = _RUNNER_LABELS[runner]
        return f"This repo runs {label}; write the test for {label}. " + survey
    return survey


_TEST_FN_RE = re.compile(r"\b(?:test|it)\s*\(")
_TEST_ASSERT_RE = re.compile(r"\b(?:expect|assert)\b")


def looks_like_test(code: str) -> bool:
    """`test(`/`it(` plus `expect`/`assert` (§1.1)."""
    return bool(_TEST_FN_RE.search(code) and _TEST_ASSERT_RE.search(code))


# --------------------------------------------------------------------------
# Adapter wiring (§3; discovered via `ADAPTER` by the registry)


class _JavaScriptAdapter:
    """The §3 adapter; every method delegates to the pure functions."""

    name = "javascript"
    image = IMAGE
    install_timeout_s = INSTALL_TIMEOUT_S
    suite_timeout_s = SUITE_TIMEOUT_S

    def __init__(self) -> None:
        self._manifest: Optional[str] = None

    def manifest_names(self) -> List[str]:
        """Manifests run.py fetches before the command methods (Q2 hook)."""
        return ["package.json"]

    def configure_manifests(
        self, manifests: Dict[str, Optional[str]]
    ) -> None:
        try:
            text = manifests.get("package.json")
        except AttributeError:
            text = None
        self._manifest = text if isinstance(text, str) else None

    def _first(self, paths: List[str]) -> str:
        return detect_runner(paths, self._manifest)

    def detect(self, paths: List[str]) -> int:
        return detect(paths)

    def trace_start(self, line: str) -> bool:
        return trace_start(line)

    def trace_continues(self, line: str) -> bool:
        return trace_continues(line)

    def parse_trace(self, text: str) -> Optional[TracebackInfo]:
        return parse_trace(text)

    def map_frame(
        self, frame_file: str, func: str, paths: List[str]
    ) -> Optional[str]:
        return map_frame(frame_file, func, paths)

    def source_files(self, paths: List[str]) -> List[str]:
        return source_files(paths)

    def install_cmds(self, paths: List[str]) -> List[List[str]]:
        return install_cmds(paths)

    def suite_cmd(self, paths: List[str]) -> List[str]:
        return suite_cmd(paths, first=self._first(paths))

    def single_test_cmd(
        self, test_relpath: str, paths: List[str]
    ) -> List[str]:
        return single_test_cmd(
            test_relpath, paths, first=self._first(paths)
        )

    def parse_results(
        self, stdout: str, stderr: str, read_file: Callable[[str], Optional[str]]
    ) -> SuiteResult:
        return parse_results(stdout, stderr, read_file)

    def repro_test_path(
        self, fingerprint: str, paths: List[str], located: List[str]
    ) -> str:
        return repro_test_path(fingerprint, paths, located)

    def repro_rules(self) -> str:
        return repro_rules(_runner_from_manifest(self._manifest))

    def looks_like_test(self, code: str) -> bool:
        return looks_like_test(code)


ADAPTER = _JavaScriptAdapter()
