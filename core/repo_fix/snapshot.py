"""Snapshot: resolve the commit, fetch + filter the tarball (J-R3 step 2).

The tarball is taken at the failing commit when ingest knew it, else base
HEAD. Download aborts past 50 MB; filtering drops `.git`, `node_modules`,
caches, files over 2 MB and detected binaries, strips the top-level dir,
and refuses unsafe entries — the sandbox receives a clean, flat tree.
"""

from __future__ import annotations

import io
import tarfile
import time
from typing import Any, Dict, List, Optional

import httpx

MAX_TARBALL_BYTES = 50 * 1024 * 1024
MAX_MEMBER_BYTES = 2 * 1024 * 1024

DROP_DIRS = (".git/", "node_modules/", "__pycache__/", ".venv/", "venv/")
DROP_SUFFIXES = (".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe")


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


class SnapshotTooBig(RuntimeError):
    """The repo tarball exceeded the size cap (draft-PR path)."""


class SnapshotFailed(RuntimeError):
    """The commit/branch could not be resolved or downloaded."""


def resolve_commit(
    repo: str,
    token: str,
    commit: str,
    base: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, str]:
    """Failing commit when usable, else base HEAD. Returns {sha, source}."""
    owned = client is None
    http = client or httpx.Client(
        base_url="https://api.github.com", headers=_headers(token),
        timeout=30.0,
    )
    try:
        if (commit or "").strip():
            response = http.get(f"/repos/{repo}/commits/{commit.strip()}")
            if response.status_code == 200:
                return {
                    "sha": str(response.json()["sha"]),
                    "source": f"failing commit {commit.strip()[:12]}",
                }
        branch = (base or "").strip()
        if not branch:
            repo_info = http.get(f"/repos/{repo}")
            if repo_info.status_code != 200:
                raise SnapshotFailed(
                    f"cannot read repo {repo}: {repo_info.status_code}"
                )
            branch = str(repo_info.json().get("default_branch", "main"))
        ref = http.get(f"/repos/{repo}/git/ref/heads/{branch}")
        if ref.status_code != 200:
            raise SnapshotFailed(
                f"cannot resolve branch {branch}: {ref.status_code}"
            )
        return {
            "sha": str(ref.json()["object"]["sha"]),
            "source": f"base branch {branch}",
        }
    finally:
        if owned:
            http.close()


def fetch_tarball(
    repo: str,
    token: str,
    sha: str,
    client: Optional[httpx.Client] = None,
) -> bytes:
    """Download the tarball at `sha`; abort past 50 MB."""
    owned = client is None
    http = client or httpx.Client(
        base_url="https://api.github.com", headers=_headers(token),
        timeout=120.0, follow_redirects=True,
    )
    try:
        with http.stream("GET", f"/repos/{repo}/tarball/{sha}") as response:
            if response.status_code != 200:
                raise SnapshotFailed(
                    f"tarball fetch failed ({response.status_code})"
                )
            chunks: List[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > MAX_TARBALL_BYTES:
                    raise SnapshotTooBig(
                        f"repo tarball exceeds "
                        f"{MAX_TARBALL_BYTES // 1024 // 1024} MB"
                    )
                chunks.append(chunk)
            return b"".join(chunks)
    finally:
        if owned:
            http.close()


def _looks_binary(sample: bytes) -> bool:
    return b"\x00" in sample


def filter_snapshot(tarball: bytes) -> bytes:
    """Drop junk + binaries, strip the top dir, refuse unsafe entries."""
    incoming = tarfile.open(fileobj=io.BytesIO(tarball))
    kept: List[Any] = []
    tops = set()
    for member in incoming.getmembers():
        name = member.name
        if not name or name.startswith(("/", "\\")):
            continue
        parts = name.split("/")
        if ".." in parts:
            continue
        tops.add(parts[0])
        kept.append(member)
    # GitHub tarballs nest everything under one top dir; strip it when
    # every entry shares it, else keep names as they are.
    strip = len(tops) == 1 and len(kept) > 1
    outgoing = io.BytesIO()
    with tarfile.open(fileobj=outgoing, mode="w:gz") as tar:
        for member in kept:
            name = member.name
            if strip:
                name = "/".join(name.split("/")[1:])
                if not name:
                    continue
            lowered = name.lower()
            if lowered.startswith(DROP_DIRS) or "/.git/" in lowered:
                continue
            if lowered.endswith(DROP_SUFFIXES):
                continue
            if not (member.isfile() or member.isdir()):
                continue
            if member.isfile():
                if member.size > MAX_MEMBER_BYTES:
                    continue
                handle = incoming.extractfile(member)
                if handle is None:
                    continue
                data = handle.read()
                if _looks_binary(data[:8192]):
                    continue
                info = tarfile.TarInfo(name=name)
                info.size = len(data)
                info.mtime = int(member.mtime or time.time())
                info.mode = 0o644
                tar.addfile(info, io.BytesIO(data))
            else:
                info = tarfile.TarInfo(name=name)
                info.type = tarfile.DIRTYPE
                info.mtime = int(member.mtime or time.time())
                info.mode = 0o755
                tar.addfile(info)
    incoming.close()
    return outgoing.getvalue()


def python_files(paths: List[str]) -> List[str]:
    return [path for path in paths if path.endswith(".py")]


def has_requirements(paths: List[str]) -> bool:
    names = {path.rsplit("/", 1)[-1] for path in paths}
    return "requirements.txt" in names


def has_packaging(paths: List[str]) -> bool:
    names = {path.rsplit("/", 1)[-1] for path in paths}
    return bool(names & {"setup.py", "setup.cfg", "pyproject.toml"})
