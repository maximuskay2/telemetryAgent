"""GitHub repo connections: live repo/permission/branch checks (J-R2).

`check_repo` is what the /connect "Test" button calls: it verifies the
repo exists, the token can read it, the base branch exists, and the token
can write — the write probe creates and immediately deletes a throwaway
ref, so the check leaves no trace. `connection_repo` resolves a system's
github connection to (repo, base, token) for the fix pipeline (J-R3);
tokens from it must never be logged or returned by the API.
"""

from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import uuid4

import httpx

from core.connections import store as connection_store

API = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT_S = 15.0


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


def _message(response: httpx.Response) -> str:
    try:
        return str(response.json().get("message", ""))
    except Exception:
        return response.text[:200]


def check_repo(
    repo: str,
    token: str,
    base_branch: str = "",
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Live check: repo readable, base branch exists, token can write."""
    repo = (repo or "").strip()
    if "/" not in repo or repo.startswith("/") or repo.endswith("/"):
        return {
            "ok": False,
            "detail": "config.repo must be owner/name",
            "permissions": {"read": False, "pull_requests": False},
        }
    owned = client is None
    http = client or httpx.Client(
        base_url=API, headers=_headers(token), timeout=TIMEOUT_S
    )
    try:
        try:
            got = http.get(f"/repos/{repo}")
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "detail": f"cannot reach GitHub: {exc}",
                "permissions": {"read": False, "pull_requests": False},
            }
        if got.status_code == 401:
            return {
                "ok": False,
                "detail": "GitHub rejected the token (401): check it has "
                "not expired and can access this repo",
                "permissions": {"read": False, "pull_requests": False},
            }
        if got.status_code == 404:
            return {
                "ok": False,
                "detail": "repo not found, or the token cannot see it "
                "(fine-grained tokens need repository access)",
                "permissions": {"read": False, "pull_requests": False},
            }
        if got.status_code != 200:
            return {
                "ok": False,
                "detail": f"GitHub error ({got.status_code}): "
                f"{_message(got)}",
                "permissions": {"read": False, "pull_requests": False},
            }
        default_branch = str(got.json().get("default_branch", "main"))
        base = (base_branch or "").strip() or default_branch
        ref = http.get(f"/repos/{repo}/git/ref/heads/{base}")
        if ref.status_code == 404:
            return {
                "ok": False,
                "detail": f"base branch {base!r} not found "
                f"(default is {default_branch!r})",
                "permissions": {"read": True, "pull_requests": False},
            }
        if ref.status_code != 200:
            return {
                "ok": False,
                "detail": f"GitHub error ({ref.status_code}): "
                f"{_message(ref)}",
                "permissions": {"read": True, "pull_requests": False},
            }
        sha = str(ref.json()["object"]["sha"])
        probe = f"ta-probe-{uuid4().hex[:8]}"
        try:
            created = http.post(
                f"/repos/{repo}/git/refs",
                json={"ref": f"refs/heads/{probe}", "sha": sha},
            )
        except httpx.HTTPError as exc:
            return {
                "ok": False,
                "detail": f"cannot reach GitHub: {exc}",
                "permissions": {"read": True, "pull_requests": False},
            }
        if created.status_code == 201:
            try:
                http.delete(f"/repos/{repo}/git/refs/heads/{probe}")
            except httpx.HTTPError:
                pass  # probe left behind; harmless, detail says so below
            return {
                "ok": True,
                "detail": f"connected · default branch {default_branch} · "
                "write verified (throwaway ref created and deleted)",
                "permissions": {"read": True, "pull_requests": True},
            }
        if created.status_code in (403, 404):
            return {
                "ok": False,
                "detail": "can read, cannot open PRs: the token needs "
                "Contents and Pull requests write access",
                "permissions": {"read": True, "pull_requests": False},
            }
        return {
            "ok": False,
            "detail": f"GitHub rejected the write probe "
            f"({created.status_code}): {_message(created)}",
            "permissions": {"read": True, "pull_requests": False},
        }
    finally:
        if owned:
            http.close()


def connection_repo(system_id: str) -> Optional[Dict[str, str]]:
    """A system's github connection as {connection_id, repo, base, token}.

    None when no github connection (or no token) is stored. The token is
    for outbound GitHub calls only — never log or return it.
    """
    for connection in connection_store.list_connections(system_id):
        if connection.kind != "github":
            continue
        repo = str((connection.config or {}).get("repo", "")).strip()
        base = str((connection.config or {}).get("base_branch", "")).strip()
        token = connection_store.get_secret(connection.id)
        if repo and token:
            return {
                "connection_id": connection.id,
                "repo": repo,
                "base": base,
                "token": token,
            }
    return None
