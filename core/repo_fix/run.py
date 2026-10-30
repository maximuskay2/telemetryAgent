"""Repo-fix orchestrator: production error → verified PR (J-R3).

`maybe_trigger` (called from the ingest routes) starts `run_repo_fix` in the
background for armed production systems with a github connection and a
parsed traceback. The run locates the code, snapshots the repo, reproduces
in a sandbox, patches, proves no regressions, and opens one PR per
fingerprint — commenting on the existing PR when the error repeats.

Only ever runs for `is_production(profile)`; the demo `target="inventory"`
path is untouched. All `apps.api.main` imports are deferred (function
level): routers load before main finishes executing.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from core.actions import mitigate as mitigate_actions
from core.connections import github as github_conn
from core.connections import is_production
from core.repo_fix import generate as repo_generate
from core.repo_fix import locate as repo_locate
from core.repo_fix import snapshot as repo_snapshot
from core.repo_fix.lang import by_name as _adapter_by_name
from core.repo_fix.lang import parse as _registry_parse
from core.schemas.diagnosis import Diagnosis
from core.schemas.remediation import (
    ExecutionResult,
    RunVerification,
    VerifyAttempt,
)

log = logging.getLogger(__name__)

REPRO_ATTEMPTS = 3
PATCH_ATTEMPTS = 2
REPRO_TIMEOUT_S = 300
#: Default adapter (python); the pipeline threads the per-run adapter
#: since L-J2, this stays for the legacy shims + fallbacks.
ADAPTER = _adapter_by_name("python")
assert ADAPTER is not None  # lang/python.py must register
#: Legacy alias for the frozen tests; the pipeline uses adapter commands.
#: (V1: derived from the registry-resolved adapter, not its module.)
PYTEST = ADAPTER.suite_cmd([])
PR_LABEL = "telemetry-agent"
MAX_BODY_CHARS = 4000

#: Fingerprints with a run in flight right now.
_active: set = set()

#: fingerprint -> last epoch seconds we commented on its PR.
_last_repeat_comment: Dict[str, float] = {}
REPEAT_COMMENT_EVERY_S = 3600.0


def branch_for(fingerprint: str) -> str:
    return f"telemetry-agent/fix-{fingerprint[:12]}"


def reset_run_state() -> None:
    """Clear in-flight + throttle state (tests only)."""
    _active.clear()
    _last_repeat_comment.clear()


def parse_pytest(text: str) -> Dict[str, Any]:
    """Legacy shim for the frozen tests; the pipeline uses the adapter."""
    result = ADAPTER.parse_results(text, "", lambda _path: None)
    return {
        "passed": result.passed,
        "failed": result.failed,
        "failed_ids": result.failed_ids,
        "total": result.total,
    }


def keywords_for(exc_type: str, exc_value: str, frames: List[Any]) -> List[str]:
    words: List[str] = []
    for token in re.split(r"[^A-Za-z0-9]+", f"{exc_type} {exc_value}"):
        if len(token) > 2 and token.lower() not in ("error", "exception"):
            words.append(token)
    for frame in frames[:3]:
        name = frame.file if hasattr(frame, "file") else frame.get("file", "")
        base = str(name).replace("\\", "/").rsplit("/", 1)[-1]
        stem = base.rsplit(".", 1)[0]
        if len(stem) > 2:
            words.append(stem)
    seen = set()
    ordered = []
    for word in words:
        if word.lower() not in seen:
            seen.add(word.lower())
            ordered.append(word)
    return ordered[:10]


def should_trigger(
    profile: Any, decision: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """Trigger context for a production traceback, or None to skip."""
    if profile is None or not is_production(profile):
        return None
    if getattr(profile, "status", "") != "armed":
        return None
    if decision.get("decision") not in ("act", "observe"):
        return None
    # Parse-based, not rule-based: a traceback mentioning "deadlock" is
    # still a traceback (rules match deadlock first). Frames are required:
    # log lines like uvicorn's "ERROR:    Exception in ASGI application"
    # parse as `ERROR: ...` and precede the real traceback, which would
    # then be skipped as an in-flight fingerprint.
    window = decision.get("window", "") or ""
    if not window.strip():
        return None
    try:
        found = _registry_parse(window)
    except Exception:
        return None
    if found is None or not found[1].frames:
        return None
    adapter_name = found[0].name
    language = found[1].language
    fingerprint = decision.get("fingerprint", "") or ""
    if not fingerprint or fingerprint in _active:
        return None
    resolved = github_conn.connection_repo(
        getattr(profile, "system_id", "")
    )
    if resolved is None:
        return None
    return {
        "repo_info": resolved,
        "fingerprint": fingerprint,
        "traceback_text": window,
        "commit": decision.get("commit", "") or "",
        # L-J2: the trace picks the adapter; _pipeline confirms the repo
        # matches it (`detect`) once the tree is fetched. The `detect`
        # check lives there (not here) because it needs network and this
        # stays sync for the frozen trigger tests.
        "adapter_name": adapter_name,
        "language": language,
    }


async def maybe_trigger(
    system_id: str,
    decisions: List[Dict[str, Any]],
    commit: str,
) -> List[str]:
    """Fire-and-forget repo runs for triggerable decisions; run_ids."""
    from core.setup import store as setup_store

    profile = setup_store.get_profile(system_id)
    started: List[str] = []
    for decision in decisions:
        decision = {**decision, "commit": commit}
        ctx = should_trigger(profile, decision)
        if ctx is None:
            continue
        run_id = uuid4().hex[:12]
        _active.add(ctx["fingerprint"])
        # J-R4: a confirmed production incident proposes a rollback window
        # (approve-to-run: it expires unless a human approves). Best effort:
        # policy/paused/rate refusals just mean no window opens.
        try:
            await mitigate_actions.propose(
                system_id, run_id, "rollback", auto_apply=False
            )
        except Exception as exc:
            log.warning("rollback proposal skipped: %s", exc)
        task = asyncio.create_task(
            run_repo_fix(
                run_id=run_id,
                system_id=system_id,
                gate=dict(decision),
                **ctx,
            )
        )
        task.add_done_callback(_log_task_error)
        started.append(run_id)
    return started


def _log_task_error(task: "asyncio.Task") -> None:
    try:
        task.result()
    except Exception as exc:  # never let a background run crash the loop
        log.exception("repo-fix background task failed: %s", exc)


def _emit(
    run_id: str,
    step: str,
    attempt: int,
    model: str,
    status: str,
    message: str,
    detail: str = "",
) -> None:
    from apps.api.main import _record_step, hub
    from core.schemas.events import AgentStep

    entry = AgentStep(
        step=step,
        attempt=attempt,
        model=model,
        status=status,
        message=message,
        run_id=run_id,
        domain="software",
        source="ingest",
        detail=detail[:500],
    )
    _record_step(entry)
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(hub.broadcast(entry))


def _remember_run(run_id: str, entry: Dict[str, Any]) -> None:
    from apps.api.main import _remember, software_runs

    _remember(software_runs, run_id, entry)


def _pr_body(
    *,
    diagnosis: Diagnosis,
    fingerprint: str,
    sha: str,
    files: List[str],
    repro_fail: str,
    repro_pass: str,
    suite: Dict[str, Any],
    note: str,
) -> str:
    evidence = (
        f"### Proof (sandbox pytest)\n\n"
        f"Repro fails on original:\n```\n{repro_fail[-1500:]}\n```\n\n"
        f"Repro passes on patch:\n```\n{repro_pass[-1500:]}\n```\n\n"
        f"Suite: {suite['passed']} passed, {suite['failed']} failed, "
        f"{suite['new_failures']} new failures."
    )
    body = (
        f"## TelemetryAgent verified fix\n\n"
        f"- **Diagnosis:** {diagnosis.summary}\n"
        f"- **Likely cause:** {diagnosis.likely_cause}\n"
        f"- **Fingerprint:** `{fingerprint}`\n"
        f"- **Commit:** `{sha[:12]}`\n"
        f"- **Files:** {', '.join(f'`{path}`' for path in files)}\n"
        + (f"- **Note:** {note}\n" if note else "")
        + f"\n{evidence}\n"
    )
    return body[:MAX_BODY_CHARS]


def _draft_body(
    *,
    diagnosis: Diagnosis,
    fingerprint: str,
    sha: str,
    reason: str,
    repro_test: str,
) -> str:
    body = (
        f"## TelemetryAgent diagnosis (draft — no verified fix)\n\n"
        f"- **Diagnosis:** {diagnosis.summary}\n"
        f"- **Likely cause:** {diagnosis.likely_cause}\n"
        f"- **Fingerprint:** `{fingerprint}`\n"
        f"- **Commit:** `{sha[:12]}`\n"
        f"- **Why no fix:** {reason}\n"
    )
    if repro_test:
        body += "\nThe failing repro test is included; the patch is left to a human.\n"
    return body[:MAX_BODY_CHARS]


async def run_repo_fix(
    *,
    run_id: str,
    system_id: str,
    repo_info: Dict[str, str],
    fingerprint: str,
    traceback_text: str,
    commit: str,
    gate: Dict[str, Any],
    http_client: Any = None,
    sandbox_factory: Optional[Callable[[bytes], Any]] = None,
    diagnose_fn: Optional[Callable[..., Diagnosis]] = None,
    adapter_name: str = "python",
    language: str = "python",
) -> Dict[str, Any]:
    """Full pipeline; always resolves the run entry (never raises)."""
    from apps.api.main import hub
    from core.schemas.events import SimEvent

    repo = repo_info["repo"]
    base = repo_info.get("base", "")
    token = repo_info.get("token", "")
    adapter = _adapter_by_name(adapter_name) or ADAPTER
    outcome: Dict[str, Any] = {"run_id": run_id, "status": "FAIL"}
    try:
        outcome = await _run(
            run_id=run_id,
            system_id=system_id,
            repo=repo,
            base=base,
            token=token,
            fingerprint=fingerprint,
            traceback_text=traceback_text,
            commit=commit,
            gate=gate,
            http_client=http_client,
            sandbox_factory=sandbox_factory,
            diagnose_fn=diagnose_fn,
            adapter=adapter,
        )
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        _finish(
            run_id, system_id, repo, fingerprint, gate,
            ExecutionResult(
                status="FAIL", stdout="", stderr=reason[:2000],
                attempts=0, model_used="", run_id=run_id, repo=repo,
            ),
        )
        outcome = {"run_id": run_id, "status": "FAIL", "reason": reason}
    finally:
        _active.discard(fingerprint)
    if outcome.get("pr_url"):
        await hub.broadcast(
            SimEvent(
                kind="pr_opened",
                payload={
                    "run_id": run_id,
                    "system_id": system_id,
                    "pr_url": outcome["pr_url"],
                    "repo": repo,
                },
            )
        )
    return outcome


def _finish(
    run_id: str,
    system_id: str,
    repo: str,
    fingerprint: str,
    gate: Dict[str, Any],
    result: ExecutionResult,
) -> None:
    _remember_run(
        run_id,
        {
            "target": "repo",
            "system_id": system_id,
            "repo": repo,
            "fingerprint": fingerprint,
            "result": result,
            "gate": gate,
        },
    )
    _emit(
        run_id, "done", result.attempts, result.model_used,
        "ok" if result.status == "PASS" else "error",
        result.pr_url or result.stderr[:200],
    )


async def _run(
    *,
    run_id: str,
    system_id: str,
    repo: str,
    base: str,
    token: str,
    fingerprint: str,
    traceback_text: str,
    commit: str,
    gate: Dict[str, Any],
    http_client: Any,
    sandbox_factory: Optional[Callable[[bytes], Any]],
    diagnose_fn: Optional[Callable[..., Diagnosis]],
    adapter: Any,
) -> Dict[str, Any]:
    import httpx

    from core.actions import github_pr
    from core.infer import meta_client

    owned = http_client is None
    http = http_client or httpx.Client(
        base_url="https://api.github.com",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=60.0,
        # The tarball endpoint 302s to codeload; httpx drops the
        # Authorization header on the cross-host hop by itself.
        follow_redirects=True,
    )
    try:
        return await _pipeline(
            run_id=run_id,
            system_id=system_id,
            repo=repo,
            base=base,
            token=token,
            fingerprint=fingerprint,
            traceback_text=traceback_text,
            commit=commit,
            gate=gate,
            http=http,
            github_pr=github_pr,
            meta_client=meta_client,
            sandbox_factory=sandbox_factory,
            diagnose_fn=diagnose_fn,
            adapter=adapter,
        )
    finally:
        if owned:
            http.close()


async def _pipeline(
    *,
    run_id: str,
    system_id: str,
    repo: str,
    base: str,
    token: str,
    fingerprint: str,
    traceback_text: str,
    commit: str,
    gate: Dict[str, Any],
    http: Any,
    github_pr: Any,
    meta_client: Any,
    sandbox_factory: Optional[Callable[[bytes], Any]],
    diagnose_fn: Optional[Callable[..., Diagnosis]],
    adapter: Any,
) -> Dict[str, Any]:
    from core.verify import repo_sandbox

    found = _registry_parse(traceback_text)
    assert found is not None  # should_trigger guarantees a parse
    parsed = found[1]
    branch = branch_for(fingerprint)

    # 1. Locate ---------------------------------------------------------
    _emit(run_id, "diagnose", 0, "", "ok", "locating suspect files")
    try:
        commit_info = await asyncio.to_thread(
            repo_snapshot.resolve_commit, repo, token, commit, base, http
        )
    except repo_snapshot.SnapshotFailed as exc:
        return _fail(run_id, system_id, repo, fingerprint, gate, str(exc))
    sha = commit_info["sha"]
    tree = await asyncio.to_thread(
        repo_locate.fetch_tree, repo, token, sha, http
    )
    paths: List[str] = tree["paths"]
    try:
        repo_score = adapter.detect(paths)
    except Exception:
        repo_score = 0
    if repo_score <= 0:
        # The trace format picked this adapter, but the repo isn't its
        # language (e.g. a Java trace in a Python repo's logs): no run.
        return _fail(
            run_id, system_id, repo, fingerprint, gate,
            f"trace language {adapter.name} does not match"
            f" repo {repo} (detect score 0)",
        )
    await _configure_adapter(repo, token, sha, paths, http, adapter)
    located = repo_locate.match_frames(parsed.frames, paths, adapter.map_frame)
    test_relpath = adapter.repro_test_path(
        fingerprint, paths, [item["path"] for item in located]
    )
    contexts: List[Dict[str, Any]] = []
    if located:
        for item in located:
            try:
                content = await asyncio.to_thread(
                    repo_locate.read_file_at, repo, token, sha,
                    item["path"], http,
                )
            except (RuntimeError, ValueError) as exc:
                contexts.append(
                    {"path": item["path"], "line": item["line"],
                     "context": f"<unreadable: {exc}>"}
                )
                continue
            contexts.append(
                {
                    "path": item["path"],
                    "line": item["line"],
                    "context": repo_locate.context_for(content, item["line"]),
                }
            )
    else:
        keywords = keywords_for(
            parsed.exc_type, parsed.exc_value, parsed.frames
        )
        picked = await asyncio.to_thread(
            repo_locate.pick_files_no_frames, paths, keywords,
            lambda ranked: repo_generate.choose_files(
                ranked, parsed.signature
            ),
        )
        for path in picked:
            try:
                content = await asyncio.to_thread(
                    repo_locate.read_file_at, repo, token, sha, path, http
                )
            except (RuntimeError, ValueError):
                continue
            contexts.append(
                {"path": path, "line": 0,
                 "context": repo_locate.context_for(content, 1)}
            )
    if not contexts:
        return await _draft(
            run_id, system_id, repo, base or "main", token, fingerprint,
            sha, gate, http, github_pr,
            Diagnosis(
                summary="Could not locate suspect files.",
                likely_cause=parsed.signature,
                suggested_actions=["Inspect the traceback by hand."],
                confidence=0.2,
            ),
            "no suspect files readable at the failing commit", "",
            adapter, test_relpath,
        )

    # Diagnose (Muse Spark, existing client) -----------------------------
    _emit(run_id, "diagnose", 1, "meta:muse-spark", "ok", "diagnosing")
    telemetry = (
        f"production traceback from {repo}@{sha[:12]}:\n{traceback_text}\n\n"
        + "\n\n".join(
            f"--- {item['path']} ---\n{item['context']}" for item in contexts
        )
    )
    diagnose = diagnose_fn or meta_client.diagnose
    try:
        diagnosis = await asyncio.to_thread(diagnose, telemetry, "")
    except Exception as exc:
        return _fail(
            run_id, system_id, repo, fingerprint, gate,
            f"diagnosis failed: {exc}",
        )

    # 2. Snapshot + sandbox ----------------------------------------------
    _emit(run_id, "diagnose", 1, "", "ok", "snapshotting repo")
    try:
        tarball = await asyncio.to_thread(
            repo_snapshot.fetch_tarball, repo, token, sha, http
        )
    except repo_snapshot.SnapshotTooBig:
        return await _draft(
            run_id, system_id, repo, base or "main", token, fingerprint,
            sha, gate, http, github_pr, diagnosis,
            "repo snapshot exceeds 50 MB", "",
            adapter, test_relpath,
        )
    filtered = await asyncio.to_thread(repo_snapshot.filter_snapshot, tarball)
    opener = sandbox_factory or repo_sandbox.open_repo_sandbox
    try:
        if sandbox_factory is None:
            sandbox = await asyncio.to_thread(
                opener, filtered, image=adapter.image
            )
        else:
            sandbox = await asyncio.to_thread(opener, filtered)
    except Exception as exc:
        return _fail(
            run_id, system_id, repo, fingerprint, gate,
            f"no sandbox available: {exc}",
        )
    try:
        return await _verify_and_fix(
            run_id=run_id,
            system_id=system_id,
            repo=repo,
            base=base or "main",
            token=token,
            fingerprint=fingerprint,
            sha=sha,
            gate=gate,
            http=http,
            github_pr=github_pr,
            sandbox=sandbox,
            diagnosis=diagnosis,
            parsed=parsed,
            contexts=contexts,
            paths=paths,
            test_relpath=test_relpath,
            branch=branch,
            adapter=adapter,
        )
    finally:
        await asyncio.to_thread(sandbox.terminate)


async def _sandbox_exec(sandbox: Any, cmd: List[str], **kwargs: Any) -> Dict[str, Any]:
    return await asyncio.to_thread(sandbox.exec, cmd, **kwargs)


def _reader(sandbox: Any) -> Callable[[str], Optional[str]]:
    """Sandbox read_file when it has one (fakes predate it)."""
    return getattr(sandbox, "read_file", lambda _path: None)


async def _configure_adapter(
    repo: str,
    token: str,
    sha: str,
    paths: List[str],
    http: Any,
    adapter: Any = None,
) -> None:
    """Pass manifest text to adapters that ask (L-J0 optional hook).

    Adapters MAY define `manifest_names()` + `configure_manifests()` (see
    `lang/base.py`); Python defines neither, so this is a no-op for it.
    Failures here never break the run — the adapter falls back.
    """
    active = adapter if adapter is not None else ADAPTER
    names_fn = getattr(active, "manifest_names", None)
    configure = getattr(active, "configure_manifests", None)
    if not callable(names_fn) or not callable(configure):
        return
    try:
        names = list(names_fn() or [])
    except Exception:
        return
    if not names:
        return
    manifests: Dict[str, Optional[str]] = {}
    for name in names:
        if name not in paths:
            manifests[name] = None
            continue
        try:
            manifests[name] = await asyncio.to_thread(
                repo_locate.read_file_at, repo, token, sha, name, http
            )
        except Exception:
            manifests[name] = None
    try:
        configure(manifests)
    except Exception:
        pass


async def _install_deps(
    run_id: str, sandbox: Any, paths: List[str], adapter: Any
) -> Optional[str]:
    """Install snapshot deps; None on success, else the failure output."""
    _emit(run_id, "verify", 0, "", "ok", "installing dependencies")
    for cmd in adapter.install_cmds(paths):
        result = await _sandbox_exec(
            sandbox,
            cmd,
            timeout=adapter.install_timeout_s,
            network=True,
        )
        if result["returncode"] != 0:
            return str(result["stderr"] or result["stdout"])
    return None


def _suite_summary(baseline: Any, proved: Any) -> Dict[str, int]:
    new_failures = len(
        set(proved.failed_ids) - set(baseline.failed_ids)
    )
    return {
        "passed": proved.passed,
        "failed": proved.failed,
        "new_failures": new_failures,
    }


async def _verify_and_fix(
    *,
    run_id: str,
    system_id: str,
    repo: str,
    base: str,
    token: str,
    fingerprint: str,
    sha: str,
    gate: Dict[str, Any],
    http: Any,
    github_pr: Any,
    sandbox: Any,
    diagnosis: Diagnosis,
    parsed: Any,
    contexts: List[Dict[str, Any]],
    paths: List[str],
    test_relpath: str,
    branch: str,
    adapter: Any,
) -> Dict[str, Any]:
    install_error = await _install_deps(run_id, sandbox, paths, adapter)
    if install_error is not None:
        return await _draft(
            run_id, system_id, repo, base, token, fingerprint, sha,
            gate, http, github_pr, diagnosis,
            f"dependencies would not install:\n{install_error[-800:]}", "",
            adapter, test_relpath,
        )
    _emit(run_id, "verify", 0, "", "ok", "running baseline suite")
    baseline_raw = await _sandbox_exec(
        sandbox,
        adapter.suite_cmd(paths),
        timeout=adapter.suite_timeout_s,
    )
    baseline = adapter.parse_results(
        str(baseline_raw["stdout"]),
        str(baseline_raw["stderr"]),
        _reader(sandbox),
    )
    if baseline.total == 0:
        return await _draft(
            run_id, system_id, repo, base, token, fingerprint, sha,
            gate, http, github_pr, diagnosis,
            "no tests collected in the snapshot", "",
            adapter, test_relpath,
        )

    # 4. Reproduce --------------------------------------------------------
    repro_code = ""
    repro_fail_output = ""
    repro_failed = False
    model_used = ""
    attempts = 0
    for attempt in range(1, REPRO_ATTEMPTS + 1):
        attempts += 1
        _emit(
            run_id, "generate", attempt, "", "ok",
            "writing repro test",
        )
        try:
            candidate, model_used = await asyncio.to_thread(
                repo_generate.generate_repro_test,
                parsed.raw,
                parsed.signature,
                contexts,
                adapter.source_files(paths),
                repro_fail_output or None,
                attempt,
                REPRO_ATTEMPTS,
                test_relpath,
                adapter=adapter,
            )
        except Exception as exc:
            repro_fail_output = f"generation failed: {exc}"
            continue
        await asyncio.to_thread(sandbox.write_file, test_relpath, candidate)
        ran = await _sandbox_exec(
            sandbox,
            adapter.single_test_cmd(test_relpath, paths),
            timeout=REPRO_TIMEOUT_S,
        )
        output = str(ran["stdout"]) + "\n" + str(ran["stderr"])
        ran_result = adapter.parse_results(
            str(ran["stdout"]), str(ran["stderr"]), _reader(sandbox)
        )
        if ran["returncode"] != 0 and ran_result.failed > 0:
            repro_code = candidate  # fails on original: a real repro
            repro_fail_output = output
            repro_failed = True
            break
        repro_fail_output = output
    if not repro_failed:
        return await _draft(
            run_id, system_id, repo, base, token, fingerprint, sha,
            gate, http, github_pr, diagnosis,
            "could not write a test that fails on the original code",
            "",
            adapter, test_relpath,
        )

    # 5+6. Patch + prove ---------------------------------------------------
    patch_note = ""
    for attempt in range(1, PATCH_ATTEMPTS + 1):
        attempts += 1
        _emit(run_id, "generate", attempt, "", "ok", "writing patch")
        try:
            files, model_used, patch_note = await asyncio.to_thread(
                repo_generate.generate_patch,
                parsed.raw,
                parsed.signature,
                diagnosis.summary,
                contexts,
                paths,
                repro_fail_output,
                attempt,
                PATCH_ATTEMPTS,
            )
        except Exception as exc:
            repro_fail_output = f"patch generation failed: {exc}"
            continue
        for item in files:
            await asyncio.to_thread(
                sandbox.write_file, item["path"], item["content"]
            )
        rerun = await _sandbox_exec(
            sandbox,
            adapter.single_test_cmd(test_relpath, paths),
            timeout=REPRO_TIMEOUT_S,
        )
        rerun_output = str(rerun["stdout"]) + "\n" + str(rerun["stderr"])
        if rerun["returncode"] != 0:
            repro_fail_output = rerun_output
            continue
        proved_raw = await _sandbox_exec(
            sandbox,
            adapter.suite_cmd(paths),
            timeout=adapter.suite_timeout_s,
        )
        proved = adapter.parse_results(
            str(proved_raw["stdout"]),
            str(proved_raw["stderr"]),
            _reader(sandbox),
        )
        suite = _suite_summary(baseline, proved)
        if suite["new_failures"] > 0:
            repro_fail_output = (
                f"new failures: {proved.failed_ids}\n{rerun_output}"
            )
            continue
        # 7. PR ------------------------------------------------------------
        return await _open_or_comment(
            run_id=run_id,
            system_id=system_id,
            repo=repo,
            base=base,
            token=token,
            fingerprint=fingerprint,
            sha=sha,
            gate=gate,
            http=http,
            github_pr=github_pr,
            diagnosis=diagnosis,
            files=files,
            test_relpath=test_relpath,
            repro_code=repro_code,
            repro_fail=repro_fail_output,
            repro_pass=rerun_output,
            suite=suite,
            patch_note=patch_note,
            attempts=attempts,
            model_used=model_used,
            sandbox_backend=sandbox.backend,
            branch=branch,
        )
    return await _draft(
        run_id, system_id, repo, base, token, fingerprint, sha,
        gate, http, github_pr, diagnosis,
        "patch attempts did not prove (repro must pass, no new failures)",
        repro_code,
        adapter, test_relpath,
    )


async def _open_or_comment(
    *,
    run_id: str,
    system_id: str,
    repo: str,
    base: str,
    token: str,
    fingerprint: str,
    sha: str,
    gate: Dict[str, Any],
    http: Any,
    github_pr: Any,
    diagnosis: Diagnosis,
    files: List[Dict[str, str]],
    test_relpath: str,
    repro_code: str,
    repro_fail: str,
    repro_pass: str,
    suite: Dict[str, int],
    patch_note: str,
    attempts: int,
    model_used: str,
    sandbox_backend: str,
    branch: str,
) -> Dict[str, Any]:
    _emit(run_id, "verify", attempts, "", "ok", "opening pull request")
    existing = await asyncio.to_thread(
        github_pr.open_pr_for_branch, repo, branch, token, http
    )
    if existing is not None:
        # Chatty errors must not spam the PR: one repeat comment/hour/fp.
        now = time.time()
        if now - _last_repeat_comment.get(fingerprint, 0.0) >= REPEAT_COMMENT_EVERY_S:
            await asyncio.to_thread(
                github_pr.comment_on_pr,
                repo,
                existing["number"],
                f"Seen again in run `{run_id}` — still covered by this PR "
                f"(suite {suite['passed']} passed, {suite['new_failures']} "
                f"new failures).",
                token,
                http,
            )
            _last_repeat_comment[fingerprint] = now
        pr_url = existing["html_url"]
    else:
        pr_files = {item["path"]: item["content"] for item in files}
        pr_files[test_relpath] = repro_code
        title = f"fix: {(diagnosis.summary or 'telemetry-agent repair')[:90]}"
        pr_url = await asyncio.to_thread(
            github_pr.open_pr,
            repo=repo,
            base=base,
            branch=branch,
            title=title,
            body=_pr_body(
                diagnosis=diagnosis,
                fingerprint=fingerprint,
                sha=sha,
                files=[item["path"] for item in files],
                repro_fail=repro_fail,
                repro_pass=repro_pass,
                suite=suite,
                note=patch_note,
            ),
            files=pr_files,
            token=token,
            client=http,
            labels=[PR_LABEL],
        )
    result = ExecutionResult(
        status="PASS",
        stdout=f"suite {suite['passed']} passed, {suite['failed']} failed, "
        f"{suite['new_failures']} new failures",
        stderr="",
        attempts=attempts,
        model_used=model_used,
        pr_url=pr_url,
        run_id=run_id,
        repo=repo,
        suite=dict(suite),
        verification=RunVerification(
            target=f"repo:{repo}",
            test_code=repro_code,
            original=VerifyAttempt(passed=False, output=repro_fail[-4000:]),
            patched=VerifyAttempt(passed=True, output=repro_pass[-4000:]),
            runner=sandbox_backend,
        ),
    )
    _finish(run_id, system_id, repo, fingerprint, gate, result)
    return {"run_id": run_id, "status": "PASS", "pr_url": pr_url}


async def _draft(
    run_id: str,
    system_id: str,
    repo: str,
    base: str,
    token: str,
    fingerprint: str,
    sha: str,
    gate: Dict[str, Any],
    http: Any,
    github_pr: Any,
    diagnosis: Diagnosis,
    reason: str,
    repro_code: str,
    adapter: Any = None,
    test_relpath: str = "",
) -> Dict[str, Any]:
    """Draft PR with diagnosis (+ repro test when one exists)."""
    _emit(run_id, "verify", 0, "", "ok", "opening draft PR")
    branch = branch_for(fingerprint)
    existing = await asyncio.to_thread(
        github_pr.open_pr_for_branch, repo, branch, token, http
    )
    if existing is not None:
        pr_url = existing["html_url"]
    else:
        files = {
            "TELEMETRY_AGENT_DIAGNOSIS.md": (
                f"# TelemetryAgent diagnosis\n\n"
                f"**Summary:** {diagnosis.summary}\n\n"
                f"**Likely cause:** {diagnosis.likely_cause}\n\n"
                f"**Why no verified fix:** {reason}\n"
            )
        }
        if repro_code:
            active = adapter if adapter is not None else ADAPTER
            files[
                test_relpath
                or active.repro_test_path(fingerprint, [], [])
            ] = repro_code
        pr_url = await asyncio.to_thread(
            github_pr.open_pr,
            repo=repo,
            base=base,
            branch=branch,
            title=f"diagnosis: {diagnosis.summary[:80]}",
            body=_draft_body(
                diagnosis=diagnosis,
                fingerprint=fingerprint,
                sha=sha,
                reason=reason,
                repro_test=repro_code,
            ),
            files=files,
            token=token,
            client=http,
            labels=[PR_LABEL],
            draft=True,
        )
    result = ExecutionResult(
        status="NO_ACTION",
        stdout="",
        stderr=f"draft: {reason}"[:2000],
        attempts=0,
        model_used="",
        pr_url=pr_url,
        run_id=run_id,
        repo=repo,
    )
    _finish(run_id, system_id, repo, fingerprint, gate, result)
    return {"run_id": run_id, "status": "NO_ACTION", "pr_url": pr_url}


def _fail(
    run_id: str,
    system_id: str,
    repo: str,
    fingerprint: str,
    gate: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    result = ExecutionResult(
        status="FAIL", stdout="", stderr=reason[:2000],
        attempts=0, model_used="", run_id=run_id, repo=repo,
    )
    _finish(run_id, system_id, repo, fingerprint, gate, result)
    return {"run_id": run_id, "status": "FAIL", "reason": reason}
