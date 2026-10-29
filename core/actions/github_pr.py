"""Open a real GitHub PR for a verified software fix (Day 4).

Uses the GitHub REST git-database API with httpx (already a dependency):
blobs -> tree -> commit -> branch ref -> pull request. One commit holds
both the patch and its regression test.
"""

from __future__ import annotations

import base64
import os
import re
import time
from typing import Mapping, NoReturn, Optional
from uuid import uuid4

import httpx

from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import GeneratedPatch

API = "https://api.github.com"
API_VERSION = "2022-11-28"
MAX_BODY_OUTPUT_CHARS = 4000

#: R2: within this window after a fix PR, further runs reuse its URL.
PR_REUSE_WINDOW_S = 600.0
_last_pr_at = 0.0
_last_pr_url: Optional[str] = None


def _token(explicit: Optional[str] = None) -> str:
    token = explicit or os.environ.get("GITHUB_TOKEN", "")
    if not token.strip():
        raise RuntimeError(
            "Set GITHUB_TOKEN to a fine-grained token with contents and "
            "pull_requests write access on the demo target repo."
        )
    return token


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": API_VERSION,
    }


def _fail(response: httpx.Response, context: str) -> NoReturn:
    status = response.status_code
    try:
        detail = response.json().get("message", "")
    except Exception:
        detail = response.text[:200]
    if status == 401:
        raise RuntimeError(f"GitHub rejected GITHUB_TOKEN (401) during {context}.")
    if status == 403:
        raise RuntimeError(
            f"GitHub forbade the request (403) during {context}: {detail}. "
            "Check token scopes and rate limits."
        )
    if status == 404:
        raise RuntimeError(
            f"GitHub resource not found (404) during {context}: {detail}. "
            "Check GITHUB_DEMO_REPO and the token's repository access."
        )
    if status == 422:
        raise RuntimeError(f"GitHub rejected the request (422) during {context}: {detail}.")
    raise RuntimeError(f"GitHub request failed ({status}) during {context}: {detail}.")


def _ref_exists(client: httpx.Client, repo: str, branch: str) -> bool:
    response = client.get(f"/repos/{repo}/git/ref/heads/{branch}")
    if response.status_code == 200:
        return True
    if response.status_code == 404:
        return False
    _fail(response, f"checking branch {branch}")


def _pick_branch(client: httpx.Client, repo: str, stem: str) -> str:
    if not _ref_exists(client, repo, stem):
        return stem
    for suffix in range(2, 10):
        candidate = f"{stem}-{suffix}"
        if not _ref_exists(client, repo, candidate):
            return candidate
    raise RuntimeError(f"Could not find a free branch name under {stem!r}.")


def open_pr(
    *,
    repo: str,
    base: str,
    branch: str,
    title: str,
    body: str,
    files: Mapping[str, str],
    token: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    labels: Optional[list] = None,
    draft: bool = False,
) -> str:
    """Create one commit with `files` on a new branch and open a PR.

    Returns the PR's HTML URL. `client` is injectable for tests; when omitted
    a short-lived client against api.github.com is used. `labels` are applied
    best-effort (a missing label never fails the PR); `draft` falls back to
    a normal PR when the repo rejects drafts.
    """
    if not files:
        raise ValueError("files must map at least one path to its content")
    owned = client is None
    http = client or httpx.Client(
        base_url=API, headers=_headers(_token(token)), timeout=30.0
    )
    try:
        base_ref = http.get(f"/repos/{repo}/git/ref/heads/{base}")
        if base_ref.status_code != 200:
            _fail(base_ref, f"reading base branch {base}")
        base_sha = base_ref.json()["object"]["sha"]

        branch = _pick_branch(http, repo, branch)

        blobs = []
        for path, content in files.items():
            blob = http.post(
                f"/repos/{repo}/git/blobs",
                json={
                    "content": base64.b64encode(content.encode()).decode(),
                    "encoding": "base64",
                },
            )
            if blob.status_code != 201:
                _fail(blob, f"creating blob for {path}")
            blobs.append(
                {"path": path, "mode": "100644", "type": "blob", "sha": blob.json()["sha"]}
            )

        tree = http.post(
            f"/repos/{repo}/git/trees",
            json={"base_tree": base_sha, "tree": blobs},
        )
        if tree.status_code != 201:
            _fail(tree, "creating tree")
        commit = http.post(
            f"/repos/{repo}/git/commits",
            json={"message": title, "tree": tree.json()["sha"], "parents": [base_sha]},
        )
        if commit.status_code != 201:
            _fail(commit, "creating commit")

        ref = http.post(
            f"/repos/{repo}/git/refs",
            json={"ref": f"refs/heads/{branch}", "sha": commit.json()["sha"]},
        )
        if ref.status_code != 201:
            _fail(ref, f"creating branch {branch}")

        payload: dict = {
            "title": title,
            "head": branch,
            "base": base,
            "body": body,
        }
        if draft:
            payload["draft"] = True
        pr = http.post(f"/repos/{repo}/pulls", json=payload)
        if pr.status_code == 422 and draft:
            pr = http.post(f"/repos/{repo}/pulls", json={**payload, "draft": False})
        if pr.status_code != 201:
            _fail(pr, "opening pull request")
        opened = pr.json()
        if labels:
            _apply_labels(http, repo, opened.get("number"), labels)
        return opened["html_url"]
    finally:
        if owned:
            http.close()


def _apply_labels(
    http: httpx.Client, repo: str, number: object, labels: list
) -> None:
    """Best-effort label apply; never raises (labels are advisory)."""
    try:
        if not isinstance(number, int):
            return
        names = [str(label) for label in labels if str(label).strip()]
        if not names:
            return
        for name in names:
            created = http.post(
                f"/repos/{repo}/labels",
                json={"name": name, "color": "0E786D"},
            )
            if created.status_code not in (200, 201, 422):
                return
        http.patch(
            f"/repos/{repo}/issues/{number}", json={"labels": names}
        )
    except Exception:
        return


def open_pr_for_branch(
    repo: str,
    branch: str,
    token: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> Optional[dict]:
    """Open PR from `branch`, if any: {number, html_url} (J-R3 dedupe)."""
    owned = client is None
    http = client or httpx.Client(
        base_url=API, headers=_headers(_token(token)), timeout=30.0
    )
    try:
        owner = repo.split("/")[0]
        response = http.get(
            f"/repos/{repo}/pulls",
            params={"head": f"{owner}:{branch}", "state": "open"},
        )
        if response.status_code != 200:
            _fail(response, f"listing PRs for {branch}")
        items = response.json()
        if not items:
            return None
        return {
            "number": items[0]["number"],
            "html_url": items[0]["html_url"],
        }
    finally:
        if owned:
            http.close()


def comment_on_pr(
    repo: str,
    number: int,
    body: str,
    token: Optional[str] = None,
    client: Optional[httpx.Client] = None,
) -> None:
    """Append a comment to an existing PR/issue (J-R3 dedupe path)."""
    owned = client is None
    http = client or httpx.Client(
        base_url=API, headers=_headers(_token(token)), timeout=30.0
    )
    try:
        response = http.post(
            f"/repos/{repo}/issues/{number}/comments", json={"body": body}
        )
        if response.status_code != 201:
            _fail(response, f"commenting on PR #{number}")
    finally:
        if owned:
            http.close()


def open_fix_pr(
    *,
    diagnosis: Diagnosis,
    patch: GeneratedPatch,
    verification_feedback: str,
    attempts: int,
    model_used: str,
    repo: Optional[str] = None,
    base: Optional[str] = None,
    branch: Optional[str] = None,
    token: Optional[str] = None,
    client: Optional[httpx.Client] = None,
    code_path: str = "solution.py",
    test_path: str = "test_solution.py",
) -> str:
    """Loop-compatible wrapper: build the PR title/body/files and open it."""
    global _last_pr_at, _last_pr_url
    repo = repo or os.environ.get("GITHUB_DEMO_REPO", "")
    if not repo.strip() or "/" not in repo:
        raise RuntimeError("Set GITHUB_DEMO_REPO to the demo target as owner/repo.")
    if (
        client is None
        and _last_pr_url is not None
        and time.time() - _last_pr_at < PR_REUSE_WINDOW_S
    ):
        # R2: one demo storm must not open a PR per run; reuse the fresh one.
        # Explicit clients (tests, scripts) always go through.
        return _last_pr_url
    base = base or os.environ.get("GITHUB_BASE_BRANCH", "main")
    branch = branch or f"telemetry-agent/fix-{uuid4().hex[:8]}"
    output = (verification_feedback or "")[-MAX_BODY_OUTPUT_CHARS:]
    title = f"fix: {diagnosis.summary[:100]}"
    body = (
        f"## TelemetryAgent verified fix\n\n"
        f"- **Diagnosis:** {diagnosis.summary}\n"
        f"- **Likely cause:** {diagnosis.likely_cause}\n"
        f"- **Attempts:** {attempts}\n"
        f"- **Generation model:** {model_used}\n\n"
        f"### Verification (pytest in Modal Sandbox)\n\n```\n{output}\n```\n"
    )
    url = open_pr(
        repo=repo,
        base=base,
        branch=branch,
        title=title,
        body=body,
        files={
            code_path: patch.patch_code,
            test_path: retarget_imports(patch.test_code, code_path),
        },
        token=token,
        client=client,
    )
    if client is None:
        _last_pr_at = time.time()
        _last_pr_url = url
    return url


def retarget_imports(test_code: str, code_path: str) -> str:
    """Point a test written against `solution` at the module the PR changes.

    Generated tests import `solution` (the sandbox filename); in the target
    repo the patch lands as `code_path`, so the test must import that module.
    """
    module = os.path.splitext(os.path.basename(code_path))[0]
    if module == "solution":
        return test_code
    test_code = re.sub(r"^(\s*)from solution import", rf"\1from {module} import",
                       test_code, flags=re.MULTILINE)
    test_code = re.sub(r"^(\s*)import solution as ", rf"\1import {module} as ",
                       test_code, flags=re.MULTILINE)
    return re.sub(r"^(\s*)import solution\s*$", rf"\1import {module} as solution",
                  test_code, flags=re.MULTILINE)
