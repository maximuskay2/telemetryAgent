"""L-D4: end-to-end language matrix (mocked GitHub, real Docker sandboxes).

For each language, `run_repo_fix` runs against that language's proof app:
the real trigger trace goes in, GitHub is an httpx mock serving the real
proof-app files, and the sandbox is the real per-language Docker image.

Two modes (see scripts/lang_e2e.sh):
- mocked (default): canned repro + patch per language prove the plumbing
  deterministically; the outcome must be PASS with the mock PR url.
- live (TA_E2E_LIVE=1): real models (Baseten first, Wonder last attempt);
  PASS or draft both pass — a draft is recorded, not a failure.

Selection: TA_E2E_LANGS=all (default) or a comma-separated subset of
python,javascript,java,kotlin,go,rust,php. A language skips when Docker
is missing, when its adapter hasn't landed yet, or (mocked mode) when
no canned outputs exist for it yet.
"""

import asyncio
import base64
import contextlib
import hashlib
import io
import os
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import httpx

from core.repo_fix import generate as repo_generate
from core.repo_fix import run as repo_run
from core.repo_fix.lang import by_name as adapter_by_name
from core.schemas.diagnosis import Diagnosis
from core.verify import repo_sandbox
from core.verify.local_runner import resolve_docker

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "examples"
TRACES = Path(__file__).resolve().parent / "fixtures" / "traces"

LIVE = os.environ.get("TA_E2E_LIVE", "") == "1"
SELECTED = {
    lang.strip().lower()
    for lang in os.environ.get("TA_E2E_LANGS", "all").split(",")
    if lang.strip()
}

MOCK_PR_URL = "https://github.com/acme/proof-app/pull/7"
MOCK_SHA = "abc123def456789012345678901234567890abcd"

#: Build outputs never shipped in the mock tarball (mirrors .gitignore).
_EXCLUDE_DIRS = {
    "target",
    "vendor",
    "build",
    ".phpunit.cache",
    "node_modules",
    "__pycache__",
    ".git",
}


def _snap_files(appdir):
    """Worktree files minus build outputs: {relpath: bytes}."""
    files = {}
    for path in sorted(appdir.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(appdir).as_posix()
        if any(part in _EXCLUDE_DIRS for part in rel.split("/")):
            continue
        files[rel] = path.read_bytes()
    assert files, f"no files under {appdir}"
    return files


def _make_tar(files, top):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in sorted(files):
            data = files[name]
            info = tarfile.TarInfo(name=f"{top}/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


class MockGitHub:
    """httpx transport serving a proof app as a GitHub repo + PR flow."""

    def __init__(self, repo, files):
        self.repo = repo
        self.files = files
        self.tarball = _make_tar(files, f"{repo.rsplit('/', 1)[-1]}-abc123d")

    def handler(self, request):
        path = request.url.path
        method = request.method
        base = f"/repos/{self.repo}"
        if path == f"{base}/commits/{MOCK_SHA}":
            return httpx.Response(200, json={"sha": MOCK_SHA})
        if path == base:
            return httpx.Response(200, json={"default_branch": "main"})
        if path == f"{base}/git/trees/{MOCK_SHA}":
            return httpx.Response(
                200,
                json={
                    "truncated": False,
                    "tree": [
                        {"type": "blob", "path": name}
                        for name in sorted(self.files)
                    ],
                },
            )
        if path.startswith(f"{base}/contents/"):
            rel = path[len(f"{base}/contents/") :]
            if rel in self.files:
                content = base64.b64encode(self.files[rel]).decode()
                return httpx.Response(
                    200, json={"content": content, "size": len(self.files[rel])}
                )
            return httpx.Response(404, json={"message": "Not Found"})
        if path == f"{base}/tarball/{MOCK_SHA}":
            return httpx.Response(200, content=self.tarball)
        if path == f"{base}/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": MOCK_SHA}})
        if path.startswith(f"{base}/git/ref/heads/"):
            return httpx.Response(404, json={"message": "Not Found"})
        if path == f"{base}/pulls" and method == "GET":
            return httpx.Response(200, json=[])
        if path == f"{base}/git/blobs":
            return httpx.Response(201, json={"sha": "blob1"})
        if path == f"{base}/git/trees":
            return httpx.Response(201, json={"sha": "tree1"})
        if path == f"{base}/git/commits":
            return httpx.Response(201, json={"sha": "commit1"})
        if path == f"{base}/git/refs":
            return httpx.Response(201, json={"ref": "x"})
        if path == f"{base}/pulls" and method == "POST":
            return httpx.Response(
                201, json={"html_url": MOCK_PR_URL, "number": 7}
            )
        if path == f"{base}/labels":
            return httpx.Response(201, json={})
        if path == f"{base}/issues/7":
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"message": "Not Found"})

    def client(self):
        return httpx.Client(
            transport=httpx.MockTransport(self.handler),
            base_url="https://api.github.com",
        )


# --------------------------------------------------------------------------
# Canned model outputs (mocked mode). Patches derive from the worktree
# files by replacing the BUG line, so they track formatting drift.
# --------------------------------------------------------------------------

PYTHON_REPRO = '''"""Empty-cart repro (canned for the mocked matrix)."""

from app.cart import summary


def test_empty_cart_average_is_zero():
    assert summary([])["average_item_price"] == 0.0
'''

PYTHON_BUG = "    average = round(total / len(items), 2)  # BUG: empty cart -> ZeroDivisionError\n"
PYTHON_FIX = """    if not items:
        return {
            "lines": 0,
            "subtotal": 0.0,
            "discount": 0.0,
            "total": 0.0,
            "average_item_price": 0.0,
        }
    average = round(total / len(items), 2)
"""


def _python_canned(appdir):
    cart = appdir / "app" / "cart.py"
    content = cart.read_text()
    assert PYTHON_BUG in content, "python BUG line moved"
    return PYTHON_REPRO, [
        {"path": "app/cart.py", "content": content.replace(PYTHON_BUG, PYTHON_FIX)}
    ]


RUST_REPRO = """//! Empty-cart repro (canned for the mocked matrix).

use proof_shop_rust::cart::{self, Item};

#[test]
fn empty_cart_average_is_zero() {
    let result = cart::summary(&[]);
    assert_eq!(result.average_cents, 0);
}

#[test]
fn nonempty_cart_still_totals() {
    let result = cart::summary(&[Item::new("a", 400, 2)]);
    assert_eq!(result.total_cents, 800);
}
"""

RUST_BUG = "    let average = total / items.len() as i64; // BUG: empty cart -> attempt to divide by zero\n"
RUST_FIX = """    if items.is_empty() {
        return Summary {
            lines: 0,
            subtotal_cents: 0,
            discount_cents: 0,
            total_cents: 0,
            average_cents: 0,
            currency: "USD".to_string(),
        };
    }
    let average = total / items.len() as i64;
"""


def _rust_canned(appdir):
    cart = appdir / "src" / "cart.rs"
    content = cart.read_text()
    assert RUST_BUG in content, "rust BUG line moved"
    return RUST_REPRO, [
        {"path": "src/cart.rs", "content": content.replace(RUST_BUG, RUST_FIX)}
    ]


PHP_REPRO_TMPL = """<?php

declare(strict_types=1);

namespace ProofShop\\Tests;

use PHPUnit\\Framework\\TestCase;
use ProofShop\\Cart;

final class {cls} extends TestCase
{{
    public function testEmptyCartAverageIsZero(): void
    {{
        $summary = Cart::summary([]);
        $this->assertSame(0.0, $summary['average_item_price']);
    }}
}}
"""

PHP_BUG = "        $average = intdiv($total, count($items)); // BUG: empty cart -> DivisionByZeroError\n"
PHP_FIX = "        $average = count($items) === 0 ? 0 : intdiv($total, count($items));\n"


def _php_canned(appdir):
    cart = appdir / "src" / "Cart.php"
    content = cart.read_text()
    assert PHP_BUG in content, "php BUG line moved"
    return None, [
        {"path": "src/Cart.php", "content": content.replace(PHP_BUG, PHP_FIX)}
    ]


def _php_repro_for(test_path):
    cls = test_path.rsplit("/", 1)[-1]
    assert cls.endswith("Test.php"), test_path
    return PHP_REPRO_TMPL.format(cls=cls[: -len(".php")])


# --------------------------------------------------------------------------
# Proof-app trigger traces. Rust/PHP live in trace fixtures (also parsed
# by the adapter suites); the rest are verbatim captures inlined here —
# each was produced by its app's trigger against a live server on 30 Oct.
# --------------------------------------------------------------------------

PYTHON_TRACE = """Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/uvicorn/protocols/http/h11_impl.py", line 403, in run_asgi
    result = await app(  # type: ignore[func-returns-value]
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/uvicorn/middleware/proxy_headers.py", line 60, in __call__
    return await self.app(scope, receive, send)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/applications.py", line 1054, in __call__
    await super().__call__(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/applications.py", line 113, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/errors.py", line 187, in __call__
    raise exc
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/errors.py", line 165, in __call__
    await self.app(scope, receive, _send)
  File "/usr/local/lib/python3.11/site-packages/starlette/middleware/exceptions.py", line 62, in __call__
    await wrap_app_handling_exceptions(self.app, conn)(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/usr/local/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 715, in __call__
    await self.middleware_stack(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 735, in app
    await route.handle(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 288, in handle
    await self.app(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 76, in app
    await wrap_app_handling_exceptions(app, request)(scope, receive, send)
  File "/usr/local/lib/python3.11/site-packages/starlette/_exception_handler.py", line 53, in wrapped_app
    raise exc
  File "/usr/local/lib/python3.11/site-packages/starlette/_exception_handler.py", line 42, in wrapped_app
    await app(scope, receive, sender)
  File "/usr/local/lib/python3.11/site-packages/starlette/routing.py", line 73, in app
    response = await f(request)
               ^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/routing.py", line 301, in app
    raw_response = await run_endpoint_function(
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/fastapi/routing.py", line 214, in run_endpoint_function
    return await run_in_threadpool(dependant.call, **values)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/starlette/concurrency.py", line 39, in run_in_threadpool
    return await anyio.to_thread.run_sync(func, *args)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/anyio/to_thread.py", line 65, in run_sync
    return await get_async_backend().run_sync_in_worker_thread(
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/anyio/_backends/_asyncio.py", line 2706, in run_sync_in_worker_thread
    return await future
           ^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/anyio/_backends/_asyncio.py", line 1100, in run
    result = context.run(func, *args)
             ^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/main.py", line 34, in checkout
    return summary([item.model_dump() for item in payload.items])
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/app/app/cart.py", line 37, in summary
    average = round(total / len(items), 2)  # BUG: empty cart -> ZeroDivisionError
                    ~~~~~~^~~~~~~~~~~~
ZeroDivisionError: float division by zero
"""

JAVASCRIPT_TRACE = """TypeError: Cannot read properties of undefined (reading 'currency')
    at summary (file:///app/src/cart.js:40:29)
    at IncomingMessage.<anonymous> (file:///app/src/server.js:48:26)
    at IncomingMessage.emit (node:events:524:28)
    at endReadableNT (node:internal/streams/readable:1698:12)
    at process.processTicksAndRejections (node:internal/process/task_queues:82:21)
"""

JAVA_TRACE = """java.lang.ArithmeticException: / by zero
\tat com.example.shop.Cart.summary(Cart.java:58)
\tat com.example.shop.ShopServer.lambda$create$1(ShopServer.java:41)
\tat jdk.httpserver/com.sun.net.httpserver.Filter$Chain.doFilter(Filter.java:98)
\tat jdk.httpserver/sun.net.httpserver.AuthFilter.doFilter(AuthFilter.java:82)
\tat jdk.httpserver/com.sun.net.httpserver.Filter$Chain.doFilter(Filter.java:101)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Exchange$LinkHandler.handle(ServerImpl.java:969)
\tat jdk.httpserver/sun.net.httpserver.Filter$Chain.doFilter(Filter.java:98)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Exchange.run(ServerImpl.java:945)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$DefaultExecutor.execute(ServerImpl.java:207)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Dispatcher.handle(ServerImpl.java:620)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Dispatcher.run(ServerImpl.java:585)
\tat java.base/java.lang.Thread.run(Thread.java:1583)
"""

KOTLIN_TRACE = """java.lang.ArithmeticException: / by zero
\tat com.example.shop.Cart.summary(Cart.kt:48)
\tat com.example.shop.ShopServer.create$lambda$1(ShopServer.kt:33)
\tat jdk.httpserver/com.sun.net.httpserver.Filter$Chain.doFilter(Filter.java:98)
\tat jdk.httpserver/sun.net.httpserver.AuthFilter.doFilter(AuthFilter.java:82)
\tat jdk.httpserver/sun.net.httpserver.Filter$Chain.doFilter(Filter.java:101)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Exchange$LinkHandler.handle(ServerImpl.java:969)
\tat jdk.httpserver/sun.net.httpserver.Filter$Chain.doFilter(Filter.java:98)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Exchange.run(ServerImpl.java:945)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$DefaultExecutor.execute(ServerImpl.java:207)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Dispatcher.handle(ServerImpl.java:620)
\tat jdk.httpserver/sun.net.httpserver.ServerImpl$Dispatcher.run(ServerImpl.java:585)
\tat java.base/java.lang.Thread.run(Thread.java:1583)
"""

GO_TRACE = """2026/10/30 15:00:21 panic: runtime error: integer divide by zero
goroutine 8 [running]:
runtime/debug.Stack()
\t/usr/local/go/src/runtime/debug/stack.go:26 +0x64
proofshop/shop.Handler.withRecovery.func1.1()
\t/app/shop/server.go:73 +0x44
panic({0x26f940?, 0x4e81f0?})
\t/usr/local/go/src/runtime/panic.go:791 +0x124
proofshop/shop.Summarize({0x51b920, 0x4000076300?, 0x0})
\t/app/shop/cart.go:70 +0x1b8
proofshop/shop.NewMux.func2({0x33b268, 0x400011a1c0}, 0xffffb32f9428?)
\t/app/shop/server.go:106 +0x174
net/http.HandlerFunc.ServeHTTP(0x400011a0e0?, {0x33b268?, 0x400011a1c0?}, 0x0?)
\t/usr/local/go/src/net/http/server.go:2220 +0x38
net/http.(*ServeMux).ServeHTTP(0x4000060ae8?, {0x33b268, 0x400011a1c0}, 0x400012e140)
\t/usr/local/go/src/net/http/server.go:2747 +0x1b4
proofshop/shop.Handler.withRecovery.func1({0x33b268?, 0x400011a1c0?}, 0x0?)
\t/app/shop/server.go:79 +0x6c
net/http.HandlerFunc.ServeHTTP(0x10?, {0x33b268?, 0x400011a1c0?}, 0x400011a1c0?)
\t/usr/local/go/src/net/http/server.go:2220 +0x38
net/http.serverHandler.ServeHTTP({0x33a0d0?}, {0x33b268?, 0x400011a1c0?}, 0x6?)
\t/usr/local/go/src/net/http/server.go:3210 +0xbc
net/http.(*conn).serve(0x4000130120, {0x33b848, 0x400010cdb0})
\t/usr/local/go/src/net/http/server.go:2092 +0x4fc
created by net/http.(*Server).Serve in goroutine 1
\t/usr/local/go/src/net/http/server.go:3360 +0x3dc
"""


def _rust_trace():
    return (TRACES / "rust" / "proofshop_empty_cart.txt").read_text()


def _php_trace():
    return (TRACES / "php" / "proofshop_division_by_zero.txt").read_text()


# lang -> (adapter name, proof-app dir, trace, canned builder | None).
# Canned outputs exist where the adapter does; the rest flip on as
# James/John land java/go/javascript (trace + app already wired).
LANGS = {
    "python": ("python", "proof-app", PYTHON_TRACE, _python_canned),
    "javascript": ("javascript", "proof-app-node", JAVASCRIPT_TRACE, None),
    "java": ("java", "proof-app-java", JAVA_TRACE, None),
    "kotlin": ("kotlin", "proof-app-kotlin", KOTLIN_TRACE, None),
    "go": ("go", "proof-app-go", GO_TRACE, None),
    "rust": ("rust", "proof-app-rust", None, _rust_canned),
    "php": ("php", "proof-app-php", None, _php_canned),
}


def _trace_for(lang):
    if lang == "rust":
        return _rust_trace()
    if lang == "php":
        return _php_trace()
    return LANGS[lang][2]


class LangE2EMatrix(unittest.TestCase):
    """One method per language so `-k` and the shell summary stay simple."""

    maxDiff = 4000

    def _run_lang(self, lang):
        adapter_name, appdir_name, _trace, canned_fn = LANGS[lang]
        if "all" not in SELECTED and lang not in SELECTED:
            self.skipTest(f"not selected (TA_E2E_LANGS)")
        adapter = adapter_by_name(adapter_name)
        if adapter is None:
            self.skipTest(f"no {adapter_name} adapter yet")
        if not LIVE and canned_fn is None:
            self.skipTest(f"no canned outputs for {lang} yet")
        if LIVE and not os.environ.get("BASETEN_API_KEY"):
            self.skipTest("live mode needs BASETEN_API_KEY")
        if resolve_docker() is None:
            self.skipTest("no docker CLI")

        appdir = EXAMPLES / appdir_name
        files = _snap_files(appdir)
        repo = f"acme/{appdir_name}"
        fake = MockGitHub(repo, files)
        fingerprint = hashlib.sha1(f"ta-e2e-{lang}".encode()).hexdigest()[:12]
        diagnosis = Diagnosis(
            summary=f"Empty-cart crash in {appdir_name} (e2e canned).",
            likely_cause="Missing empty-list guard in the totals path.",
            suggested_actions=["Add the guard."],
            confidence=0.9,
        )
        image = adapter.image

        def factory(tar):
            return repo_sandbox.open_repo_sandbox(tar, image=image)

        patches = []
        if not LIVE:
            assert canned_fn is not None
            repro_code, patch_files = canned_fn(appdir)

            def fake_repro(*args, **kwargs):
                test_path = kwargs.get("test_path")
                if test_path is None and len(args) >= 8:
                    test_path = args[7]
                code = repro_code
                if code is None:  # PHP: class name must match the file
                    assert test_path, "repro needs test_path"
                    code = _php_repro_for(test_path)
                return code, "mocked"

            def fake_patch(*args, **kwargs):
                return patch_files, "mocked", ""

            patches = [
                mock.patch.object(
                    repo_generate, "generate_repro_test", fake_repro
                ),
                mock.patch.object(
                    repo_generate, "generate_patch", fake_patch
                ),
                mock.patch.object(
                    repo_generate,
                    "choose_files",
                    lambda ranked, signature: list(ranked)[:5],
                ),
            ]

        tmp = tempfile.mkdtemp(prefix="ta-e2e-")
        started = time.perf_counter()
        stack = contextlib.ExitStack()
        stack.enter_context(
            mock.patch.dict(os.environ, {"TA_DATA_DIR": tmp, "TA_VERIFY": "local"})
        )
        for entered in patches:
            stack.enter_context(entered)
        try:
            try:
                outcome = asyncio.run(
                    repo_run.run_repo_fix(
                        run_id=f"e2e{lang}12345678",
                        system_id="acme",
                        repo_info={
                            "repo": repo,
                            "base": "main",
                            "token": "good",
                        },
                        fingerprint=fingerprint,
                        traceback_text=_trace_for(lang),
                        commit=MOCK_SHA,
                        gate={"decision": "observe"},
                        http_client=fake.client(),
                        sandbox_factory=factory,
                        diagnose_fn=None if LIVE else (lambda *args: diagnosis),
                        adapter_name=adapter_name,
                        language=lang,
                    )
                )
            except repo_sandbox.SandboxUnavailable as exc:
                self.skipTest(f"no sandbox: {exc}")
        finally:
            stack.close()
            shutil.rmtree(tmp, ignore_errors=True)
        seconds = time.perf_counter() - started
        try:
            from apps.api.main import software_runs

            entry = software_runs.get(f"e2e{lang}12345678") or {}
            stored = entry.get("result")
            detail = (getattr(stored, "stderr", "") or "")[:200]
            model_used = getattr(stored, "model_used", "") or ""
        except Exception:
            detail = ""
            model_used = ""
        status = outcome.get("status")
        if status == "PASS":
            result = "PASS"
        elif status == "NO_ACTION":
            result = "DRAFT"
        else:
            result = "FAIL"
        print(
            f"E2E lang={lang} result={result} seconds={seconds:.0f} "
            f"pr={outcome.get('pr_url', '')} "
            f"model={model_used if LIVE else 'mocked'} "
            f"reason={(outcome.get('reason', '') or detail)[:200]}"
        )
        if result == "FAIL":
            self.fail(f"{lang} run failed: {outcome}")
        if not LIVE:
            self.assertEqual(
                status,
                "PASS",
                f"{lang} mocked run must PASS, got: {outcome}",
            )
            self.assertEqual(outcome.get("pr_url"), MOCK_PR_URL)

    def test_python(self):
        self._run_lang("python")

    def test_javascript(self):
        self._run_lang("javascript")

    def test_java(self):
        self._run_lang("java")

    def test_kotlin(self):
        self._run_lang("kotlin")

    def test_go(self):
        self._run_lang("go")

    def test_rust(self):
        self._run_lang("rust")

    def test_php(self):
        self._run_lang("php")


if __name__ == "__main__":
    unittest.main()

