"""L-D3: PHP adapter — parsers, commands, results (real fixtures)."""

import unittest
from pathlib import Path

from core.repo_fix.lang.php import ADAPTER

TRACES = Path(__file__).resolve().parent / "fixtures" / "traces" / "php"


def trace(name):
    return (TRACES / name).read_text(encoding="utf-8")


def info(name):
    parsed = ADAPTER.parse_trace(trace(name))
    assert parsed is not None, name
    return parsed


# Verbatim excerpts of `vendor/bin/phpunit --log-junit ta-results.xml` on
# examples/proof-app-php (pass; one erroring repro test) and of
# `vendor/bin/pest --log-junit ta-results.xml` on a Pest copy of it.
PHPUNIT_PASS = """....................                                              20 / 20 (100%)

Time: 00:00.005, Memory: 8.00 MB

OK (20 tests, 31 assertions)
"""

PHPUNIT_FAIL = """....................E.                                            22 / 22 (100%)

Time: 00:00.008, Memory: 8.00 MB

There was 1 error:

1) ProofShop\\Tests\\TaReproAbc123Test::testEmptyCartAverageIsZero
DivisionByZeroError: Division by zero

/private/tmp/php-out/src/Cart.php:62
/private/tmp/php-out/tests/TaReproAbc123Test.php:14

ERRORS!
Tests: 22, Assertions: 32, Errors: 1.
"""

# Real PHPUnit nesting (config > suite > class), verbatim attributes;
# the passing ShopTest class is elided, so the leaf holds 2 tests.
PHPUNIT_JUNIT_FAIL = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="/private/tmp/php-out/phpunit.xml" tests="22" assertions="32" errors="1" failures="0" skipped="0" time="0.005">
    <testsuite name="shop" tests="22" assertions="32" errors="1" failures="0" skipped="0" time="0.005">
      <testsuite name="ProofShop\\Tests\\TaReproAbc123Test" file="/private/tmp/php-out/tests/TaReproAbc123Test.php" tests="2" assertions="1" errors="1" failures="0" skipped="0" time="0.005279">
        <testcase name="testEmptyCartAverageIsZero" file="/private/tmp/php-out/tests/TaReproAbc123Test.php" line="12" class="ProofShop\\Tests\\TaReproAbc123Test" classname="ProofShop.Tests.TaReproAbc123Test" assertions="0" time="0.005223">
          <error type="DivisionByZeroError">ProofShop\\Tests\\TaReproAbc123Test::testEmptyCartAverageIsZero
DivisionByZeroError: Division by zero
</error>
        </testcase>
        <testcase name="testNonemptyCartStillTotals" file="/private/tmp/php-out/tests/TaReproAbc123Test.php" line="18" class="ProofShop\\Tests\\TaReproAbc123Test" classname="ProofShop.Tests.TaReproAbc123Test" assertions="1" time="0.0001"/>
      </testsuite>
    </testsuite>
  </testsuite>
</testsuites>
"""

PEST_FAIL = """
   FAIL  Tests\\CartPestTest
  ✓ line total multiplies
  ⨯ empty cart average is zero

   FAILED  Tests\\CartPestTest > empty cart average is z…  DivisionByZeroError
  Division by zero

  at src/Cart.php:62

  Tests:    1 failed, 21 passed (32 assertions)
  Duration: 0.07s
"""


class TraceStartTest(unittest.TestCase):
    def test_heads(self):
        for line in (
            "PHP Fatal error:  Uncaught DivisionByZeroError: Division by zero in /app/src/Cart.php:62",
            "PHP Fatal error:  Uncaught TypeError: count(): Argument #1 ($value) must be of type Countable|array, null given in /var/www/html/app/Cart.php:12",
            "Fatal error: Uncaught Error: Call to undefined function foo() in /app/x.php:2",
            "PHP Parse error:  syntax error, unexpected token in /app/x.php on line 5",
            "PHP Catchable fatal error:  Object of class stdClass could not be converted to string in /app/x.php:3",
            "[Fri Oct 30 14:12:35 2026] PHP Fatal error:  Uncaught DivisionByZeroError: Division by zero in /app/src/Cart.php:62",
            '[2026-10-30T13:14:24.351847+00:00] proof-shop.ERROR: checkout failed {"cart":[],"exception":"[object] (DivisionByZeroError(code: 0): Division by zero at /app/mono.php:11)',
            '[2026-10-30 13:15:37] laravel.EMERGENCY: Unable to create configured logger. {"exception":"[object] (Illuminate\\\\Contracts\\\\Container\\\\BindingResolutionException(code: 0): Target x is not instantiable. at /app/vendor/illuminate/container/Container.php:1444)',
        ):
            self.assertTrue(ADAPTER.trace_start(line), line[:60])

    def test_not_heads(self):
        for line in (
            "",
            "Stack trace:",
            "#0 /app/src/Cart.php(62): intdiv(0, 0)",
            "#1 {main}",
            "  thrown in /app/src/Cart.php on line 62",
            "[stacktrace]",
            "Next RuntimeException: outer in /app/x.php:9",
            'PHP Warning:  Attempt to read property "currency" on null in /app/x.php on line 2',
            "PHP Deprecated:  strlen(): Passing null is deprecated in /app/x.php:1",
            "Traceback (most recent call last):",
            "TypeError: js boom",
            "panic: runtime error: integer divide by zero",
            "thread 'main' panicked at src/main.rs:4:5:",
            "FATAL ERROR: Reached heap limit Allocation failed",
        ):
            self.assertFalse(ADAPTER.trace_start(line), line[:60])


class TraceContinuesTest(unittest.TestCase):
    def test_continues(self):
        for line in (
            "Stack trace:",
            "#0 /app/src/Cart.php(62): intdiv(0, 0)",
            "#1 /app/src/Shop.php(28): ProofShop\\Cart::summary(Array)",
            "#2 {main}",
            "  thrown in /app/src/Cart.php on line 62",
            "Next RuntimeException: checkout totals unavailable in /app/x.php:12",
            "[stacktrace]",
            "[Fri Oct 30 14:12:35 2026] #0 /app/src/Cart.php(62): intdiv(0, 0)",
        ):
            self.assertTrue(ADAPTER.trace_continues(line), line[:60])

    def test_ends(self):
        for line in (
            "",
            "PHP Fatal error:  Uncaught Error: x in /app/x.php:1",
            "Fatal error: Uncaught Error: x in /app/x.php:1",
            "[2026-10-30] proof-shop.ERROR: checkout failed {\"exception\":\"[object] (E(code: 0): m at /app/x.php:1)",
            '"} ',
            "[Fri Oct 30 13:49:01 2026] 127.0.0.1:52369 Closing",
            "INFO request done",
        ):
            self.assertFalse(ADAPTER.trace_continues(line), line[:60])


class ParseTraceTest(unittest.TestCase):
    def test_proofshop_division_by_zero(self):
        parsed = info("proofshop_division_by_zero.txt")
        self.assertEqual(parsed.language, "php")
        self.assertEqual(parsed.exc_type, "DivisionByZeroError")
        self.assertEqual(parsed.exc_value, "Division by zero")
        self.assertTrue(parsed.frames[0].file.endswith("src/Cart.php"))
        self.assertEqual(parsed.frames[0].line, 62)
        self.assertIn("intdiv", parsed.frames[0].func)
        self.assertTrue(
            any(frame.file.endswith("src/Shop.php") for frame in parsed.frames)
        )

    def test_typeerror(self):
        parsed = info("typeerror.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertIn("must be of type array", parsed.exc_value)
        self.assertTrue(parsed.frames[0].file.endswith("typeerror.php"))
        self.assertEqual(parsed.frames[0].line, 2)

    def test_undefined_function(self):
        parsed = info("undefined_function.txt")
        self.assertEqual(parsed.exc_type, "Error")
        self.assertIn("apply_promo", parsed.exc_value)

    def test_value_error(self):
        parsed = info("value_error.txt")
        self.assertEqual(parsed.exc_type, "ValueError")
        self.assertIn("random_int", parsed.exc_value)

    def test_class_not_found(self):
        parsed = info("class_not_found.txt")
        self.assertEqual(parsed.exc_type, "Error")
        self.assertIn("CartService", parsed.exc_value)

    def test_warning_then_fatal(self):
        # A Warning precedes the fatal: the fatal still wins.
        parsed = info("method_on_null.txt")
        self.assertEqual(parsed.exc_type, "TypeError")
        self.assertEqual(len(parsed.frames), 2)  # head + #0 ({main} skipped)

    def test_chained_first_wins(self):
        # PHP prints the root cause first, then `Next <outer>`: the
        # first block (like Java's root-cause-wins) is the exception.
        parsed = info("chained_next.txt")
        self.assertEqual(parsed.exc_type, "InvalidArgumentException")
        self.assertEqual(parsed.exc_value, "currency code is empty")
        self.assertEqual(parsed.frames[0].line, 4)

    def test_monolog_stacktrace(self):
        parsed = info("monolog_stacktrace.txt")
        self.assertEqual(parsed.exc_type, "DivisionByZeroError")
        self.assertEqual(parsed.exc_value, "Division by zero")
        self.assertEqual(parsed.frames[0].file, "/app/mono.php")
        self.assertEqual(parsed.frames[0].line, 11)
        self.assertTrue(
            any("charge" in frame.func for frame in parsed.frames)
        )

    def test_laravel_log_first_entry_wins(self):
        parsed = info("laravel_emergency_log.txt")
        self.assertEqual(
            parsed.exc_type,
            "Illuminate\\Contracts\\Container\\BindingResolutionException",
        )
        self.assertIn("ContextLogProcessor", parsed.exc_value)
        # Frames stop at the next log entry's head (no cross-entry glue).
        self.assertTrue(
            all("laravel4.php" not in frame.file for frame in parsed.frames)
        )

    def test_rejects_foreign_traces(self):
        for snippet in (
            'Traceback (most recent call last):\n  File "/a/b.py", line 1, in f\nValueError: x\n',
            "TypeError: boom\n    at f (/app/x.js:1:1)\n",
            "panic: boom\ngoroutine 1 [running]:\n",
            "thread 'main' panicked at src/main.rs:4:5:\nboom\n",
            "java.lang.ArithmeticException: / by zero\n\tat com.Foo.bar(Foo.java:1)\n",
            "INFO all good\nlistening on :8080\n",
        ):
            self.assertIsNone(ADAPTER.parse_trace(snippet), snippet[:40])


class MapFrameTest(unittest.TestCase):
    PATHS = [
        "composer.json",
        "public/index.php",
        "src/Cart.php",
        "src/Shop.php",
        "tests/ShopTest.php",
    ]

    def test_suffix(self):
        self.assertEqual(
            ADAPTER.map_frame(
                "/var/www/html/src/Cart.php", "ProofShop\\Cart::summary", self.PATHS
            ),
            "src/Cart.php",
        )
        self.assertEqual(
            ADAPTER.map_frame("/app/tests/ShopTest.php", "ShopTest::x", self.PATHS),
            "tests/ShopTest.php",
        )

    def test_vendor_never_maps(self):
        paths = self.PATHS + ["vendor/monolog/monolog/src/Logger.php"]
        self.assertIsNone(
            ADAPTER.map_frame(
                "/app/vendor/monolog/monolog/src/Logger.php",
                "Monolog\\Logger::error",
                paths,
            )
        )

    def test_miss(self):
        self.assertIsNone(
            ADAPTER.map_frame("/app/src/Missing.php", "f", self.PATHS)
        )


class DetectTest(unittest.TestCase):
    def test_scores(self):
        self.assertEqual(
            ADAPTER.detect(["composer.json", "src/A.php", "src/B.php"]), 2 + 5
        )
        self.assertEqual(ADAPTER.detect(["src/A.php"]), 1)
        self.assertEqual(ADAPTER.detect(["package.json", "x.js"]), 0)

    def test_source_files_skip_vendor(self):
        self.assertEqual(
            ADAPTER.source_files(
                ["src/A.php", "vendor/pkg/f.php", "lib/vendor/g.php", "x.js"]
            ),
            ["src/A.php"],
        )


class CommandsTest(unittest.TestCase):
    PATHS = ["composer.json", "phpunit.xml", "src/Cart.php", "tests/ShopTest.php"]
    PEST = PATHS + ["tests/Pest.php"]

    def test_install(self):
        self.assertEqual(
            ADAPTER.install_cmds(self.PATHS),
            [["composer", "install", "--no-interaction", "--no-progress"]],
        )
        self.assertEqual(ADAPTER.install_cmds(["src/A.php"]), [])

    def test_suite_phpunit(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.PATHS),
            ["vendor/bin/phpunit", "--log-junit", "ta-results.xml"],
        )

    def test_suite_pest(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.PEST),
            ["vendor/bin/pest", "--log-junit", "ta-results.xml"],
        )

    def test_single(self):
        self.assertEqual(
            ADAPTER.single_test_cmd("tests/TaReproAbc123Test.php", self.PATHS),
            ["vendor/bin/phpunit", "tests/TaReproAbc123Test.php"],
        )
        self.assertEqual(
            ADAPTER.single_test_cmd("tests/TaReproAbc123Test.php", self.PEST),
            ["vendor/bin/pest", "tests/TaReproAbc123Test.php"],
        )

    def test_timeouts_and_image(self):
        self.assertEqual((ADAPTER.name, ADAPTER.image), ("php", "php"))
        self.assertEqual(
            (ADAPTER.install_timeout_s, ADAPTER.suite_timeout_s), (300, 600)
        )


class ParseResultsTest(unittest.TestCase):
    def test_junit_primary(self):
        result = ADAPTER.parse_results(
            "", "", lambda path: PHPUNIT_JUNIT_FAIL if path == "ta-results.xml" else None
        )
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(
            result.failed_ids,
            ["ProofShop.Tests.TaReproAbc123Test.testEmptyCartAverageIsZero"],
        )

    def test_stdout_pass_fallback(self):
        result = ADAPTER.parse_results(
            PHPUNIT_PASS, "", lambda _path: None
        )
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (20, 20, 0))
        self.assertEqual(result.failed_ids, [])

    def test_stdout_fail_fallback(self):
        result = ADAPTER.parse_results(
            PHPUNIT_FAIL, "", lambda _path: None
        )
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (22, 21, 1))
        self.assertEqual(
            result.failed_ids,
            ["ProofShop\\Tests\\TaReproAbc123Test::testEmptyCartAverageIsZero"],
        )

    def test_pest_stdout_fallback(self):
        result = ADAPTER.parse_results(PEST_FAIL, "", lambda _path: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (22, 21, 1))
        self.assertEqual(
            result.failed_ids, ["Tests\\CartPestTest > empty cart average is z…"]
        )

    def test_garbage(self):
        result = ADAPTER.parse_results(
            "something broke horribly\n", "", lambda _path: None
        )
        self.assertTrue(result.errored)
        self.assertEqual(result.total, 0)


class ReproTest(unittest.TestCase):
    PATHS = ["composer.json", "src/Cart.php", "tests/ShopTest.php"]

    def test_path(self):
        self.assertEqual(
            ADAPTER.repro_test_path("abc123def456789", self.PATHS, ["src/Cart.php"]),
            "tests/TaReproabc123def456Test.php",
        )

    def test_rules_and_check(self):
        rules = ADAPTER.repro_rules()
        self.assertIn("TestCase", rules)
        self.assertIn("Pest", rules)
        self.assertTrue(
            ADAPTER.looks_like_test(
                "final class T extends TestCase {\n"
                "public function testX(): void {}\n}"
            )
        )
        self.assertTrue(
            ADAPTER.looks_like_test(
                "test('empty cart', function () {\n"
                "expect(Cart::summary([]))->toBe(0.0);\n});"
            )
        )
        self.assertFalse(ADAPTER.looks_like_test("function helper() {}"))
        self.assertFalse(
            ADAPTER.looks_like_test("$cart->test(); // not a test file")
        )


if __name__ == "__main__":
    unittest.main()
