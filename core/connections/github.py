"""GitHub repo connections: live repo/permission/branch checks (J-R2).

`check_repo` is what the /connect "Test" button calls: it verifies the
repo exists, the token can read it, the base branch exists, and the token
can write — the write probe creates and immediately deletes a throwaway
ref, so the check leaves no trace. `connection_repo` resolves a system's
github connection to (repo, base, token) for the fix pipeline (J-R3);
tokens from it must never be logged or returned by the API.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx

from core.connections import store as connection_store

API = "https://api.github.com"
API_VERSION = "2022-11-28"
TIMEOUT_S = 15.0

#: GitHub top-language → `/connect` language (languages §1.1, L-J0).
_SUPPORTED = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "java": "java",
    "kotlin": "kotlin",
    "go": "go",
    "rust": "rust",
    "php": "php",
}
def _tree_paths(http: Any, repo: str, sha: str) -> List[str]:
    """Repo file list for language detection; [] when it fails."""
    try:
        response = http.get(
            f"/repos/{repo}/git/trees/{sha}", params={"recursive": "1"}
        )
    except httpx.HTTPError:
        return []
    if response.status_code != 200:
        return []
    try:
        body = response.json()
    except ValueError:
        return []
    return [
        item["path"]
        for item in body.get("tree", [])
        if item.get("type") == "blob" and item.get("path")
    ]


def _detect_language(
    http: Any, repo: str, sha: str, gh_lang: str
) -> tuple:
    """(language, autofix): detect_repo on the tree, rollup as fallback.

    `language` names the repo even when unsupported ("/connect shows
    alerts-and-rollback-only"); `autofix` is True only once an adapter
    for it exists. Import is deferred: lang pulls in core.ingest.
    """
    from core.repo_fix.lang import by_name, detect_repo

    detected = detect_repo(_tree_paths(http, repo, sha))
    if detected:
        language = detected[0][0]
    else:
        language = _SUPPORTED.get(gh_lang, gh_lang or None)
    return language, bool(language) and by_name(language) is not None


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
        repo_meta = got.json()
        default_branch = str(repo_meta.get("default_branch", "main"))
        # Languages §3 (L-J0): the rollup is the fallback; the tree
        # detection below decides whenever the tree call succeeds.
        gh_lang = str(repo_meta.get("language") or "").strip().lower()
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
            language, autofix = _detect_language(http, repo, sha, gh_lang)
            return {
                "ok": True,
                "detail": f"connected · default branch {default_branch} · "
                "write verified (throwaway ref created and deleted)",
                "permissions": {"read": True, "pull_requests": True},
                "language": language,
                "autofix": autofix,
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


def connection_repo(
    system_id: str, org_id: str = ""
) -> Optional[Dict[str, str]]:
    """A system's github connection as {connection_id, repo, base, token}.

    None when no github connection (or no token) is stored. The token is
    for outbound GitHub calls only — never log or return it.
    Hosted callers pass the org (per-org Postgres rows, decrypted with the
    org's data key); self-hosted reads the file store as before.
    """
    import os

    if os.environ.get("DATABASE_URL", "").strip() and org_id:
        from core.commerce import repo as repo_module

        store = repo_module.get_store().scoped(org_id)
        for connection in store.list_connections(org_id, system_id):
            if connection.get("kind") != "github":
                continue
            config = connection.get("config") or {}
            repo = str(config.get("repo", "")).strip()
            base = str(config.get("base_branch", "")).strip()
            token = store.get_connection_secret(org_id, connection["id"])
            if repo and token:
                return {
                    "connection_id": connection["id"],
                    "repo": repo,
                    "base": base,
                    "token": token,
                }
        return None
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
