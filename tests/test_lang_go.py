"""L-J4: Go adapter — panic parser, mapping, commands, results.

Every fixture under tests/fixtures/traces/go/ is real `go` output (the
proof-app trigger in the sandbox image, or scratch programs run with
`go run` / `go test` there). The Docker E2E proof runs live at merge
time (see status); Jude's L-D4 harness owns the committed matrix.
"""

import os
import unittest

from core.ingest import pipeline as ingest_pipeline
from core.repo_fix.lang import by_name, parse
from core.repo_fix.lang.go import ADAPTER

GO_DIR = "tests/fixtures/traces/go"


def _read(name):
    with open(os.path.join(GO_DIR, name), encoding="utf-8") as handle:
        return handle.read()


class AdapterPresenceTest(unittest.TestCase):
    def test_registry_knows_go(self):
        self.assertIs(by_name("go"), ADAPTER)

    def test_timeouts_and_image(self):
        self.assertEqual(
            (ADAPTER.install_timeout_s, ADAPTER.suite_timeout_s), (300, 600)
        )
        self.assertEqual(ADAPTER.image, "go")


class TraceStartTest(unittest.TestCase):
    def test_panic_starts(self):
        self.assertTrue(ADAPTER.trace_start("panic: boom"))
        self.assertTrue(ADAPTER.trace_start(
            "panic: runtime error: integer divide by zero"
        ))

    def test_timestamped_panic_starts(self):
        self.assertTrue(ADAPTER.trace_start(
            "2026/10/30 15:21:19 panic: runtime error: x"
        ))

    def test_recovered_panic_starts(self):
        self.assertTrue(ADAPTER.trace_start("panic: test blew up [recovered]"))

    def test_other_lines_do_not_start(self):
        self.assertFalse(ADAPTER.trace_start("goroutine 1 [running]:"))
        self.assertFalse(ADAPTER.trace_start("main.main()"))
        self.assertFalse(ADAPTER.trace_start("\t/app/x.go:1 +0x2"))
        self.assertFalse(ADAPTER.trace_start("created by main.main"))
        self.assertFalse(ADAPTER.trace_start("exit status 2"))
        self.assertFalse(ADAPTER.trace_start("--- FAIL: TestX (0.00s)"))
        self.assertFalse(ADAPTER.trace_start(
            "Traceback (most recent call last):"
        ))
        self.assertFalse(ADAPTER.trace_start(
            "java.lang.X: boom"
        ))

    def test_continues(self):
        self.assertTrue(ADAPTER.trace_continues(""))
        self.assertTrue(ADAPTER.trace_continues("goroutine 19 [running]:"))
        self.assertTrue(ADAPTER.trace_continues("main.main()"))
        self.assertTrue(ADAPTER.trace_continues(
            "proofshop/shop.Summarize({0x1, 0x2})"
        ))
        self.assertTrue(ADAPTER.trace_continues("\t/app/shop/cart.go:70 +0x1b8"))
        self.assertTrue(ADAPTER.trace_continues("\t/s/x.go:3"))
        self.assertTrue(ADAPTER.trace_continues(
            "created by main.main in goroutine 1"
        ))
        self.assertFalse(ADAPTER.trace_continues("panic: boom"))
        self.assertFalse(ADAPTER.trace_continues("exit status 2"))
        self.assertFalse(ADAPTER.trace_continues("FAIL\tpkg\t0.1s"))
        self.assertFalse(ADAPTER.trace_continues("--- FAIL: T (0.00s)"))


class ParseGoTracesTest(unittest.TestCase):
    def _parse(self, name):
        found = parse(_read(name))
        self.assertIsNotNone(found, name)
        adapter, info = found
        self.assertIs(adapter, ADAPTER, name)
        self.assertEqual(info.language, "go", name)
        return info

    def test_proof_app_checkout(self):
        info = self._parse("proof-app-checkout.txt")
        self.assertEqual(info.exc_type, "panic")
        self.assertIn("integer divide by zero", info.exc_value)
        self.assertGreater(len(info.frames), 5)
        shop = [f for f in info.frames if f.file == "/app/shop/cart.go"]
        self.assertEqual(len(shop), 1)
        self.assertEqual(shop[0].line, 70)
        self.assertIn("Summarize", shop[0].func)

    def test_unrecovered_panic(self):
        info = self._parse("unrecovered-panic.txt")
        self.assertEqual(info.exc_value, "boom from lib")
        self.assertEqual(len(info.frames), 2)
        self.assertEqual(info.frames[0].func, "proofshop-go/scratchlib.Boom(...)")

    def test_nil_pointer(self):
        info = self._parse("nil-pointer.txt")
        self.assertIn("nil pointer dereference", info.exc_value)
        self.assertEqual(len(info.frames), 1)
        self.assertEqual(info.frames[0].file, "/s/nilptr.go")

    def test_goroutines_created_by_bare(self):
        info = self._parse("goroutines.txt")
        self.assertEqual(info.exc_value, "worker blew up")
        self.assertEqual(len(info.frames), 2)
        self.assertEqual(info.frames[1].func, "")
        self.assertEqual(info.frames[1].file, "/s/goroutines.go")

    def test_index_range(self):
        info = self._parse("index-range.txt")
        self.assertIn("index out of range", info.exc_value)
        self.assertEqual(len(info.frames), 1)

    def test_test_fail_panic(self):
        info = self._parse("test-fail-panic.txt")
        self.assertEqual(info.exc_value, "test blew up")
        self.assertGreater(len(info.frames), 3)
        mine = [f for f in info.frames if f.file.endswith("fail_test.go")]
        self.assertEqual(len(mine), 1)


class ParseRejectsTest(unittest.TestCase):
    def test_python_trace_rejected(self):
        with open("tests/fixtures/traces/python/real-traceback.txt") as handle:
            self.assertIsNone(ADAPTER.parse_trace(handle.read()))

    def test_java_trace_rejected(self):
        with open("tests/fixtures/traces/java/direct-call.txt") as handle:
            self.assertIsNone(ADAPTER.parse_trace(handle.read()))

    def test_frameless_panic_rejected(self):
        self.assertIsNone(ADAPTER.parse_trace("panic: boom\n"))

    def test_trailing_junk_rejected(self):
        self.assertIsNone(ADAPTER.parse_trace(
            "panic: boom\n"
            "goroutine 1 [running]:\n"
            "main.main()\n"
            "\t/s/x.go:1 +0x2\n"
            "exit status 2\n"
        ))


class MapFrameTest(unittest.TestCase):
    PATHS = ["go.mod", "shop/cart.go", "shop/server.go", "cmd/proofshop/main.go"]

    def test_absolute_container_path(self):
        self.assertEqual(
            ADAPTER.map_frame(
                "/app/shop/cart.go", "proofshop/shop.Summarize", self.PATHS
            ),
            "shop/cart.go",
        )

    def test_module_prefix_stripped(self):
        paths = ["go.mod", "shop/cart.go"]
        self.assertEqual(
            ADAPTER.map_frame(
                "cart.go", "github.com/acme/app/shop.Summarize", paths
            ),
            "shop/cart.go",
        )

    def test_stdlib_unmappable(self):
        self.assertIsNone(ADAPTER.map_frame(
            "/usr/local/go/src/net/http/server.go:2747",
            "net/http.(*ServeMux).ServeHTTP", self.PATHS,
        ))


class DetectTest(unittest.TestCase):
    def test_go_mod_scores(self):
        self.assertGreater(
            ADAPTER.detect(["go.mod", "main.go"]), 10
        )

    def test_bare_sources_score_weakly(self):
        self.assertEqual(ADAPTER.detect(["main.go"]), 1)

    def test_foreign_repo_zero(self):
        self.assertEqual(ADAPTER.detect(["pom.xml", "A.java"]), 0)
        self.assertEqual(ADAPTER.detect(["a.py"]), 0)
        self.assertEqual(ADAPTER.detect([]), 0)

    def test_source_files(self):
        self.assertEqual(
            ADAPTER.source_files(["a.go", "b_test.go", "c.py"]),
            ["a.go", "b_test.go"],
        )


class CommandsTest(unittest.TestCase):
    PATHS = ["go.mod", "shop/cart.go"]

    def test_install_downloads(self):
        self.assertEqual(
            ADAPTER.install_cmds(self.PATHS), [["go", "mod", "download"]]
        )
        self.assertEqual(ADAPTER.install_cmds(["a.go"]), [])

    def test_suite_json(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.PATHS), ["go", "test", "./...", "-json"]
        )

    def test_single_test_subdir(self):
        self.assertEqual(
            ADAPTER.single_test_cmd("shop/ta_repro_abc_test.go", self.PATHS),
            ["go", "test", "./shop", "-run", "TestTaRepro", "-json"],
        )

    def test_single_test_root(self):
        self.assertEqual(
            ADAPTER.single_test_cmd("ta_repro_abc_test.go", self.PATHS),
            ["go", "test", ".", "-run", "TestTaRepro", "-json"],
        )


class ParseResultsTest(unittest.TestCase):
    def test_json_stream(self):
        out = (
            '{"Action":"run","Package":"shop","Test":"TestA"}\n'
            '{"Action":"pass","Package":"shop","Test":"TestA"}\n'
            '{"Action":"run","Package":"shop","Test":"TestTaRepro"}\n'
            '{"Action":"fail","Package":"shop","Test":"TestTaRepro"}\n'
            '{"Action":"fail","Package":"shop"}\n'
        )
        result = ADAPTER.parse_results(out, "", lambda path: None)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(result.failed_ids, ["shop.TestTaRepro"])
        self.assertFalse(result.errored)


class ReproTest(unittest.TestCase):
    def test_same_dir_as_located(self):
        self.assertEqual(
            ADAPTER.repro_test_path(
                "ab" * 20, ["go.mod"], ["shop/cart.go"]
            ),
            "shop/ta_repro_abababababab_test.go",
        )

    def test_root_fallback(self):
        self.assertEqual(
            ADAPTER.repro_test_path("ab" * 20, [], []),
            "ta_repro_abababababab_test.go",
        )

    def test_rules_and_check(self):
        self.assertIn("TestTaRepro", ADAPTER.repro_rules())
        self.assertIn("SAME package", ADAPTER.repro_rules())
        self.assertTrue(ADAPTER.looks_like_test(
            "func TestTaReproX(t *testing.T) {}"
        ))
        self.assertFalse(ADAPTER.looks_like_test("func TestX(t *testing.T) {}"))


class AssembleGoTest(unittest.TestCase):
    def test_proof_trace_assembles_with_orphan_trailer(self):
        ingest_pipeline.reset_assemblers()
        try:
            entries = ingest_pipeline.assemble(
                "ingest:t:api",
                _read("proof-app-checkout.txt").splitlines() + ["exit status 2"],
                0.0,
            )
        finally:
            ingest_pipeline.reset_assemblers()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].traceback.language, "go")
        self.assertTrue(entries[0].traceback.frames)
        self.assertEqual(entries[1].text, "exit status 2")
        self.assertIsNone(entries[1].traceback)


if __name__ == "__main__":
    unittest.main()
