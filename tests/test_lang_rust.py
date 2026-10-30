"""L-D2: Rust adapter — parsers, commands, results (real fixtures)."""

import unittest
from pathlib import Path

from core.repo_fix.lang.rust import ADAPTER

TRACES = Path(__file__).resolve().parent / "fixtures" / "traces" / "rust"


def trace(name):
    return (TRACES / name).read_text(encoding="utf-8")


def info(name):
    parsed = ADAPTER.parse_trace(trace(name))
    assert parsed is not None, name
    return parsed


# Verbatim excerpts of `cargo test --offline --no-fail-fast` on
# examples/proof-app-rust in rust:1-slim (pass; one failing repro test;
# lib compile error). Full outputs in /tmp/rust-out/*.txt (scratch).
PASS_RUN = """test cart::tests::summary_totals ... ok
test result: ok. 13 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

test checkout_ok ... ok
test result: ok. 8 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

running 0 tests

test result: ok. 0 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
"""

FAIL_RUN = """test empty_cart_average_is_zero ... FAILED

failures:

---- empty_cart_average_is_zero stdout ----

thread 'empty_cart_average_is_zero' (368) panicked at src/cart.rs:70:19:
attempt to divide by zero
note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace


failures:
    empty_cart_average_is_zero

test result: FAILED. 1 passed; 1 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s

error: test failed, to rerun pass `--test ta_repro_abc123`
"""

COMPILE_ERROR = """   Compiling proof-shop-rust v1.0.0 (/app)
error[E0308]: mismatched types
  --> src/cart.rs:71:23
   |
71 |     let broken: i64 = "nan";
   |                 ---   ^^^^^ expected `i64`, found `&str`
error: could not compile `proof-shop-rust` (lib test) due to 1 previous error
"""


class TraceStartTest(unittest.TestCase):
    def test_heads(self):
        for line in (
            "thread 'main' panicked at src/main.rs:4:5:",
            "thread 'main' (144) panicked at src/bin/div_zero.rs:1:43:",
            "thread 'proof-shop-worker' (164) panicked at src/cart.rs:70:19:",
            "thread 'empty_cart_average_is_zero' (368) panicked at src/cart.rs:70:19:",
            "thread 'main' panicked at 'boom', src/main.rs:4:5",
            "thread 'tokio-runtime-worker' (7) panicked at ' 풀 exhausted', src/pool.rs:9:3",
        ):
            self.assertTrue(ADAPTER.trace_start(line), line)

    def test_not_heads(self):
        for line in (
            "",
            "stack backtrace:",
            "   0: rust_begin_unwind",
            "             at ./src/panic.rs:10:5",
            "attempt to divide by zero",
            "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace",
            "Traceback (most recent call last):",
            "TypeError: js boom",
            "panic: runtime error: integer divide by zero",
            "PHP Fatal error:  Uncaught Error: x in /a/b.php:1",
            "java.lang.ArithmeticException: / by zero",
            "thread 'main' finished without panic",
        ):
            self.assertFalse(ADAPTER.trace_start(line), line)


class TraceContinuesTest(unittest.TestCase):
    def test_continues(self):
        for line in (
            "stack backtrace:",
            "   0: __rustc::rust_begin_unwind",
            "   3: proof_shop_rust::cart::summary",
            "             at ./src/cart.rs:70:19",
            "             at /rustc/58cf8f9c35b355199727627d07ae34a4e2846d67/library/std/src/panicking.rs:679:5",
            "note: Some details are omitted, run with `RUST_BACKTRACE=full` for a verbose backtrace.",
            "note: run with `RUST_BACKTRACE=1` environment variable to display a backtrace",
        ):
            self.assertTrue(ADAPTER.trace_continues(line), line)

    def test_ends(self):
        for line in (
            "",
            "thread 'main' panicked at src/main.rs:4:5:",
            "thread 'main' panicked at 'boom', src/main.rs:4:5",
            "attempt to divide by zero",
            "called `Option::unwrap()` on a `None` value",
            "proof-shop-rust listening on 0.0.0.0:8325",
            "INFO request done",
        ):
            self.assertFalse(ADAPTER.trace_continues(line), line)


class ParseTraceTest(unittest.TestCase):
    def test_proofshop_empty_cart(self):
        parsed = info("proofshop_empty_cart.txt")
        self.assertEqual(parsed.language, "rust")
        self.assertEqual(parsed.exc_type, "panic")
        self.assertEqual(parsed.exc_value, "attempt to divide by zero")
        self.assertEqual(parsed.frames[0].file, "src/cart.rs")
        self.assertEqual(parsed.frames[0].line, 70)
        self.assertEqual(parsed.frames[0].func, "proof_shop_rust::cart::summary")
        self.assertTrue(
            any(frame.file == "src/server.rs" for frame in parsed.frames)
        )

    def test_div_zero(self):
        parsed = info("div_zero.txt")
        self.assertEqual(parsed.exc_value, "attempt to divide by zero")
        self.assertEqual(
            (parsed.frames[0].file, parsed.frames[0].line),
            ("src/bin/div_zero.rs", 1),
        )

    def test_index_oob(self):
        parsed = info("index_oob.txt")
        self.assertEqual(
            parsed.exc_value, "index out of bounds: the len is 2 but the index is 4"
        )
        self.assertEqual(parsed.frames[0].func, "index_oob::pick")

    def test_assert_fail_message_is_first_line(self):
        parsed = info("assert_fail.txt")
        self.assertEqual(
            parsed.exc_value,
            "assertion `left == right` failed: till totals must balance",
        )
        self.assertEqual(parsed.frames[0].file, "src/bin/assert_fail.rs")

    def test_overflow(self):
        parsed = info("overflow.txt")
        self.assertEqual(parsed.exc_value, "attempt to add with overflow")

    def test_custom_panic(self):
        parsed = info("custom_panic.txt")
        self.assertEqual(parsed.exc_value, "order total went negative: -50")

    def test_expect_err(self):
        parsed = info("expect_err.txt")
        self.assertIn("config must load", parsed.exc_value)

    def test_no_backtrace_head_frame_only(self):
        parsed = info("unwrap_none.txt")
        self.assertEqual(
            parsed.exc_value, "called `Option::unwrap()` on a `None` value"
        )
        self.assertEqual(len(parsed.frames), 1)
        self.assertEqual(parsed.frames[0].file, "src/bin/unwrap_none.rs")
        self.assertEqual(parsed.frames[0].line, 1)

    def test_backtrace_disabled(self):
        parsed = info("overflow_notrace.txt")
        self.assertEqual(parsed.exc_value, "attempt to add with overflow")
        self.assertEqual(len(parsed.frames), 1)

    def test_legacy_format(self):
        # Documented pre-1.73 shape (modern rustc cannot emit it):
        # message inline, single line, no backtrace section.
        parsed = info("legacy_pre173_panic.txt")
        self.assertEqual(parsed.exc_value, "attempt to divide by zero")
        self.assertEqual(
            (parsed.frames[0].file, parsed.frames[0].line), ("src/main.rs", 2)
        )

    def test_rejects_foreign_traces(self):
        for snippet in (
            'Traceback (most recent call last):\n  File "/a/b.py", line 1, in f\nValueError: x\n',
            "TypeError: boom\n    at f (/app/x.js:1:1)\n",
            "panic: boom\ngoroutine 1 [running]:\n",
            "PHP Fatal error:  Uncaught Error: x in /a/b.php:1\nStack trace:\n#0 {main}\n",
            "java.lang.ArithmeticException: / by zero\n\tat com.Foo.bar(Foo.java:1)\n",
            "INFO all good\nlistening on :8080\n",
        ):
            self.assertIsNone(ADAPTER.parse_trace(snippet), snippet[:40])

    def test_empty_backtrace_section(self):
        # Genuinely observed once (1/3 trigger runs): the engine printed
        # `stack backtrace:` plus the omission note with zero frames.
        # The panic location must still come through.
        parsed = info("proofshop_empty_backtrace.txt")
        self.assertEqual(parsed.exc_value, "attempt to divide by zero")
        self.assertEqual(len(parsed.frames), 1)
        self.assertEqual(
            (parsed.frames[0].file, parsed.frames[0].line),
            ("src/cart.rs", 70),
        )


class MapFrameTest(unittest.TestCase):
    PATHS = ["Cargo.toml", "src/cart.rs", "src/server.rs", "tests/api.rs"]

    def test_suffix(self):
        self.assertEqual(
            ADAPTER.map_frame("./src/cart.rs", "cart::summary", self.PATHS),
            "src/cart.rs",
        )
        self.assertEqual(
            ADAPTER.map_frame(
                "/app/src/server.rs", "server::handle", self.PATHS
            ),
            "src/server.rs",
        )

    def test_std_never_maps(self):
        self.assertIsNone(
            ADAPTER.map_frame(
                "/rustc/58cf/library/std/src/panicking.rs",
                "std::panicking::begin_panic",
                self.PATHS,
            )
        )

    def test_miss(self):
        self.assertIsNone(
            ADAPTER.map_frame("src/other.rs", "other::f", self.PATHS)
        )


class DetectTest(unittest.TestCase):
    def test_scores(self):
        self.assertEqual(
            ADAPTER.detect(["Cargo.toml", "src/main.rs"]), 1 + 5
        )
        self.assertEqual(ADAPTER.detect(["src/main.rs"]), 1)
        self.assertEqual(ADAPTER.detect(["package.json", "x.js"]), 0)

    def test_source_files(self):
        self.assertEqual(
            ADAPTER.source_files(["a.rs", "b.py", "Cargo.toml"]), ["a.rs"]
        )


class CommandsTest(unittest.TestCase):
    PATHS = ["Cargo.toml", "src/lib.rs", "src/cart.rs", "tests/api.rs"]

    def test_install(self):
        self.assertEqual(
            ADAPTER.install_cmds(self.PATHS),
            [["cargo", "fetch"], ["cargo", "test", "--no-run"]],
        )
        self.assertEqual(ADAPTER.install_cmds(["src/main.rs"]), [])

    def test_suite(self):
        self.assertEqual(
            ADAPTER.suite_cmd(self.PATHS),
            ["cargo", "test", "--offline", "--no-fail-fast"],
        )

    def test_single_integration(self):
        self.assertEqual(
            ADAPTER.single_test_cmd("tests/ta_repro_abc123.rs", self.PATHS),
            ["cargo", "test", "--offline", "--test", "ta_repro_abc123"],
        )

    def test_single_inline_module(self):
        self.assertEqual(
            ADAPTER.single_test_cmd("src/cart.rs", self.PATHS),
            ["cargo", "test", "--offline", "ta_repro"],
        )

    def test_timeouts_and_image(self):
        self.assertEqual(
            (ADAPTER.name, ADAPTER.image),
            ("rust", "rust"),
        )
        self.assertEqual(
            (ADAPTER.install_timeout_s, ADAPTER.suite_timeout_s), (900, 900)
        )


class ParseResultsTest(unittest.TestCase):
    def test_pass(self):
        result = ADAPTER.parse_results(PASS_RUN, "", lambda _path: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (21, 21, 0))
        self.assertEqual(result.failed_ids, [])

    def test_fail(self):
        result = ADAPTER.parse_results(FAIL_RUN, "", lambda _path: None)
        self.assertFalse(result.errored)
        self.assertEqual((result.total, result.passed, result.failed), (2, 1, 1))
        self.assertEqual(result.failed_ids, ["empty_cart_average_is_zero"])

    def test_compile_error(self):
        result = ADAPTER.parse_results(
            COMPILE_ERROR, "", lambda _path: None
        )
        self.assertTrue(result.errored)
        self.assertEqual(result.total, 0)


class ReproTest(unittest.TestCase):
    LIB = ["Cargo.toml", "src/lib.rs", "src/cart.rs"]
    BIN = ["Cargo.toml", "src/main.rs"]

    def test_lib_gets_integration_test(self):
        self.assertEqual(
            ADAPTER.repro_test_path("abc123def456789", self.LIB, ["src/cart.rs"]),
            "tests/ta_repro_abc123def456.rs",
        )

    def test_binary_only_gets_inline_module(self):
        self.assertEqual(
            ADAPTER.repro_test_path("abc123def456789", self.BIN, ["src/main.rs"]),
            "src/main.rs",
        )

    def test_bin_target_gets_inline_module(self):
        paths = self.LIB + ["src/bin/tool.rs"]
        self.assertEqual(
            ADAPTER.repro_test_path("abc123def456789", paths, ["src/bin/tool.rs"]),
            "src/bin/tool.rs",
        )

    def test_binary_no_located_falls_back(self):
        self.assertEqual(
            ADAPTER.repro_test_path("abc123def456789", self.BIN, []),
            "src/main.rs",
        )

    def test_rules_and_check(self):
        rules = ADAPTER.repro_rules()
        self.assertIn("#[test]", rules)
        self.assertIn("tests/", rules)
        self.assertTrue(ADAPTER.looks_like_test("#[test]\nfn empty() {}"))
        self.assertFalse(ADAPTER.looks_like_test("fn empty() {}"))


if __name__ == "__main__":
    unittest.main()
