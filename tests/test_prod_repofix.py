"""J-R3 acceptance: real fix pipeline (James). All external calls mocked."""

import asyncio
import base64
import io
import json
import os
import tarfile
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

import apps.api.main as api_main
from core.actions import mitigate
from core.connections import store as connection_store
from core.repo_fix import generate as repo_generate
from core.repo_fix import locate as repo_locate
from core.repo_fix import run as repo_run
from core.repo_fix import snapshot as repo_snapshot
from core.schemas.diagnosis import Diagnosis
from core.schemas.profile import SystemProfile
from core.setup import store as setup_store
from core.verify import repo_sandbox

TRACEBACK_TEXT = """Traceback (most recent call last):
  File "/srv/acme/app/cart.py", line 17, in total
    return sum(items) / len(items)
ZeroDivisionError: division by zero"""

TREE_PATHS = [
    "app/cart.py",
    "app/views.py",
    "requirements.txt",
    "tests/test_old.py",
]

CART_CODE = '''"""Cart totals."""


def total(items):
    return sum(items) / len(items)
'''

DIAGNOSIS = Diagnosis(
    summary="division by zero on empty cart",
    likely_cause="len(items) is 0",
    suggested_actions=["guard empty cart"],
    confidence=0.9,
)


def _tmp_data() -> str:
    return tempfile.mkdtemp(prefix="ta-repofix-test-")


def _save_production(tmp: str, system_id: str, status: str = "armed") -> None:
    with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
        setup_store.save_profile(
            SystemProfile(
                system_id=system_id,
                name="Acme",
                kind="software",
                environment={"mode": "production"},
                status=status,
            )
        )


def _make_tar(files: dict) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name, content in files.items():
            data = content.encode()
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _ok_exec(stdout: str = "", code: int = 0) -> dict:
    return {
        "returncode": code, "stdout": stdout, "stderr": "",
        "timed_out": False,
    }


class FakeSandbox:
    backend = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.files = {}
        self.execs = []
        self.terminated = False

    def exec(self, cmd, timeout=300, network=False):
        self.execs.append(cmd)
        assert self.script, f"unexpected exec: {cmd!r}"
        return self.script.pop(0)

    def write_file(self, relpath, content):
        self.files[relpath] = content

    def terminate(self):
        self.terminated = True


class FakeGitHub:
    """Mock GitHub API for the pipeline; logs PR-shape calls."""

    def __init__(self, tarball: bytes, existing_pr=None):
        self.tarball = tarball
        self.existing_pr = existing_pr
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        method = request.method
        self.calls.append((method, path))
        if path == "/repos/acme/api/commits/abc123":
            return httpx.Response(200, json={"sha": "abc123"})
        if path == "/repos/acme/api":
            return httpx.Response(200, json={"default_branch": "main"})
        if path == "/repos/acme/api/git/trees/abc123":
            return httpx.Response(
                200,
                json={
                    "truncated": False,
                    "tree": [
                        {"type": "blob", "path": name} for name in TREE_PATHS
                    ],
                },
            )
        if path.startswith("/repos/acme/api/contents/"):
            content = base64.b64encode(CART_CODE.encode()).decode()
            return httpx.Response(
                200, json={"content": content, "size": len(CART_CODE)}
            )
        if path == "/repos/acme/api/tarball/abc123":
            return httpx.Response(200, content=self.tarball)
        if path == "/repos/acme/api/git/ref/heads/main":
            return httpx.Response(200, json={"object": {"sha": "abc123"}})
        if path.startswith("/repos/acme/api/git/ref/heads/"):
            return httpx.Response(404, json={"message": "Not Found"})
        if path == "/repos/acme/api/pulls" and method == "GET":
            params = dict(request.url.params)
            if params.get("state") == "open" and self.existing_pr:
                return httpx.Response(200, json=[self.existing_pr])
            return httpx.Response(200, json=[])
        if path == "/repos/acme/api/git/blobs":
            return httpx.Response(201, json={"sha": "blob1"})
        if path == "/repos/acme/api/git/trees":
            return httpx.Response(201, json={"sha": "tree1"})
        if path == "/repos/acme/api/git/commits":
            return httpx.Response(201, json={"sha": "commit1"})
        if path == "/repos/acme/api/git/refs":
            return httpx.Response(201, json={"ref": "x"})
        if path == "/repos/acme/api/pulls" and method == "POST":
            return httpx.Response(
                201,
                json={
                    "html_url": "https://github.com/acme/api/pull/7",
                    "number": 7,
                },
            )
        if path == "/repos/acme/api/labels":
            return httpx.Response(201, json={})
        if path == "/repos/acme/api/issues/7":
            return httpx.Response(200, json={})
        if path == "/repos/acme/api/issues/3/comments":
            return httpx.Response(201, json={})
        return httpx.Response(404, json={"message": "Not Found"})

    def client(self) -> httpx.Client:
        return httpx.Client(
            transport=httpx.MockTransport(self.handler),
            base_url="https://api.github.com",
            headers={"Authorization": "Bearer good"},
        )


def _run_pipeline(
    tarball: bytes,
    script: list,
    existing_pr=None,
    commit: str = "abc123",
) -> tuple:
    fake = FakeGitHub(tarball, existing_pr)
    box = FakeSandbox(script)
    outcome = asyncio.run(
        repo_run.run_repo_fix(
            run_id="runrepo123456",
            system_id="acme",
            repo_info={
                "repo": "acme/api",
                "base": "main",
                "token": "good",
            },
            fingerprint="fp9f2c4d8a1b3e",
            traceback_text=TRACEBACK_TEXT,
            commit=commit,
            gate={"decision": "observe"},
            http_client=fake.client(),
            sandbox_factory=lambda _tar: box,
            diagnose_fn=lambda *args: DIAGNOSIS,
        )
    )
    return outcome, fake, box


BASE_TARBALL = _make_tar(
    {
        "acme-api-abc/app/cart.py": CART_CODE,
        "acme-api-abc/requirements.txt": "pytest\n",
        "acme-api-abc/tests/test_old.py": "def test_old(): assert True\n",
    }
)

PASS_SCRIPT = [
    _ok_exec("installed"),  # pip install -r requirements.txt
    _ok_exec(".....\n5 passed in 0.10s\n"),  # baseline
    _ok_exec(
        "F\nFAILED tests/test_telemetry_agent_fp9f2c4d8a1b3e.py::test_total - "
        "ZeroDivisionError\n1 failed in 0.05s\n",
        code=1,
    ),  # repro fails on original
    _ok_exec(".\n1 passed in 0.05s\n"),  # repro passes on patch
    _ok_exec("......\n6 passed in 0.10s\n"),  # full suite, no new failures
]


class LocateTests(unittest.TestCase):
    def test_suffix_match_and_context(self) -> None:
        from core.ingest.traceback import parse_traceback

        parsed = parse_traceback(TRACEBACK_TEXT)
        assert parsed is not None
        matched = repo_locate.match_frames(parsed.frames, TREE_PATHS)
        self.assertEqual(len(matched), 1)
        self.assertEqual(matched[0]["path"], "app/cart.py")
        context = repo_locate.context_for(CART_CODE, 17)
        self.assertIn("5:     return sum(items) / len(items)", context)

    def test_match_caps_at_three_files(self) -> None:
        frames = [
            {"file": f"/srv/deploy/pkg/file{index}.py", "line": 1}
            for index in range(5)
        ]
        paths = [f"pkg/file{index}.py" for index in range(5)]
        matched = repo_locate.match_frames(frames, paths)
        self.assertEqual(len(matched), 3)

    def test_keyword_pick_falls_back_on_chooser_error(self) -> None:
        def boom(ranked):
            raise RuntimeError("model down")

        picked = repo_locate.pick_files_no_frames(
            ["app/cart.py", "app/views.py"], ["cart"], boom
        )
        self.assertEqual(picked, ["app/cart.py"])


class SnapshotTests(unittest.TestCase):
    def test_resolve_prefers_commit_then_base(self) -> None:
        fake = FakeGitHub(BASE_TARBALL)
        info = repo_snapshot.resolve_commit(
            "acme/api", "good", "abc123", "main", fake.client()
        )
        self.assertEqual(info["sha"], "abc123")
        self.assertIn("failing commit", info["source"])

    def test_filter_drops_junk_and_strips_top(self) -> None:
        tarball = _make_tar(
            {
                "top/app.py": "x = 1\n",
                "top/.git/HEAD": "ref\n",
                "top/node_modules/lib.js": "y\n",
                "top/blob.bin": "a\x00b",
                "top/ok.py": "z = 2\n",
            }
        )
        filtered = repo_snapshot.filter_snapshot(tarball)
        names = tarfile.open(fileobj=io.BytesIO(filtered)).getnames()
        self.assertEqual(sorted(names), ["app.py", "ok.py"])

    def test_tarball_cap_aborts(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"x" * 500)

        client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.github.com",
        )
        with patch.object(repo_snapshot, "MAX_TARBALL_BYTES", 100):
            with self.assertRaises(repo_snapshot.SnapshotTooBig):
                repo_snapshot.fetch_tarball("acme/api", "good", "abc", client)


class ParsePytestTests(unittest.TestCase):
    def test_counts_and_failed_ids(self) -> None:
        parsed = repo_run.parse_pytest(
            "F.\nFAILED tests/a.py::test_x - assert\n"
            "1 failed, 1 passed in 0.05s\n"
        )
        self.assertEqual(
            (parsed["passed"], parsed["failed"], parsed["total"]),
            (1, 1, 2),
        )
        self.assertEqual(parsed["failed_ids"], ["tests/a.py::test_x"])

    def test_empty_suite_is_zero(self) -> None:
        parsed = repo_run.parse_pytest("no tests ran in 0.01s\n")
        self.assertEqual(parsed["total"], 0)


class GenerateTests(unittest.TestCase):
    def test_repro_uses_wonder_on_final_attempt(self) -> None:
        seen = {}

        def fake_baseten(system_prompt, user_content):
            seen["baseten"] = True
            return '{"test_code": "def test_x(): assert True"}'

        def fake_wonder(system_prompt, user_content):
            seen["wonder"] = True
            return '{"test_code": "def test_x(): assert False"}'

        with (
            patch.object(
                repo_generate.baseten_client, "generate", fake_baseten
            ),
            patch.object(
                repo_generate, "_wonder_generate", fake_wonder
            ),
        ):
            code, model = repo_generate.generate_repro_test(
                TRACEBACK_TEXT, "ZeroDivisionError", [], ["a.py"], None,
                1, 3, "tests/test_x.py",
            )
            self.assertIn("baseten", model)
            self.assertTrue(seen.get("baseten"))
            code, model = repo_generate.generate_repro_test(
                TRACEBACK_TEXT, "ZeroDivisionError", [], ["a.py"],
                "output", 3, 3, "tests/test_x.py",
            )
            self.assertIn("wonder", model)
            self.assertTrue(seen.get("wonder"))

    def test_repro_without_tests_rejected(self) -> None:
        with patch.object(
            repo_generate.baseten_client,
            "generate",
            lambda *args: '{"test_code": "x = 1"}',
        ):
            with self.assertRaises(ValueError):
                repo_generate.generate_repro_test(
                    TRACEBACK_TEXT, "E", [], ["a.py"], None,
                    1, 3, "tests/test_x.py",
                )

    def test_patch_caps_at_three_known_files(self) -> None:
        payload = {
            "files": [
                {"path": f"a{i}.py", "content": "x = 1"}
                for i in range(5)
            ]
            + [{"path": "ghost.py", "content": "y = 2"}]
        }
        with patch.object(
            repo_generate.baseten_client,
            "generate",
            lambda *args: json.dumps(payload),
        ):
            files, _, note = repo_generate.generate_patch(
                TRACEBACK_TEXT, "E", "d", [], ["a0.py", "a1.py", "a2.py",
                                              "a3.py", "a4.py"],
                "out", 1, 2,
            )
        self.assertEqual(len(files), 3)
        self.assertIn("kept the first 3", note)


class TriggerTests(unittest.TestCase):
    def setUp(self) -> None:
        repo_run.reset_run_state()
        mitigate.reset_mitigate_state()

    def _decision(self, **overrides) -> dict:
        base = {
            "decision": "observe",
            "rule": "traceback",
            "fingerprint": "fp9f2c4d8a1b3e",
            "window": TRACEBACK_TEXT,
            "commit": "abc123",
        }
        base.update(overrides)
        return base

    def test_matrix(self) -> None:
        tmp = _tmp_data()
        _save_production(tmp, "acme")
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            profile = setup_store.get_profile("acme")
            # No github connection yet: no trigger.
            self.assertIsNone(
                repo_run.should_trigger(profile, self._decision())
            )
            connection_store.create_connection(
                "acme", "github", {"repo": "acme/api"}, "good"
            )
            ctx = repo_run.should_trigger(profile, self._decision())
            assert ctx is not None
            self.assertEqual(ctx["repo_info"]["repo"], "acme/api")
            # Demo system, unarmed, other rules, empty window: no trigger.
            setup_store.save_profile(
                SystemProfile(
                    system_id="demo", name="Demo", kind="software",
                    status="armed",
                )
            )
            demo = setup_store.get_profile("demo")
            self.assertIsNone(repo_run.should_trigger(demo, self._decision()))
            # A traceback labeled "deadlock" still triggers (parse-based).
            deadlock_tb = self._decision(
                rule="deadlock",
                window=TRACEBACK_TEXT.replace(
                    "ZeroDivisionError", "deadlock TimeoutError"
                ),
            )
            self.assertIsNotNone(
                repo_run.should_trigger(profile, deadlock_tb)
            )
            # But a plain ERROR line never triggers (nothing to parse).
            self.assertIsNone(
                repo_run.should_trigger(
                    profile,
                    self._decision(rule="error", window="ERROR boom"),
                )
            )
            # Nor does uvicorn's pre-traceback line, which parses as
            # `ERROR: ...` but has no frames.
            self.assertIsNone(
                repo_run.should_trigger(
                    profile,
                    self._decision(
                        rule="error",
                        window="ERROR:    Exception in ASGI application",
                    ),
                )
            )
            self.assertIsNone(
                repo_run.should_trigger(profile, self._decision(window=""))
            )
            self.assertIsNone(repo_run.should_trigger(None, self._decision()))
            _save_production(tmp, "acme-learning", status="learning")
            learning = setup_store.get_profile("acme-learning")
            self.assertIsNone(
                repo_run.should_trigger(learning, self._decision())
            )
            # In-flight fingerprint: no second trigger.
            repo_run._active.add("fp9f2c4d8a1b3e")
            self.assertIsNone(
                repo_run.should_trigger(profile, self._decision())
            )

    def test_maybe_trigger_proposes_window_and_starts_run(self) -> None:
        tmp = _tmp_data()
        with patch.dict(os.environ, {"TA_DATA_DIR": tmp}):
            setup_store.save_profile(
                SystemProfile(
                    system_id="acme",
                    name="Acme",
                    kind="software",
                    environment={"mode": "production"},
                    status="armed",
                    policy={"allowed_actions": ["rollback"]},
                )
            )
            connection_store.create_connection(
                "acme", "github", {"repo": "acme/api"}, "good"
            )
            connection_store.create_connection(
                "acme", "webhook", {"url": "http://hook/x"}, "sec"
            )

            async def main():
                with patch.object(
                    repo_run, "run_repo_fix", new=AsyncMock(
                        return_value={"status": "PASS"}
                    )
                ) as started_run:
                    begun = await repo_run.maybe_trigger(
                        "acme", [self._decision()], "abc123"
                    )
                    # Cancel the propose ticker first: it never ends.
                    ticker = mitigate._ticker_task
                    if ticker is not None:
                        ticker.cancel()
                    current = asyncio.current_task()
                    others = [
                        task
                        for task in asyncio.all_tasks()
                        if task is not current
                    ]
                    if others:
                        await asyncio.gather(
                            *others, return_exceptions=True
                        )
                    return begun, started_run

            with (
                patch.dict(os.environ, {"TA_DATA_DIR": tmp}),
                patch.object(
                    api_main.hub, "broadcast", new=AsyncMock()
                ),
            ):
                begun, started_run = asyncio.run(main())
        self.assertEqual(len(begun), 1)
        started_run.assert_awaited_once()
        # Rollback window proposed (approve-to-run, policy allowed).
        window = mitigate._windows.get(begun[0])
        assert window is not None
        self.assertEqual(window.state, "pending")
        self.assertFalse(window.auto_apply)
        mitigate.reset_mitigate_state()


class RunPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        repo_run.reset_run_state()
        api_main.software_runs.pop("runrepo123456", None)

    def test_pass_opens_pr_with_proof(self) -> None:
        with (
            patch.object(
                repo_generate, "generate_repro_test",
                return_value=("def test_total(): assert False", "baseten:m"),
            ),
            patch.object(
                repo_generate, "generate_patch",
                return_value=(
                    [{"path": "app/cart.py", "content": "fixed"}],
                    "baseten:m",
                    "",
                ),
            ),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        ):
            outcome, fake, box = _run_pipeline(BASE_TARBALL, PASS_SCRIPT)
        self.assertEqual(outcome["status"], "PASS")
        self.assertEqual(
            outcome["pr_url"], "https://github.com/acme/api/pull/7"
        )
        entry = api_main.software_runs["runrepo123456"]
        self.assertEqual(entry["target"], "repo")
        self.assertEqual(entry["result"].repo, "acme/api")
        self.assertEqual(
            entry["result"].suite.model_dump(),
            {"passed": 6, "failed": 0, "new_failures": 0},
        )
        posts = [
            call for call in fake.calls
            if call == ("POST", "/repos/acme/api/pulls")
        ]
        self.assertEqual(len(posts), 1)
        # Branch is deterministic per fingerprint.
        refs = [
            call for call in fake.calls
            if call == ("POST", "/repos/acme/api/git/refs")
        ]
        self.assertEqual(len(refs), 1)
        self.assertTrue(box.terminated)

    def test_existing_pr_gets_comment_not_new_pr(self) -> None:
        existing = {
            "number": 3,
            "html_url": "https://github.com/acme/api/pull/3",
        }
        with (
            patch.object(
                repo_generate, "generate_repro_test",
                return_value=("def test_total(): assert False", "baseten:m"),
            ),
            patch.object(
                repo_generate, "generate_patch",
                return_value=(
                    [{"path": "app/cart.py", "content": "fixed"}],
                    "baseten:m",
                    "",
                ),
            ),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        ):
            outcome, fake, _ = _run_pipeline(
                BASE_TARBALL, PASS_SCRIPT, existing_pr=existing
            )
        self.assertEqual(outcome["status"], "PASS")
        self.assertEqual(
            outcome["pr_url"], "https://github.com/acme/api/pull/3"
        )
        posts = [
            call for call in fake.calls
            if call == ("POST", "/repos/acme/api/pulls")
        ]
        self.assertEqual(posts, [])
        comments = [
            call for call in fake.calls
            if call == ("POST", "/repos/acme/api/issues/3/comments")
        ]
        self.assertEqual(len(comments), 1)

    def test_unreproducible_opens_draft(self) -> None:
        script = [
            _ok_exec("installed"),
            _ok_exec(".....\n5 passed in 0.10s\n"),
            _ok_exec(".\n1 passed in 0.05s\n"),
            _ok_exec(".\n1 passed in 0.05s\n"),
            _ok_exec(".\n1 passed in 0.05s\n"),
        ]
        seen_payloads = []
        original_handler = FakeGitHub(BASE_TARBALL).handler

        def handler(request: httpx.Request) -> httpx.Response:
            if (
                request.method == "POST"
                and request.url.path == "/repos/acme/api/pulls"
            ):
                seen_payloads.append(json.loads(request.content))
            if (
                request.method == "POST"
                and request.url.path == "/repos/acme/api/git/trees"
            ):
                seen_payloads.append(
                    {"tree": json.loads(request.content)}
                )
            return original_handler(request)

        fake_client = httpx.Client(
            transport=httpx.MockTransport(handler),
            base_url="https://api.github.com",
        )
        box = FakeSandbox(script)
        with (
            patch.object(
                repo_generate, "generate_repro_test",
                return_value=("def test_total(): assert True", "baseten:m"),
            ),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        ):
            outcome = asyncio.run(
                repo_run.run_repo_fix(
                    run_id="runrepo123456",
                    system_id="acme",
                    repo_info={
                        "repo": "acme/api", "base": "main", "token": "good",
                    },
                    fingerprint="fp9f2c4d8a1b3e",
                    traceback_text=TRACEBACK_TEXT,
                    commit="abc123",
                    gate={"decision": "observe"},
                    http_client=fake_client,
                    sandbox_factory=lambda _tar: box,
                    diagnose_fn=lambda *args: DIAGNOSIS,
                )
            )
        self.assertEqual(outcome["status"], "NO_ACTION")
        drafts = [p for p in seen_payloads if p.get("draft") is True]
        self.assertEqual(len(drafts), 1)
        trees = [p["tree"]["tree"] for p in seen_payloads if "tree" in p]
        self.assertTrue(
            any(
                item["path"] == "TELEMETRY_AGENT_DIAGNOSIS.md"
                for tree in trees
                for item in tree
            )
        )

    def test_repeat_comment_throttled_to_one_per_hour(self) -> None:
        existing = {
            "number": 3,
            "html_url": "https://github.com/acme/api/pull/3",
        }
        patches = (
            patch.object(
                repo_generate, "generate_repro_test",
                return_value=("def test_total(): assert False", "baseten:m"),
            ),
            patch.object(
                repo_generate, "generate_patch",
                return_value=(
                    [{"path": "app/cart.py", "content": "fixed"}],
                    "baseten:m",
                    "",
                ),
            ),
            patch.object(api_main.hub, "broadcast", new=AsyncMock()),
        )
        for entered in patches:
            entered.__enter__()
        try:
            _, fake_first, _ = _run_pipeline(
                BASE_TARBALL, PASS_SCRIPT, existing_pr=existing
            )
            repo_run._active.clear()
            _, fake_second, _ = _run_pipeline(
                BASE_TARBALL, PASS_SCRIPT, existing_pr=existing
            )
        finally:
            for entered in patches:
                entered.__exit__(None, None, None)
        first = [
            call for call in fake_first.calls
            if call == ("POST", "/repos/acme/api/issues/3/comments")
        ]
        second = [
            call for call in fake_second.calls
            if call == ("POST", "/repos/acme/api/issues/3/comments")
        ]
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_no_sandbox_fails_clearly(self) -> None:
        def boom(_tar):
            raise repo_sandbox.SandboxUnavailable("no backend here")

        with patch.object(api_main.hub, "broadcast", new=AsyncMock()):
            outcome = asyncio.run(
                repo_run.run_repo_fix(
                    run_id="runrepo123456",
                    system_id="acme",
                    repo_info={
                        "repo": "acme/api", "base": "main", "token": "good",
                    },
                    fingerprint="fp9f2c4d8a1b3e",
                    traceback_text=TRACEBACK_TEXT,
                    commit="abc123",
                    gate={"decision": "observe"},
                    http_client=FakeGitHub(BASE_TARBALL).client(),
                    sandbox_factory=boom,
                    diagnose_fn=lambda *args: DIAGNOSIS,
                )
            )
        self.assertEqual(outcome["status"], "FAIL")
        self.assertIn("no sandbox", outcome["reason"])
        entry = api_main.software_runs["runrepo123456"]
        self.assertIn("no sandbox", entry["result"].stderr)


class SandboxBackendTests(unittest.TestCase):
    def test_local_without_docker_fails_clearly(self) -> None:
        with (
            patch.dict(os.environ, {"TA_VERIFY": "local"}),
            patch.object(
                repo_sandbox, "resolve_docker", return_value=None
            ),
        ):
            with self.assertRaises(repo_sandbox.SandboxUnavailable):
                repo_sandbox.open_repo_sandbox(b"bogus")

    def test_selected_backend_reports(self) -> None:
        with patch.dict(os.environ, {"TA_VERIFY": "local"}):
            self.assertEqual(repo_sandbox.selected_backend(), "docker")

    def test_docker_runs_pytest_live(self) -> None:
        from core.verify.local_runner import resolve_docker

        if resolve_docker() is None:
            self.skipTest("no docker CLI")
        tarball = _make_tar(
            {
                "calc.py": "def add(a, b):\n    return a + b\n",
                "test_calc.py": (
                    "from calc import add\n\n"
                    "def test_add():\n    assert add(1, 2) == 3\n"
                ),
            }
        )
        with patch.dict(os.environ, {"TA_VERIFY": "local"}):
            try:
                box = repo_sandbox.open_repo_sandbox(tarball)
            except repo_sandbox.SandboxUnavailable as exc:
                self.skipTest(str(exc))
            try:
                self.assertEqual(box.backend, "docker")
                result = box.exec(
                    ["pytest", "-q", "-p", "no:cacheprovider"], timeout=180
                )
                self.assertEqual(result["returncode"], 0)
                self.assertIn("1 passed", result["stdout"])
            finally:
                box.terminate()

    def test_docker_pytest_imports_package_from_tests_dir(self) -> None:
        from core.verify.local_runner import resolve_docker

        if resolve_docker() is None:
            self.skipTest("no docker CLI")
        tarball = _make_tar(
            {
                "app/__init__.py": "",
                "app/calc.py": "def add(a, b):\n    return a + b\n",
                "tests/test_calc.py": (
                    "from app.calc import add\n\n"
                    "def test_add():\n    assert add(1, 2) == 3\n"
                ),
            }
        )
        with patch.dict(os.environ, {"TA_VERIFY": "local"}):
            try:
                box = repo_sandbox.open_repo_sandbox(tarball)
            except repo_sandbox.SandboxUnavailable as exc:
                self.skipTest(str(exc))
            try:
                result = box.exec(repo_run.PYTEST, timeout=180)
                self.assertEqual(result["returncode"], 0, result["stdout"])
                self.assertIn("1 passed", result["stdout"])
            finally:
                box.terminate()
