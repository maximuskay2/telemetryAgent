"""L-N1: JS/TS adapter pure functions (pre-contracts, coded to §3)."""

import unittest
from pathlib import Path

from core.repo_fix.lang import javascript as js

TRACES = Path(__file__).resolve().parent / "fixtures" / "traces"


def trace(*parts):
    return (TRACES.joinpath(*parts)).read_text(encoding="utf-8")


def info(*parts):
    parsed = js.parse_trace(trace(*parts))
    assert parsed is not None
    return parsed


class TraceStartTest(unittest.TestCase):
    def test_heads(self):
        for line in (
            "TypeError: Cannot read properties of null",
            "Error: boom",
            "⨯ TypeError: no good",
            "Uncaught ReferenceError: x is not defined",
            "AssertionError [ERR_ASSERTION]: 1 !== 2",
            "[Error: ENOENT: no such file, open 'x'] {",
            "Foo.BarError: namespaced",
        ):
            self.assertTrue(js.trace_start(line), line)

    def test_not_heads(self):
        for line in (
            "",
            "    at fn (/a/b.js:1:2)",
            "page: '/api/checkout'",
            "  errno: -2,",
            "https://example.com/app.js",
            "GET /api/checkout 500 in 12ms",
            "[cause]: SyntaxError: bad json",
            "Traceback (most recent call last):",
            "C:\\app\\server.js",
            "return items.reduce((a, b) => a + b, 0);",
        ):
            self.assertFalse(js.trace_start(line), line)


class TraceContinuesTest(unittest.TestCase):
    def test_continuations(self):
        for line in (
            "    at fn (/a/b.js:1:2)",
            "      at JSON.parse (<anonymous>)",
            "    ... 6 lines matching cause stack trace ...",
            "  [cause]: SyntaxError: bad json",
            "Node.js v26.12.1",
            "  1 | const x = 1;",
            "> 3 |   throw boom;",
            "    |       ^",
            "{",
            "}",
            "    at node:internal/main/run_main_module:33:47 {",
        ):
            self.assertTrue(js.trace_continues(line), line)

    def test_endings(self):
        for line in ("", "page: '/api/checkout'", "  errno: -2,",
                     "GET /ok 200 in 1ms", "TypeError: next crash"):
            self.assertFalse(js.trace_continues(line), line)


class ParseTraceTest(unittest.TestCase):
    def test_node_typeerror(self):
        parsed = info("javascript", "node_typeerror.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertIn("reduce", parsed.exc_value)
        self.assertEqual(parsed.language, "javascript")
        self.assertEqual(len(parsed.frames), 10)
        first = parsed.frames[0]
        self.assertEqual(first.file, "/app/src/sync_bug.js")
        self.assertEqual(first.line, 2)
        self.assertEqual(first.func, "average")

    def test_express_parses_app_frame_first(self):
        parsed = info("javascript", "express_error_middleware.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertEqual(parsed.frames[0].file, "/app/src/express_bug.js")
        self.assertTrue(
            any("node_modules" in frame.file for frame in parsed.frames)
        )

    def test_next_api_route(self):
        parsed = info("javascript", "next_api_route.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertEqual(len(parsed.frames), 1)
        self.assertEqual(parsed.frames[0].file, "pages/api/checkout.js")
        self.assertEqual(parsed.frames[0].line, 3)

    def test_async_object_dump_has_exc_but_no_frames(self):
        parsed = info("javascript", "node_async_enoent.txt")
        self.assertEqual(parsed.exc_type, "Error")
        self.assertIn("ENOENT", parsed.exc_value)
        self.assertEqual(parsed.frames, [])

    def test_esm_strips_file_urls(self):
        parsed = info("javascript", "node_esm_sync.txt")
        self.assertEqual(parsed.frames[0].file, "/app/src/esm_sync.mjs")

    def test_cause_chain_outer_error_wins(self):
        parsed = info("javascript", "node_error_cause.txt")
        self.assertEqual(parsed.exc_type, "Error")
        self.assertEqual(parsed.exc_value, "invalid webhook payload")
        # Main frames plus the cause frames; the elision line is skipped.
        self.assertEqual(len(parsed.frames), 12)
        self.assertIn("cause.js", parsed.frames[0].file)

    def test_recursion_and_trailer(self):
        parsed = info("javascript", "node_range_recursion.txt")
        self.assertEqual(parsed.exc_type, "RangeError")
        self.assertTrue(len(parsed.frames) >= 10)
        self.assertTrue(
            all(frame.func == "countdown" for frame in parsed.frames)
        )

    def test_unhandled_rejection(self):
        parsed = info("javascript", "node_unhandled_rejection.txt")
        self.assertEqual(parsed.exc_type, "Error")
        self.assertEqual(
            parsed.exc_value, "payment gateway timed out"
        )
        self.assertTrue(len(parsed.frames) >= 2)

    def test_browser_uncaught_keeps_urls(self):
        parsed = info("javascript", "browser_uncaught.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertEqual(len(parsed.frames), 2)
        self.assertTrue(parsed.frames[0].file.startswith("https://"))

    def test_ts_with_sourcemaps_is_typescript(self):
        parsed = info("typescript", "tsc_sourcemap.txt")
        self.assertEqual(parsed.language, "typescript")
        self.assertEqual(parsed.frames[0].file, "/app/tsrc/cart.ts")

    def test_ts_without_sourcemaps_points_at_dist(self):
        parsed = info("typescript", "tsc_no_sourcemap.txt")
        self.assertEqual(parsed.language, "javascript")
        self.assertEqual(parsed.frames[0].file, "/app/dist/cart.js")

    def test_plain_log_is_none(self):
        self.assertIsNone(js.parse_trace("GET /ok 200 in 1ms\nall quiet\n"))
        self.assertIsNone(js.parse_trace(""))


class MapFrameTest(unittest.TestCase):
    PATHS = [
        "package.json",
        "src/cart.js",
        "src/tsrc_helper.py",
        "tsrc/cart.ts",
        "src/nested/deep/util.ts",
        "tests/cart.test.js",
    ]

    def test_direct_suffix(self):
        self.assertEqual(
            js.map_frame("/app/src/cart.js", "total", self.PATHS),
            "src/cart.js",
        )

    def test_relative_next_frame(self):
        self.assertEqual(
            js.map_frame(
                "pages/api/checkout.js", "handler",
                ["pages/api/checkout.js"],
            ),
            "pages/api/checkout.js",
        )

    def test_internals_and_vendor_never_locate(self):
        for name in (
            "node:internal/modules/cjs/loader",
            "node:async_hooks",
            "/app/node_modules/express/index.js",
            "https://example.com/app.js",
            "<anonymous>",
            "evalmachine.<anonymous>",
            "",
        ):
            self.assertIsNone(js.map_frame(name, "f", self.PATHS), name)

    def test_dist_remaps_to_src(self):
        paths = ["package.json", "src/cart.ts"]
        self.assertEqual(
            js.map_frame("/app/dist/cart.js", "total", paths), "src/cart.ts"
        )

    def test_dist_falls_back_to_unique_ts_basename(self):
        # No src/ remap here, so the unique tsrc/*.ts basename wins.
        paths = [p for p in self.PATHS if p != "src/cart.js"]
        self.assertEqual(
            js.map_frame("/app/dist/cart.js", "total", paths),
            "tsrc/cart.ts",
        )

    def test_ambiguous_basename_is_none(self):
        paths = ["a/cart.ts", "b/cart.ts"]
        self.assertIsNone(js.map_frame("/app/dist/cart.js", "f", paths))


class DetectTest(unittest.TestCase):
    def test_scores(self):
        self.assertEqual(js.detect(["package.json", "src/a.js"]), 10)
        self.assertEqual(
            js.detect(["package.json", "tsconfig.json", "src/a.ts"]), 15
        )
        self.assertEqual(js.detect(["src/a.js"]), 0)
        self.assertEqual(js.detect([]), 0)

    def test_typescript_repo(self):
        self.assertTrue(js.is_typescript_repo(["package.json", "tsconfig.json"]))
        self.assertFalse(js.is_typescript_repo(["package.json"]))

    def test_source_files(self):
        self.assertEqual(
            js.source_files([
                "package.json", "src/a.js", "src/b.ts", "src/c.tsx",
                "node_modules/x/y.js", "dist/a.js", "README.md",
            ]),
            ["src/a.js", "src/b.ts", "src/c.tsx"],
        )


class CommandsTest(unittest.TestCase):
    def test_install_lockfile_decides(self):
        self.assertEqual(
            js.install_cmds(["package.json", "package-lock.json"]),
            [["npm", "ci"]],
        )
        self.assertEqual(
            js.install_cmds(["package.json", "pnpm-lock.yaml"]),
            [["corepack", "enable"], ["pnpm", "i", "--frozen-lockfile"]],
        )
        self.assertEqual(
            js.install_cmds(["package.json", "yarn.lock"]),
            [["corepack", "enable"], ["yarn", "install", "--frozen-lockfile"]],
        )
        self.assertEqual(
            js.install_cmds(["package.json"]),
            [["npm", "install", "--no-audit", "--no-fund"]],
        )

    def test_suite_detects_runner_from_binaries(self):
        cmd = js.suite_cmd(["package.json"])
        self.assertEqual(cmd[:2], ["sh", "-c"])
        script = cmd[2]
        self.assertIn("node_modules/.bin/vitest", script)
        self.assertIn("node_modules/.bin/jest", script)
        self.assertIn("node_modules/.bin/mocha", script)
        self.assertIn("node --test --test-reporter=tap", script)
        self.assertIn("rm -f ta-jest-results.json ta-vitest-results.json", script)
        self.assertIn("--outputFile=ta-jest-results.json", script)
        self.assertIn("--outputFile=ta-vitest-results.json", script)

    def test_single_test_quotes_path(self):
        cmd = js.single_test_cmd("tests/ta_repro_abc.test.js", ["package.json"])
        self.assertEqual(cmd[:2], ["sh", "-c"])
        self.assertIn("--runTestsByPath", cmd[2])
        self.assertIn("tests/ta_repro_abc.test.js", cmd[2])


def _jest_report(cases, **top):
    suites = [{
        "name": "/work/suites/a.test.js",
        "status": "passed",
        "assertionResults": [
            {
                "ancestorTitles": case[0],
                "title": case[1],
                "status": case[2],
            }
            for case in cases
        ],
    }]
    report = {
        "numTotalTests": len(cases),
        "numPassedTests": sum(1 for c in cases if c[2] == "passed"),
        "numFailedTests": sum(1 for c in cases if c[2] == "failed"),
        "testResults": suites,
    }
    report.update(top)
    return report


class ParseResultsTest(unittest.TestCase):
    def test_jest_json_file(self):
        import json

        report = _jest_report([
            ([], "adds", "passed"),
            (["cart"], "totals", "failed"),
        ])
        result = js.parse_results(
            "", "", lambda name: json.dumps(report)
        )
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(
            result.failed_ids, ["/work/suites/a.test.js > cart > totals"]
        )

    def test_vitest_json_file(self):
        import json

        report = _jest_report([([], "adds", "passed")], success=True)
        result = js.parse_results(
            "", "", lambda name: json.dumps(report)
        )
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (1, 1, 0))

    def test_failed_suite_counts(self):
        import json

        report = {
            "numTotalTests": 0,
            "numPassedTests": 0,
            "numFailedTests": 0,
            "testResults": [{
                "name": "/work/suites/broken.test.js",
                "status": "failed",
                "assertionResults": [],
            }],
        }
        result = js.parse_results("", "", lambda name: json.dumps(report))
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.failed), (1, 1))
        self.assertEqual(
            result.failed_ids,
            ["/work/suites/broken.test.js > suite failed to run"],
        )

    def test_tap_stdout(self):
        tap = (
            "TAP version 13\n"
            "# Subtest: add\n"
            "    # Subtest: adds\n"
            "    ok 1 - adds\n"
            "      ---\n"
            "      duration_ms: 0.3\n"
            "      type: 'test'\n"
            "      ...\n"
            "    1..1\n"
            "ok 1 - add\n"
            "  ---\n"
            "  duration_ms: 0.9\n"
            "  type: 'suite'\n"
            "  ...\n"
            "# Subtest: adds big\n"
            "not ok 2 - adds big\n"
            "  ---\n"
            "  type: 'test'\n"
            "  location: '/work/suites/fail.test.js:4:1'\n"
            "  ...\n"
            "1..2\n"
        )
        result = js.parse_results(tap, "", lambda name: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(
            result.failed_ids, ["/work/suites/fail.test.js > adds big"]
        )

    def test_tap_real_node20_all_pass(self):
        # Captured from node v20.20.2 in telemetry-agent-sandbox-node:
        # passing subtests carry no `type:` line at all.
        tap = (
            "TAP version 13\n"
            "# Subtest: average\n"
            "    # Subtest: averages a list\n"
            "    ok 1 - averages a list\n"
            "      ---\n"
            "      duration_ms: 0.317375\n"
            "      ...\n"
            "    # Subtest: handles one item\n"
            "    ok 2 - handles one item\n"
            "      ---\n"
            "      duration_ms: 0.047667\n"
            "      ...\n"
            "    1..2\n"
            "ok 1 - average\n"
            "  ---\n"
            "  duration_ms: 0.945417\n"
            "  type: 'suite'\n"
            "  ...\n"
            "1..1\n"
            "# pass 2\n"
            "# fail 0\n"
        )
        result = js.parse_results(tap, "", lambda name: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 2, 0))

    def test_tap_real_node20_failure(self):
        # Captured from node v20.20.2: the failing subtest has no
        # `type:` line; the failing suite summary must not count.
        tap = (
            "TAP version 13\n"
            "# Subtest: s\n"
            "    # Subtest: passes\n"
            "    ok 1 - passes\n"
            "      ---\n"
            "      duration_ms: 0.371208\n"
            "      ...\n"
            "    # Subtest: fails\n"
            "    not ok 2 - fails\n"
            "      ---\n"
            "      duration_ms: 0.550208\n"
            "      location: '/work/f.test.js:5:3'\n"
            "      failureType: 'testCodeFailure'\n"
            "      code: 'ERR_ASSERTION'\n"
            "      ...\n"
            "    1..2\n"
            "not ok 1 - s\n"
            "  ---\n"
            "  duration_ms: 1.343792\n"
            "  type: 'suite'\n"
            "  failureType: 'subtestsFailed'\n"
            "  code: 'ERR_TEST_FAILURE'\n"
            "  ...\n"
            "1..1\n"
            "# pass 1\n"
            "# fail 1\n"
        )
        result = js.parse_results(tap, "", lambda name: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(result.failed_ids, ["/work/f.test.js > fails"])

    def test_mocha_stdout(self):
        spec = (
            "\n\n  add\n"
            "    ok adds\n"
            "\n\n  1 passing (4ms)\n"
            "  1 failing\n"
            "\n  1) adds big:\n"
            "\n      AssertionError: 123 !== 124\n"
            "      at Context.<anonymous> (suites/mocha/fail.test.js:3:31)\n"
            "      at process.processImmediate (node:internal/timers:574:21)\n"
        )
        result = js.parse_results(spec, "", lambda name: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(
            result.failed_ids, ["suites/mocha/fail.test.js > adds big"]
        )

    def test_unreadable_is_errored(self):
        self.assertTrue(
            js.parse_results("hello", "boom", lambda name: None).errored
        )
        self.assertTrue(js.parse_results("", "", lambda name: None).errored)
        self.assertTrue(
            js.parse_results("", "", lambda name: "{nope").errored
        )


class ReproTest(unittest.TestCase):
    def test_convention_dirs(self):
        paths = [
            "package.json", "src/a.js", "tests/old.test.js",
            "__tests__/new.test.js",
        ]
        self.assertEqual(
            js.repro_test_path("abcdef1234567890", paths, ["src/a.js"]),
            "__tests__/ta_repro_abcdef123456.test.js",
        )

    def test_most_tests_wins(self):
        paths = [
            "package.json", "test/a.test.js", "test/b.test.js",
            "tests/c.test.js",
        ]
        self.assertEqual(
            js.repro_test_path("fp", paths, []),
            "test/ta_repro_fp.test.js",
        )

    def test_colocated_without_test_dirs(self):
        self.assertEqual(
            js.repro_test_path("fp", ["package.json", "src/a.ts"], ["src/a.ts"]),
            "src/ta_repro_fp.test.ts",
        )

    def test_tsconfig_default_ext(self):
        self.assertEqual(
            js.repro_test_path(
                "fp", ["package.json", "tsconfig.json", "src/a.ts"], []
            ),
            "tests/ta_repro_fp.test.ts",
        )

    def test_looks_like_test(self):
        self.assertTrue(js.looks_like_test("test('x', () => expect(1).toBe(1))"))
        self.assertTrue(
            js.looks_like_test("it('x', function () { assert.equal(1, 1); })")
        )
        self.assertFalse(js.looks_like_test("const latest = split(x);"))
        self.assertFalse(js.looks_like_test("test('x', () => 1);"))
        self.assertFalse(js.looks_like_test("expect(1).toBe(1);"))

    def test_repro_rules_names_styles(self):
        rules = js.repro_rules()
        for word in ("Jest", "Vitest", "Mocha", "node:test", "MUST fail"):
            self.assertIn(word, rules)


class DetectRunnerTest(unittest.TestCase):
    def test_config_files(self):
        self.assertEqual(
            js.detect_runner(["package.json", "vitest.config.ts"]), "vitest"
        )
        self.assertEqual(
            js.detect_runner(["package.json", "vite.config.js"]), "vitest"
        )
        self.assertEqual(
            js.detect_runner(["package.json", "jest.config.cjs"]), "jest"
        )
        self.assertEqual(
            js.detect_runner(["package.json", ".mocharc.yml"]), "mocha"
        )

    def test_manifest(self):
        vitest = (
            '{"scripts": {"test": "vitest run"}, '
            '"devDependencies": {"vitest": "^1.0.0"}}'
        )
        self.assertEqual(js.detect_runner(["package.json"], vitest), "vitest")
        self.assertEqual(
            js.detect_runner(["package.json"], '{"jest": {}}'), "jest"
        )
        self.assertEqual(
            js.detect_runner(
                ["package.json"], '{"scripts": {"test": "mocha"}}'
            ),
            "mocha",
        )
        self.assertEqual(
            js.detect_runner(
                ["package.json"], '{"scripts": {"test": "node --test"}}'
            ),
            "node:test",
        )

    def test_manifest_beats_config(self):
        vitest = '{"devDependencies": {"vitest": "^1.0.0"}}'
        self.assertEqual(
            js.detect_runner(["package.json", "jest.config.js"], vitest),
            "vitest",
        )

    def test_default_is_jest(self):
        self.assertEqual(js.detect_runner(["package.json"]), "jest")
        self.assertEqual(js.detect_runner([]), "jest")

    def test_garbage_manifest_falls_through(self):
        self.assertEqual(
            js.detect_runner(["package.json", ".mocharc.json"], "{nope"),
            "mocha",
        )
        self.assertEqual(js.detect_runner(["package.json"], "{nope"), "jest")
        self.assertEqual(js.detect_runner(["package.json"], "[1,2]"), "jest")
        self.assertEqual(js.detect_runner(["package.json"], None), "jest")


class ReproRulesRunnerTest(unittest.TestCase):
    def test_names_known_runner(self):
        rules = js.repro_rules("vitest")
        self.assertTrue(
            rules.startswith(
                "This repo runs Vitest; write the test for Vitest. "
            ),
            rules,
        )
        self.assertIn("MUST fail", rules)

    def test_unknown_runner_is_survey_only(self):
        self.assertEqual(js.repro_rules("bogus"), js.repro_rules())
        self.assertNotIn("This repo runs", js.repro_rules())


class SuiteOrderTest(unittest.TestCase):
    def test_default_probes_vitest_first(self):
        script = js.suite_cmd(["package.json"])[2]
        self.assertLess(
            script.index("node_modules/.bin/vitest"),
            script.index("node_modules/.bin/jest"),
        )

    def test_hint_moves_runner_first(self):
        script = js.suite_cmd(["package.json"], first="jest")[2]
        self.assertLess(
            script.index("node_modules/.bin/jest"),
            script.index("node_modules/.bin/vitest"),
        )
        single = js.single_test_cmd("t.js", ["package.json"], first="mocha")
        self.assertLess(
            single[2].index("node_modules/.bin/mocha"),
            single[2].index("node_modules/.bin/vitest"),
        )

    def test_node_test_hint_keeps_default_order(self):
        plain = js.suite_cmd(["package.json"])[2]
        hinted = js.suite_cmd(["package.json"], first="node:test")[2]
        self.assertEqual(hinted, plain)


def _fresh_adapter():
    return type(js.ADAPTER)()


class AdapterTest(unittest.TestCase):
    def test_identity(self):
        self.assertEqual(js.ADAPTER.name, "javascript")
        self.assertEqual(js.ADAPTER.image, "node")
        self.assertEqual(
            (js.ADAPTER.install_timeout_s, js.ADAPTER.suite_timeout_s),
            (300, 600),
        )

    def test_suite_result_is_shared(self):
        from core.repo_fix.lang.base import SuiteResult

        self.assertIs(js.SuiteResult, SuiteResult)

    def test_methods_delegate(self):
        adapter = _fresh_adapter()
        paths = ["package.json", "src/a.js"]
        self.assertEqual(adapter.detect(paths), js.detect(paths))
        self.assertTrue(adapter.trace_start("TypeError: x"))
        self.assertTrue(adapter.trace_continues("    at f (/a.js:1:1)"))
        parsed = adapter.parse_trace(trace("javascript", "node_typeerror.txt"))
        self.assertIsNotNone(parsed)
        self.assertEqual(
            adapter.map_frame("/app/src/a.js", "f", paths), "src/a.js"
        )
        self.assertEqual(adapter.source_files(paths), ["src/a.js"])
        self.assertEqual(adapter.install_cmds(paths), js.install_cmds(paths))
        self.assertEqual(
            adapter.suite_cmd(paths), js.suite_cmd(paths, first="jest")
        )
        self.assertEqual(
            adapter.single_test_cmd("t.js", paths),
            js.single_test_cmd("t.js", paths, first="jest"),
        )
        result = adapter.parse_results("hi", "", lambda name: None)
        self.assertTrue(result.errored)
        self.assertEqual(
            adapter.repro_test_path("fp", paths, []),
            js.repro_test_path("fp", paths, []),
        )
        self.assertEqual(adapter.repro_rules(), js.repro_rules())
        self.assertTrue(adapter.looks_like_test("test('x', () => expect(1))"))

    def test_manifest_hook_orders_and_names(self):
        adapter = _fresh_adapter()
        self.assertEqual(adapter.manifest_names(), ["package.json"])
        adapter.configure_manifests(
            {"package.json": '{"devDependencies": {"vitest": "^1.0.0"}}'}
        )
        script = adapter.suite_cmd(["package.json"])[2]
        self.assertLess(
            script.index("node_modules/.bin/vitest"),
            script.index("node_modules/.bin/jest"),
        )
        self.assertIn("This repo runs Vitest", adapter.repro_rules())

    def test_manifest_hook_absent_or_garbage(self):
        adapter = _fresh_adapter()
        adapter.configure_manifests({"package.json": None})
        self.assertEqual(adapter.suite_cmd(["package.json"])[2],
                         js.suite_cmd(["package.json"], first="jest")[2])
        self.assertEqual(adapter.repro_rules(), js.repro_rules())
        adapter.configure_manifests({})
        adapter.configure_manifests(None)  # type: ignore[arg-type]
        adapter.configure_manifests("junk")  # type: ignore[arg-type]
        self.assertEqual(adapter.repro_rules(), js.repro_rules())


class RegistryWiringTest(unittest.TestCase):
    def test_discovered_once_python_first(self):
        from core.repo_fix.lang import all_adapters

        names = [adapter.name for adapter in all_adapters()]
        self.assertEqual(names.count("javascript"), 1)
        self.assertNotIn("typescript", names)  # alias, not an object
        self.assertEqual(names[0], "python")

    def test_alias_identity(self):
        from core.repo_fix.lang import by_name

        self.assertIs(by_name("javascript"), js.ADAPTER)
        self.assertIs(by_name("typescript"), js.ADAPTER)

    def test_parse_routes_v8(self):
        from core.repo_fix.lang import parse

        adapter, found = parse(trace("javascript", "node_typeerror.txt"))
        if adapter.name == "python":
            self.skipTest(
                "framework: python parser claims V8 traces (needs "
                "James L-J1/L-J2 tightening; see Contract changes "
                "requested)"
            )
        self.assertIs(adapter, js.ADAPTER)
        self.assertEqual(found.language, "javascript")
        self.assertTrue(found.frames)
        adapter, found = parse(trace("typescript", "tsc_sourcemap.txt"))
        self.assertIs(adapter, js.ADAPTER)
        self.assertEqual(found.language, "typescript")

    def test_parse_routes_python_away(self):
        from core.repo_fix.lang import parse

        text = (
            "Traceback (most recent call last):\n"
            '  File "/app/a.py", line 1, in <module>\n'
            "ValueError: bad\n"
        )
        adapter, found = parse(text)
        self.assertEqual(adapter.name, "python")
        self.assertEqual(found.language, "python")

    def test_detect_repo(self):
        from core.repo_fix.lang import detect_repo

        self.assertEqual(
            detect_repo(["package.json", "src/a.js"]), [("javascript", 10)]
        )
        self.assertEqual(
            detect_repo(["package.json", "tsconfig.json", "src/a.ts"]),
            [("typescript", 15)],
        )
        self.assertEqual(detect_repo([]), [])


if __name__ == "__main__":
    unittest.main()
