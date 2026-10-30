"""Locate: frames → repo files at a commit (J-R3 step 1).

Tree paths come from the GitHub git-trees API; frame files (absolute,
container-local) match by suffix. The top 1–3 files with ±40 lines of
context go to the model. Without frames, keyword-ranked files go to the
model, which picks at most 5.
"""

from __future__ import annotations

import base64
from typing import Any, Callable, Dict, List, Optional

import httpx

CONTEXT_RADIUS = 40
MAX_LOCATED_FILES = 3
MAX_PICKED_FILES = 5
MAX_FILE_BYTES = 200 * 1024


def _headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def fetch_tree(
    repo: str,
    token: str,
    sha: str,
    client: Optional[httpx.Client] = None,
) -> Dict[str, Any]:
    """Repo file list at `sha`; {paths, truncated}."""
    owned = client is None
    http = client or httpx.Client(
        base_url="https://api.github.com", headers=_headers(token),
        timeout=30.0,
    )
    try:
        response = http.get(
            f"/repos/{repo}/git/trees/{sha}", params={"recursive": "1"}
        )
    finally:
        if owned:
            http.close()
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub tree fetch failed ({response.status_code}): "
            f"{response.text[:200]}"
        )
    body = response.json()
    paths = [
        item["path"]
        for item in body.get("tree", [])
        if item.get("type") == "blob" and item.get("path")
    ]
    return {"paths": paths, "truncated": bool(body.get("truncated", False))}


def _suffixes(frame_file: str) -> List[str]:
    parts = [part for part in frame_file.replace("\\", "/").split("/") if part]
    return ["/".join(parts[i:]) for i in range(len(parts))]


def _suffix_match(frame_file: str, paths: List[str]) -> Optional[str]:
    """First (longest) suffix of the frame file present in the repo."""
    for suffix in _suffixes(frame_file):
        if suffix in paths:
            return suffix
    return None


def match_frames(
    frames: List[Any],
    paths: List[str],
    map_frame: Optional[Callable[[str, str, List[str]], Optional[str]]] = None,
) -> List[Dict[str, Any]]:
    """Match each frame to a repo path; best (deepest) first, ≤ 3 files.

    `map_frame` is the language adapter's mapper; without one, plain
    suffix matching (the Python behaviour).
    """
    if map_frame is None:
        def map_frame(name: str, func: str, known: List[str]) -> Optional[str]:
            _ = func
            return _suffix_match(name, known)
    by_path: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for frame in frames:
        name = frame.file if hasattr(frame, "file") else frame.get("file", "")
        lineno = frame.line if hasattr(frame, "line") else frame.get("line", 0)
        func = frame.func if hasattr(frame, "func") else frame.get("func", "")
        hit = map_frame(str(name), str(func or ""), paths)
        if hit is not None and hit not in by_path:
            by_path[hit] = {"path": hit, "line": lineno}
            order.append(hit)
    ranked = sorted(
        (by_path[path] for path in order),
        key=lambda item: -len(item["path"]),
    )
    return ranked[:MAX_LOCATED_FILES]


def read_file_at(
    repo: str,
    token: str,
    sha: str,
    path: str,
    client: Optional[httpx.Client] = None,
) -> str:
    """File content at `sha` via the contents API (skips huge files)."""
    owned = client is None
    http = client or httpx.Client(
        base_url="https://api.github.com", headers=_headers(token),
        timeout=30.0,
    )
    try:
        response = http.get(
            f"/repos/{repo}/contents/{path}", params={"ref": sha}
        )
    finally:
        if owned:
            http.close()
    if response.status_code != 200:
        raise RuntimeError(
            f"GitHub contents fetch failed ({response.status_code}) "
            f"for {path}: {response.text[:200]}"
        )
    body = response.json()
    if int(body.get("size", 0)) > MAX_FILE_BYTES:
        raise ValueError(f"{path} exceeds the {MAX_FILE_BYTES} byte cap")
    raw = base64.b64decode(body.get("content", "") or "")
    return raw.decode("utf-8", errors="replace")


def context_for(content: str, lineno: int, radius: int = CONTEXT_RADIUS) -> str:
    """±radius numbered lines around `lineno` (1-based)."""
    lines = content.splitlines()
    if not lines:
        return ""
    index = max(0, min(len(lines) - 1, lineno - 1))
    start = max(0, index - radius)
    stop = min(len(lines), index + radius + 1)
    width = len(str(stop))
    return "\n".join(
        f"{number:>{width}}: {lines[number - 1]}"
        for number in range(start + 1, stop + 1)
    )


def keyword_rank(paths: List[str], keywords: List[str]) -> List[str]:
    """Repo paths ranked by keyword hits (filename beats directory)."""
    scored = []
    for path in paths:
        lowered = path.lower()
        name = lowered.rsplit("/", 1)[-1]
        score = 0
        for keyword in keywords:
            word = keyword.lower()
            if not word:
                continue
            if word in name:
                score += 3
            elif word in lowered:
                score += 1
        if score:
            scored.append((path, score))
    scored.sort(key=lambda item: (-item[1], item[0]))
    return [path for path, _ in scored]


def pick_files_no_frames(
    paths: List[str],
    keywords: List[str],
    chooser: Callable[[List[str]], List[str]],
) -> List[str]:
    """Model picks ≤ 5 files from the keyword-ranked top 20 (or fewer)."""
    ranked = keyword_rank(paths, keywords)[:20]
    if not ranked:
        return []
    try:
        picked = chooser(ranked) or []
    except Exception:
        picked = ranked[:MAX_PICKED_FILES]
    known = [path for path in picked if path in paths]
    return known[:MAX_PICKED_FILES]
