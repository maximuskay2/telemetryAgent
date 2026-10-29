"""J-R2 acceptance: GitHub repo connection checks (James)."""

import os
import tempfile
import unittest
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

from apps.api.main import app
from core.connections import github as github_conn
from core.connections import store as connection_store
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-github-test-")


def _save_system(tmp: str, system_id: str = "acme") -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(system_id=system_id, name="Acme", kind="software")
        )


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def _repo_handler(mode: str):
    """Mock GitHub API: wrong-token | readonly | valid | bad-base."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.headers.get("Authorization") != "Bearer good":
            if path.startswith("/repos/"):
                return httpx.Response(
                    401, json={"message": "Bad credentials"}
                )
        if path == "/repos/acme/api":
            return httpx.Response(
                200, json={"default_branch": "main", "private": True}
            )
        if path == "/repos/acme/api/git/ref/heads/main":
            return httpx.Response(
                200, json={"object": {"sha": "abc123"}}
            )
        if path.startswith("/repos/acme/api/git/ref/heads/"):
            return httpx.Response(404, json={"message": "Not Found"})
        if path == "/repos/acme/api/git/refs":
            if mode == "readonly":
                return httpx.Response(
                    403,
                    json={"message": "Resource not accessible by token"},
                )
            return httpx.Response(201, json={"ref": "x", "object": {}})
        if path.startswith("/repos/acme/api/git/refs/heads/ta-probe-"):
            return httpx.Response(204)
        return httpx.Response(404, json={"message": "Not Found"})

    return handler


def _check(mode: str, **kwargs) -> dict:
    token = kwargs.pop("token", "good")
    client = httpx.Client(
        transport=_transport(_repo_handler(mode)),
        base_url="https://api.github.com",
        headers={"Authorization": f"Bearer {token}"},
    )
    return github_conn.check_repo("acme/api", token, client=client, **kwargs)


class CheckRepoTests(unittest.TestCase):
    def test_wrong_token_is_readable(self) -> None:
        result = _check("valid", token="bad")
        self.assertFalse(result["ok"])
        self.assertIn("rejected the token", result["detail"])
        self.assertEqual(
            result["permissions"], {"read": False, "pull_requests": False}
        )

    def test_bad_repo_format_needs_no_http(self) -> None:
        result = github_conn.check_repo("not-a-repo", "good")
        self.assertFalse(result["ok"])
        self.assertIn("owner/name", result["detail"])

    def test_readonly_token_can_read_cannot_open_prs(self) -> None:
        result = _check("readonly")
        self.assertFalse(result["ok"])
        self.assertIn("can read, cannot open PRs", result["detail"])
        self.assertEqual(
            result["permissions"], {"read": True, "pull_requests": False}
        )

    def test_valid_token_is_green_with_default_branch(self) -> None:
        result = _check("valid")
        self.assertTrue(result["ok"])
        self.assertIn("default branch main", result["detail"])
        self.assertEqual(
            result["permissions"], {"read": True, "pull_requests": True}
        )

    def test_missing_base_branch_is_readable(self) -> None:
        result = _check("valid", base_branch="ghost")
        self.assertFalse(result["ok"])
        self.assertIn("ghost", result["detail"])

    def test_unreachable_github_is_readable(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("no route")

        client = httpx.Client(
            transport=_transport(handler),
            base_url="https://api.github.com",
        )
        result = github_conn.check_repo("acme/api", "good", client=client)
        self.assertFalse(result["ok"])
        self.assertIn("cannot reach GitHub", result["detail"])


class ConnectionRepoTests(unittest.TestCase):
    def test_resolves_repo_base_and_token(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            self.assertIsNone(github_conn.connection_repo("acme"))
            connection_store.create_connection(
                "acme",
                "github",
                {"repo": "acme/api", "base_branch": "main"},
                "ghp_secret",
            )
            resolved = github_conn.connection_repo("acme")
            assert resolved is not None
            self.assertEqual(resolved["repo"], "acme/api")
            self.assertEqual(resolved["base"], "main")
            self.assertEqual(resolved["token"], "ghp_secret")


class GithubTestEndpointTests(unittest.TestCase):
    def test_endpoint_returns_live_check_result(self) -> None:
        tmp = _tmp_data()
        _save_system(tmp)
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            with TestClient(app) as client:
                created = client.post(
                    "/api/connections",
                    json={
                        "system_id": "acme",
                        "kind": "github",
                        "config": {"repo": "acme/api"},
                        "secret": "good",
                    },
                )
                connection_id = created.json()["connection"]["id"]
                with patch(
                    "core.connections.github.check_repo",
                    return_value={
                        "ok": False,
                        "detail": "can read, cannot open PRs: test",
                        "permissions": {
                            "read": True,
                            "pull_requests": False,
                        },
                    },
                ) as mocked:
                    tested = client.post(
                        f"/api/connections/{connection_id}/test"
                    )
                mocked.assert_called_once_with("acme/api", "good", "")
                self.assertFalse(tested.json()["ok"])
                self.assertEqual(
                    tested.json()["permissions"],
                    {"read": True, "pull_requests": False},
                )
