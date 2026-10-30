"""L-J3: JVM adapter — parser, mapping, commands, results, E2E.

Every fixture under tests/fixtures/traces/{java,kotlin}/ is real JVM
output (proof-app triggers in the sandbox image, or scratch programs run
with `java` there). The Docker E2E tests run the full pipeline with a
mocked GitHub + mocked models against the real `jvm` image.
"""

import os
import unittest
from unittest import mock

from core.ingest.traceback import Frame
from core.repo_fix import locate as repo_locate
from core.repo_fix.lang import by_name, parse
from core.repo_fix.lang.java import ADAPTER

JAVA_DIR = "tests/fixtures/traces/java"
KOTLIN_DIR = "tests/fixtures/traces/kotlin"


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class AdapterPresenceTest(unittest.TestCase):
    def test_registry_knows_java_and_kotlin(self):
        self.assertIs(by_name("java"), ADAPTER)
        self.assertIs(by_name("kotlin"), ADAPTER)  # alias, one object

    def test_timeouts(self):
        self.assertEqual(
            (ADAPTER.install_timeout_s, ADAPTER.suite_timeout_s), (900, 900)
        )

    def test_image(self):
        self.assertEqual(ADAPTER.image, "jvm")


class TraceStartTest(unittest.TestCase):
    def test_thread_head_starts(self):
        self.assertTrue(ADAPTER.trace_start(
            'Exception in thread "main" java.lang.X: boom'
        ))
        self.assertTrue(ADAPTER.trace_start(
            'Exception in thread "pool-1-thread-1" java.lang.X: boom'
        ))

    def test_bare_head_starts(self):
        self.assertTrue(ADAPTER.trace_start(
            "java.lang.ArithmeticException: / by zero"
        ))
        self.assertTrue(ADAPTER.trace_start("com.acme.E"))

    def test_continuations_do_not_start(self):
        self.assertFalse(ADAPTER.trace_start(
            "\tat com.acme.C.m(C.java:1)"
        ))
        self.assertFalse(ADAPTER.trace_start("Caused by: java.lang.X: y"))
        self.assertFalse(ADAPTER.trace_start("... 2 more"))
        self.assertFalse(ADAPTER.trace_start("INFO shop started"))

    def test_bare_single_words_do_not_start(self):
        self.assertFalse(ADAPTER.trace_start("more"))
        self.assertFalse(ADAPTER.trace_start("done"))
        self.assertFalse(ADAPTER.trace_start("notes: blah"))
        self.assertFalse(ADAPTER.trace_start("Error: blah"))
        self.assertTrue(ADAPTER.trace_start(
            'Exception in thread "main" MyError: blah'
        ))

    def test_continues(self):
        self.assertTrue(ADAPTER.trace_continues(
            "\tat com.acme.C.m(C.java:1)"
        ))
        self.assertTrue(ADAPTER.trace_continues("Caused by: java.lang.X"))
        self.assertTrue(ADAPTER.trace_continues("Suppressed: java.lang.Y"))
        self.assertTrue(ADAPTER.trace_continues("... 2 more"))
        self.assertFalse(ADAPTER.trace_continues(
            "java.lang.X: boom"
        ))
        self.assertFalse(ADAPTER.trace_continues("INFO done"))


class ParseJavaTracesTest(unittest.TestCase):
    def _parse(self, name):
        found = parse(_read(os.path.join(JAVA_DIR, name)))
        self.assertIsNotNone(found, name)
        adapter, info = found
        self.assertIs(adapter, ADAPTER, name)
        return info

    def test_proof_app_checkout(self):
        info = self._parse("proof-app-checkout.txt")
        self.assertEqual(info.language, "java")
        self.assertEqual(info.exc_type, "java.lang.ArithmeticException")
        self.assertEqual(info.exc_value, "/ by zero")
        self.assertEqual(len(info.frames), 12)
        self.assertEqual(info.frames[0].file, "Cart.java")
        self.assertEqual(info.frames[0].line, 58)
        self.assertEqual(
            info.frames[0].func, "com.example.shop.Cart.summary"
        )

    def test_direct_call(self):
        info = self._parse("direct-call.txt")
        self.assertEqual(info.language, "java")
        self.assertEqual(info.exc_type, "java.lang.ArithmeticException")
        self.assertEqual(len(info.frames), 2)
        self.assertEqual(info.frames[1].func, "DirectJava.main")

    def test_uncaught_main(self):
        info = self._parse("uncaught-main.txt")
        self.assertEqual(info.exc_type, "java.lang.IllegalStateException")
        self.assertEqual(info.exc_value, "boom from main")
        self.assertEqual(len(info.frames), 1)

    def test_caused_by_chain_root_cause_wins(self):
        info = self._parse("caused-by-chain.txt")
        self.assertEqual(info.exc_type, "java.lang.IllegalArgumentException")
        self.assertEqual(info.exc_value, "bad value 42")
        # Outer + both causes, elisions skipped: 1 + 3 + 2.
        self.assertEqual(len(info.frames), 6)

    def test_npe_helpful_message(self):
        info = self._parse("npe-helpful.txt")
        self.assertEqual(info.exc_type, "java.lang.NullPointerException")
        self.assertIn("String.trim()", info.exc_value)
        self.assertEqual(len(info.frames), 2)

    def test_thread_pool(self):
        info = self._parse("thread-pool.txt")
        self.assertEqual(info.exc_type, "java.lang.IllegalStateException")
        self.assertEqual(len(info.frames), 4)
        self.assertIn("lambda$main$0", info.frames[0].func)


class ParseKotlinTracesTest(unittest.TestCase):
    def _parse(self, name):
        found = parse(_read(os.path.join(KOTLIN_DIR, name)))
        self.assertIsNotNone(found, name)
        adapter, info = found
        self.assertIs(adapter, ADAPTER, name)
        return info

    def test_proof_app_checkout(self):
        info = self._parse("proof-app-checkout.txt")
        self.assertEqual(info.language, "kotlin")
        self.assertEqual(info.exc_type, "java.lang.ArithmeticException")
        self.assertEqual(info.frames[0].file, "Cart.kt")
        self.assertEqual(info.frames[0].line, 48)

    def test_direct_call(self):
        info = self._parse("direct-call.txt")
        self.assertEqual(info.language, "kotlin")
        self.assertEqual(len(info.frames), 2)

    def test_kotlin_exception_sniffs_kotlin(self):
        info = ADAPTER.parse_trace(
            "kotlin.UninitializedPropertyAccessException: lateinit x\n"
            "\tat com.acme.App.get(App.kt:10)\n"
        )
        self.assertIsNotNone(info)
        self.assertEqual(info.language, "kotlin")


class ParseRejectsTest(unittest.TestCase):
    def test_python_trace_rejected(self):
        with open("tests/fixtures/traces/python/real-traceback.txt") as handle:
            self.assertIsNone(ADAPTER.parse_trace(handle.read()))

    def test_frameless_rejected(self):
        self.assertIsNone(ADAPTER.parse_trace(
            "java.lang.X: boom\n"
        ))

    def test_trailing_junk_rejected(self):
        self.assertIsNone(ADAPTER.parse_trace(
            "java.lang.X: boom\n"
            "\tat com.acme.C.m(C.java:1)\n"
            "INFO next request\n"
        ))

    def test_native_and_unknown_frames_kept_unmappable(self):
        info = ADAPTER.parse_trace(
            "java.lang.X: boom\n"
            "\tat com.acme.C.m(Native Method)\n"
            "\tat com.acme.D.n(Unknown Source)\n"
            "\tat com.acme.E.o(E.java:3)\n"
        )
        self.assertIsNotNone(info)
        self.assertEqual(len(info.frames), 3)
        self.assertEqual(info.frames[0].file, "")


class MapFrameTest(unittest.TestCase):
    PATHS = [
        "pom.xml",
        "src/main/java/com/example/shop/Cart.java",
        "src/main/java/com/example/shop/ShopServer.java",
        "src/test/java/com/example/shop/CartTest.java",
    ]

    def test_proof_app_frame(self):
        self.assertEqual(
            ADAPTER.map_frame(
                "Cart.java", "com.example.shop.Cart.summary", self.PATHS
            ),
            "src/main/java/com/example/shop/Cart.java",
        )

    def test_kotlin_frame(self):
        paths = [
            "pom.xml",
            "src/main/kotlin/com/example/shop/Cart.kt",
        ]
        self.assertEqual(
            ADAPTER.map_frame(
                "Cart.kt", "com.example.shop.Cart.summary", paths
            ),
            "src/main/kotlin/com/example/shop/Cart.kt",
        )

    def test_multi_module(self):
        paths = ["shop-api/src/main/java/com/acme/Foo.java"]
        self.assertEqual(
            ADAPTER.map_frame("Foo.java", "com.acme.Foo.bar", paths),
            "shop-api/src/main/java/com/acme/Foo.java",
        )

    def test_inner_class_uses_paren_file(self):
        paths = ["src/main/java/com/sun/Filter.java"]
        self.assertEqual(
            ADAPTER.map_frame(
                "Filter.java",
                "com.sun.Filter$Chain.doFilter", paths,
            ),
            "src/main/java/com/sun/Filter.java",
        )

    def test_jdk_frame_unmappable(self):
        self.assertIsNone(ADAPTER.map_frame(
            "Thread.java", "java.lang.Thread.run", self.PATHS
        ))

    def test_native_frame_unmappable(self):
        self.assertIsNone(ADAPTER.map_frame("", "com.acme.C.m", self.PATHS))

    def test_default_package(self):
        self.assertEqual(
            ADAPTER.map_frame("Top.java", "Top.main", ["Top.java"]),
            "Top.java",
        )

    def test_locate_integration(self):
        frames = [
            Frame("Cart.java", 58, "com.example.shop.Cart.summary"),
            Frame("Thread.java", 1583, "java.lang.Thread.run"),
        ]
        located = repo_locate.match_frames(
            frames, self.PATHS, ADAPTER.map_frame
        )
        self.assertEqual(len(located), 1)
        self.assertEqual(
            located[0]["path"], "src/main/java/com/example/shop/Cart.java"
        )


class DetectTest(unittest.TestCase):
    def test_maven_scores(self):
        self.assertGreater(
            ADAPTER.detect(MapFrameTest.PATHS), 10
        )

    def test_gradle_scores(self):
        self.assertGreater(
            ADAPTER.detect(["build.gradle", "src/main/java/A.java"]), 10
        )

    def test_kotlin_scores(self):
        self.assertGreater(
            ADAPTER.detect(["pom.xml", "src/main/kotlin/A.kt"]), 10
        )

    def test_bare_sources_score_weakly(self):
        self.assertEqual(ADAPTER.detect(["A.java"]), 1)

    def test_foreign_repo_zero(self):
        self.assertEqual(ADAPTER.detect(["go.mod", "main.go"]), 0)
        self.assertEqual(ADAPTER.detect(["a.py", "requirements.txt"]), 0)
        self.assertEqual(ADAPTER.detect([]), 0)

    def test_source_files(self):
        self.assertEqual(
            ADAPTER.source_files(["A.java", "B.kt", "c.py", "pom.xml"]),
            ["A.java", "B.kt"],
        )


class CommandsTest(unittest.TestCase):
    MAVEN = ["pom.xml", "src/main/java/A.java"]
    GRADLE_WRAPPED = ["build.gradle", "gradlew", "src/main/java/A.java"]
    GRADLE_BARE = ["build.gradle.kts", "src/main/java/A.java"]

    def test_maven_install_prefetches(self):
        # Full online run, failures ignored (surefire providers cached).
        self.assertEqual(
            ADAPTER.install_cmds(self.MAVEN),
            [["mvn", "-B", "-q", "-Dmaven.test.failure.ignore=true", "test"]],
        )

    def test_gradle_install(self):
        self.assertEqual(
            ADAPTER.install_cmds(self.GRADLE_WRAPPED),
            [["./gradlew", "--no-daemon", "testClasses"]],
        )
        self.assertEqual(
            ADAPTER.install_cmds(self.GRADLE_BARE),
            [["gradle", "--no-daemon", "testClasses"]],
        )

    def test_no_build_file_no_install(self):
        self.assertEqual(ADAPTER.install_cmds(["A.java"]), [])

    def test_maven_suite_offline(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.MAVEN), ["mvn", "-B", "-o", "test"]
        )

    def test_gradle_suite_offline(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.GRADLE_WRAPPED),
            ["./gradlew", "--no-daemon", "--offline", "test"],
        )

    def test_maven_single_test(self):
        self.assertEqual(
            ADAPTER.single_test_cmd(
                "src/test/java/com/acme/TaReproAbcTest.java", self.MAVEN
            ),
            ["mvn", "-B", "-o", "-Dtest=TaReproAbcTest", "test"],
        )

    def test_gradle_single_test(self):
        self.assertEqual(
            ADAPTER.single_test_cmd(
                "src/test/java/com/acme/TaReproAbcTest.java",
                self.GRADLE_WRAPPED,
            ),
            ["./gradlew", "--no-daemon", "--offline",
             "--tests", "*TaReproAbcTest", "test"],
        )

    def test_kotlin_single_test_strips_kt(self):
        self.assertEqual(
            ADAPTER.single_test_cmd(
                "src/test/kotlin/com/acme/TaReproAbcTest.kt", self.MAVEN
            ),
            ["mvn", "-B", "-o", "-Dtest=TaReproAbcTest", "test"],
        )


SUREFIRE_XML = """<?xml version="1.0"?>
<testsuite name="com.acme.FooTest" tests="2" failures="1" errors="0" skipped="0">
  <testcase classname="com.acme.FooTest" name="ok"/>
  <testcase classname="com.acme.FooTest" name="bad">
    <failure message="nope">trace</failure>
  </testcase>
</testsuite>"""

MAVEN_OUT = """Running com.acme.FooTest
Tests run: 2, Failures: 1, Errors: 0, Skipped: 0, Time elapsed: 0.1 s
[ERROR] Failures:
[ERROR]   com.acme.FooTest.bad:12 nope
[ERROR] Tests run: 2, Failures: 1, Errors: 0, Skipped: 0
"""

GRADLE_OUT = """CartTest > emptyCart FAILED
  org.opentest4j.AssertionFailedError at CartTest.kt:9
20 tests completed, 1 failed
> Task :test FAILED
"""


class ParseResultsTest(unittest.TestCase):
    def test_maven_xml_reports(self):
        result = ADAPTER.parse_results(
            "Running com.acme.FooTest\nTests run: 2, Failures: 1\n",
            "", lambda path: SUREFIRE_XML,
        )
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(result.failed_ids, ["com.acme.FooTest.bad"])
        self.assertFalse(result.errored)

    def test_maven_stdout_fallback(self):
        result = ADAPTER.parse_results(MAVEN_OUT, "", lambda path: None)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertIn("com.acme.FooTest.bad", result.failed_ids)
        self.assertFalse(result.errored)

    def test_maven_empty_errors(self):
        result = ADAPTER.parse_results(
            "BUILD FAILURE\n", "COMPILATION ERROR\n", lambda path: None
        )
        self.assertTrue(result.errored)

    def test_gradle_results(self):
        result = ADAPTER.parse_results(GRADLE_OUT, "", lambda path: None)
        self.assertEqual((result.total, result.passed, result.failed), (20, 19, 1))
        self.assertEqual(result.failed_ids, ["CartTest.emptyCart"])
        self.assertFalse(result.errored)

    def test_gradle_empty_errors(self):
        self.assertTrue(
            ADAPTER.parse_results("nope\n", "", lambda path: None).errored
        )


class ReproTest(unittest.TestCase):
    PATHS = MapFrameTest.PATHS

    def test_java_repro_path(self):
        self.assertEqual(
            ADAPTER.repro_test_path(
                "ab" * 20, self.PATHS,
                ["src/main/java/com/example/shop/Cart.java"],
            ),
            "src/test/java/com/example/shop/"
            "TaReproababababababTest.java",
        )

    def test_kotlin_repro_path(self):
        paths = ["pom.xml", "src/main/kotlin/com/acme/A.kt"]
        self.assertEqual(
            ADAPTER.repro_test_path(
                "ab" * 20, paths, ["src/main/kotlin/com/acme/A.kt"]
            ),
            "src/test/kotlin/com/acme/TaReproababababababTest.kt",
        )

    def test_empty_context_falls_back(self):
        self.assertEqual(
            ADAPTER.repro_test_path("ab" * 20, [], []),
            "src/test/java/TaReproababababababTest.java",
        )

    def test_rules_and_check(self):
        self.assertIn("JUnit", ADAPTER.repro_rules())
        self.assertIn("@Test", ADAPTER.repro_rules())
        self.assertTrue(ADAPTER.looks_like_test("@Test\nvoid x() {}"))
        self.assertFalse(ADAPTER.looks_like_test("class X {}"))


if __name__ == "__main__":
    unittest.main()
