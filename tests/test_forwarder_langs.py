"""L-N2: ta_forward.py forwards whole traces for every §1.1 language."""

import ast
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "agent" / "ta_forward.py"
TRACES = Path(__file__).resolve().parent / "fixtures" / "traces"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "ta_forward_langs_under_test", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class LangTraceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()
        handle, cls.log_path = tempfile.mkstemp(prefix="ta-forward-langs-")
        os.close(handle)

    def forwarded(self, lines):
        """Fresh tailer over `lines`, like main() feeds them, in order."""
        tailer = self.module.Tailer(self.log_path)
        return [tailer.wanted(line) for line in lines]

    def test_python_regression(self):
        lines = [
            "INFO boot ok",
            "Traceback (most recent call last):",
            '  File "/app/main.py", line 10, in <module>',
            "    run()",
            '  File "/app/lib.py", line 3, in run',
            "    1 / 0",
            "ZeroDivisionError: division by zero",
            "INFO after the crash",
            "ERROR something else broke",
        ]
        self.assertEqual(
            self.forwarded(lines),
            [False, True, True, True, True, True, True, False, True],
        )

    def test_javascript_real_fixture(self):
        text = (TRACES / "javascript" / "node_typeerror.txt").read_text()
        lines = text.splitlines()
        got = self.forwarded(["INFO noise before"] + lines + ["INFO noise after"])
        # Pre-head code frame is plain log text (dropped); the head and
        # every frame forward; blanks and the version trailer do not.
        head = next(
            i for i, line in enumerate(lines) if line.startswith("TypeError")
        )
        for i, line in enumerate(lines):
            if i < head:
                self.assertFalse(got[i + 1], line)
            elif not line.strip() or line.startswith("Node.js v"):
                # Blanks clear the trace; the version trailer drops.
                self.assertFalse(got[i + 1], repr(line))
            else:
                self.assertTrue(got[i + 1], line)
        self.assertFalse(got[0])
        self.assertFalse(got[-1])

    def test_javascript_cause_fixture(self):
        text = (TRACES / "javascript" / "node_error_cause.txt").read_text()
        lines = text.splitlines()
        head = next(
            i for i, line in enumerate(lines) if line.startswith("Error:")
        )
        got = self.forwarded(lines)
        for i, line in enumerate(lines[head:], start=head):
            if not line.strip():
                continue
            if line.startswith("Node.js v"):
                # The blank above cleared the trace; the trailer drops.
                self.assertFalse(got[i], line)
            else:
                self.assertTrue(got[i], line)

    def test_java(self):
        lines = [
            "INFO starting service",
            "Exception in thread \"main\" java.lang.NullPointerException: "
            "Cannot invoke \"Item.price()\" because \"item\" is null",
            "\tat com.acme.shop.Cart.total(Cart.java:42)",
            "\tat com.acme.shop.Checkout.run(Checkout.java:17)",
            "Caused by: java.lang.IllegalStateException: cart not loaded",
            "\tat com.acme.shop.Cart.load(Cart.java:9)",
            "\t... 2 more",
            "INFO still alive",
        ]
        self.assertEqual(
            self.forwarded(lines),
            [False, True, True, True, True, True, True, False],
        )

    def test_go(self):
        lines = [
            "INFO listening on :8080",
            "panic: runtime error: invalid memory address or nil pointer",
            "[signal SIGSEGV: segmentation violation code=0x1 addr=0x0]",
            "goroutine 1 [running]:",
            "main.checkout()",
            "\t/app/checkout.go:12 +0x45",
            "net/http.(*Server).Serve()",
            "\t/net/http/server.go:1 +0x1",
            "main.main()",
            "\t/app/main.go:30 +0x1a",
            "created by main.init in goroutine 3",
            "\t/app/init.go:5 +0x20",
            "INFO recovered never",
        ]
        self.assertEqual(self.forwarded(lines), [False] + [True] * 11 + [False])

    def test_rust_new_format(self):
        lines = [
            "INFO booting",
            "thread 'main' panicked at src/main.rs:4:5:",
            "called `Option::unwrap()` on a `None` value",
            "stack backtrace:",
            "   0: rust_begin_unwind",
            "             at ./src/panic.rs:10:5",
            "   1: shop::checkout",
            "             at ./src/main.rs:4:5",
            "note: Some details are omitted, run with `RUST_BACKTRACE=full`",
            "INFO done",
        ]
        self.assertEqual(self.forwarded(lines), [False] + [True] * 8 + [False])

    def test_rust_old_format(self):
        lines = [
            "thread 'main' panicked at 'boom', src/main.rs:4:5",
            "note: run with `RUST_BACKTRACE=1` to display a backtrace",
            "INFO done",
        ]
        self.assertEqual(self.forwarded(lines), [True, True, False])

    def test_php(self):
        lines = [
            "INFO request start",
            "PHP Fatal error:  Uncaught TypeError: count(): Argument #1 "
            "($value) must be of type Countable|array, null given in "
            "/var/www/html/app/Cart.php:12",
            "Stack trace:",
            "#0 /var/www/html/app/Cart.php(12): count(NULL)",
            "#1 /var/www/html/index.php(5): Cart->total()",
            "#2 {main}",
            "  thrown in /var/www/html/app/Cart.php on line 12",
            "INFO request end",
        ]
        self.assertEqual(
            self.forwarded(lines),
            [False, True, True, True, True, True, True, False],
        )

    def test_mixed_python_then_js(self):
        lines = [
            "Traceback (most recent call last):",
            '  File "/a.py", line 1, in <module>',
            "ValueError: bad",
            "TypeError: js boom",
            "    at f (/app/x.js:1:1)",
            "INFO end",
        ]
        self.assertEqual(self.forwarded(lines), [True] * 5 + [False])

    def test_starts(self):
        starts = self.module.trace_start_lang
        self.assertEqual(starts("TypeError: x"), "javascript")
        self.assertEqual(starts("⨯ Error: x"), "javascript")
        self.assertEqual(starts("[Error: ENOENT: y] {"), "javascript")
        self.assertEqual(
            starts("Exception in thread \"m\" a.b.C: x"), "java"
        )
        self.assertEqual(starts("com.foo.BarException: x"), "java")
        self.assertEqual(starts("Caused by: a.b.C: x"), "java")
        self.assertEqual(starts("panic: x"), "go")
        self.assertEqual(starts("fatal error: x"), "go")
        self.assertEqual(starts("goroutine 7 [running]:"), "go")
        self.assertEqual(
            starts("thread 'm' panicked at src/a.rs:1:2:"), "rust"
        )
        self.assertEqual(starts("PHP Fatal error: x"), "php")
        self.assertEqual(starts("Stack trace:"), "php")
        self.assertIsNone(starts("Traceback (most recent call last):"))
        self.assertIsNone(starts("INFO all quiet"))
        self.assertIsNone(starts(""))
        self.assertIsNone(starts("  errno: -2,"))

    def test_ends(self):
        end = self.module.is_traceback_end
        self.assertTrue(end("ValueError: x"))
        self.assertTrue(end("TypeError: boom"))
        self.assertTrue(end("panic: y"))
        self.assertTrue(end("thread 'm' panicked at src/a.rs:1:2:"))
        self.assertFalse(end("  indented source"))
        self.assertFalse(end("Traceback (most recent call last):"))
        self.assertFalse(end("INFO ok"))
        self.assertFalse(end(""))

    def test_still_stdlib_only_single_file(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(part.name.split(".")[0] for part in node.names)
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                imported.add(node.module.split(".")[0])
        self.assertEqual(
            imported,
            {"argparse", "json", "os", "re", "sys", "time", "urllib"},
        )


if __name__ == "__main__":
    unittest.main()
