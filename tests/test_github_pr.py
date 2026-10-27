"""PR action tests use httpx.MockTransport: no network, real request flow."""

import json
import os
import unittest
from unittest.mock import patch

import httpx

from core.actions.github_pr import open_fix_pr, open_pr
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import GeneratedPatch

DIAGNOSIS = Diagnosis(
    summary="Deadlock on inventory_items",
    likely_cause="Lock ordering inversion",
    suggested_actions=[],
    confidence=0.9,
)
PATCH = GeneratedPatch(patch_code="fixed = True\n", test_code="def test_x(): assert True\n")


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.github.com")


def _ok(payload, status=200):
    return httpx.Response(status, json=payload)


class OpenPrTests(unittest.TestCase):
    def test_returns_pr_url_on_success(self) -> None:
        seen = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((request.method, request.url.path))
            if request.url.path.endswith("/git/ref/heads/main"):
                return _ok({"object": {"sha": "base-sha"}})
            if request.url.path.endswith("/git/ref/heads/fix-1"):
                return _ok({"message": "Not Found"}, status=404)
            if request.url.path.endswith("/git/blobs"):
                body = json.loads(request.content.decode())
                self.assertEqual(body["encoding"], "base64")
                return _ok({"sha": "blob-sha"}, status=201)
            if request.url.path.endswith("/git/trees"):
                return _ok({"sha": "tree-sha"}, status=201)
            if request.url.path.endswith("/git/commits"):
                return _ok({"sha": "commit-sha"}, status=201)
            if request.url.path.endswith("/git/refs"):
                return _ok({"ref": "refs/heads/fix-1"}, status=201)
            if request.url.path.endswith("/pulls"):
                body = json.loads(request.content.decode())
                self.assertEqual(body["head"], "fix-1")
                self.assertEqual(body["base"], "main")
                return _ok({"html_url": "https://github.com/o/r/pull/1"}, status=201)
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        url = open_pr(
            repo="o/r",
            base="main",
            branch="fix-1",
            title="fix: x",
            body="b",
            files={"solution.py": "p", "test_solution.py": "t"},
            token="t",
            client=_client(handler),
        )
        self.assertEqual(url, "https://github.com/o/r/pull/1")
        self.assertEqual(
            [m for m, _ in seen].count("POST"), 6
        )  # 2 blobs + tree + commit + ref + PR

    def test_branch_collision_picks_suffix(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/git/ref/heads/main"):
                return _ok({"object": {"sha": "base-sha"}})
            if request.url.path.endswith("/git/ref/heads/fix-1"):
                return _ok({"object": {"sha": "taken"}})
            if request.url.path.endswith("/git/ref/heads/fix-1-2"):
                return _ok({"message": "Not Found"}, status=404)
            if request.url.path.endswith("/git/blobs"):
                return _ok({"sha": "b"}, status=201)
            if request.url.path.endswith("/git/trees"):
                return _ok({"sha": "t"}, status=201)
            if request.url.path.endswith("/git/commits"):
                return _ok({"sha": "c"}, status=201)
            if request.url.path.endswith("/git/refs"):
                body = json.loads(request.content.decode())
                self.assertEqual(body["ref"], "refs/heads/fix-1-2")
                return _ok({}, status=201)
            if request.url.path.endswith("/pulls"):
                return _ok({"html_url": "https://github.com/o/r/pull/2"}, status=201)
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        url = open_pr(
            repo="o/r",
            base="main",
            branch="fix-1",
            title="fix: x",
            body="b",
            files={"solution.py": "p"},
            token="t",
            client=_client(handler),
        )
        self.assertEqual(url, "https://github.com/o/r/pull/2")

    def test_missing_token_raises_without_http(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise AssertionError("no HTTP without a token")

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                open_pr(
                    repo="o/r",
                    base="main",
                    branch="b",
                    title="t",
                    body="b",
                    files={"solution.py": "p"},
                    client=None,
                )
        self.assertIn("GITHUB_TOKEN", str(ctx.exception))

    def test_unauthorized_maps_to_actionable_error(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return _ok({"message": "Bad credentials"}, status=401)

        with self.assertRaises(RuntimeError) as ctx:
            open_pr(
                repo="o/r",
                base="main",
                branch="b",
                title="t",
                body="b",
                files={"solution.py": "p"},
                token="bad",
                client=_client(handler),
            )
        self.assertIn("401", str(ctx.exception))

    def test_empty_files_rejected(self) -> None:
        with self.assertRaises(ValueError):
            open_pr(
                repo="o/r", base="main", branch="b", title="t", body="b",
                files={}, token="t", client=_client(lambda r: _ok({})),
            )


class OpenFixPrTests(unittest.TestCase):
    def test_builds_title_body_and_files(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/git/ref/heads/main"):
                return _ok({"object": {"sha": "base"}})
            if "/git/ref/heads/" in request.url.path:
                return _ok({"message": "Not Found"}, status=404)
            if request.url.path.endswith("/git/blobs"):
                return _ok({"sha": "b"}, status=201)
            if request.url.path.endswith("/git/trees"):
                tree = json.loads(request.content.decode())["tree"]
                captured["paths"] = sorted(n["path"] for n in tree)
                return _ok({"sha": "t"}, status=201)
            if request.url.path.endswith("/git/commits"):
                return _ok({"sha": "c"}, status=201)
            if request.url.path.endswith("/git/refs"):
                return _ok({}, status=201)
            if request.url.path.endswith("/pulls"):
                captured.update(json.loads(request.content.decode()))
                return _ok({"html_url": "https://github.com/o/r/pull/9"}, status=201)
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        url = open_fix_pr(
            diagnosis=DIAGNOSIS,
            patch=PATCH,
            verification_feedback="1 passed",
            attempts=2,
            model_used="baseten:x",
            repo="o/r",
            branch="fix-9",
            token="t",
            client=_client(handler),
        )
        self.assertEqual(url, "https://github.com/o/r/pull/9")
        self.assertEqual(captured["paths"], ["solution.py", "test_solution.py"])
        self.assertIn("Deadlock on inventory_items", captured["title"])
        self.assertIn("Lock ordering inversion", captured["body"])
        self.assertIn("2", captured["body"])
        self.assertIn("baseten:x", captured["body"])
        self.assertIn("1 passed", captured["body"])

    def test_custom_paths_touch_real_file(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path.endswith("/git/ref/heads/main"):
                return _ok({"object": {"sha": "base"}})
            if "/git/ref/heads/" in request.url.path:
                return _ok({"message": "Not Found"}, status=404)
            if request.url.path.endswith("/git/blobs"):
                return _ok({"sha": "b"}, status=201)
            if request.url.path.endswith("/git/trees"):
                tree = json.loads(request.content.decode())["tree"]
                captured["paths"] = sorted(n["path"] for n in tree)
                return _ok({"sha": "t"}, status=201)
            if request.url.path.endswith("/git/commits"):
                return _ok({"sha": "c"}, status=201)
            if request.url.path.endswith("/git/refs"):
                return _ok({}, status=201)
            if request.url.path.endswith("/pulls"):
                return _ok({"html_url": "https://github.com/o/r/pull/9"}, status=201)
            raise AssertionError(f"unexpected {request.method} {request.url.path}")

        url = open_fix_pr(
            diagnosis=DIAGNOSIS,
            patch=PATCH,
            verification_feedback="1 passed",
            attempts=1,
            model_used="m",
            repo="o/r",
            token="t",
            client=_client(handler),
            code_path="inventory.py",
        )
        self.assertEqual(url, "https://github.com/o/r/pull/9")
        self.assertEqual(captured["paths"], ["inventory.py", "test_solution.py"])

    def test_missing_repo_raises(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                open_fix_pr(
                    diagnosis=DIAGNOSIS,
                    patch=PATCH,
                    verification_feedback="",
                    attempts=1,
                    model_used="m",
                    client=_client(lambda r: _ok({})),
                )
        self.assertIn("GITHUB_DEMO_REPO", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
