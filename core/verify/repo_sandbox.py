"""Repo sandbox: run a customer's snapshot + pytest in Modal or Docker (J-R3).

`open_repo_sandbox` uploads a filtered snapshot tarball and yields exec +
write_file against /work. Modal first (Python 3.11, pytest baked); when
Modal is missing or fails for any reason, the local Docker runner pattern
(host-extracted temp dir, throwaway containers); when neither works, a
clear RuntimeError. `TA_VERIFY=local` forces Docker.

No customer secrets ever go inside: the snapshot arrives as bytes (chunked
base64 execs on Modal, a host mount on Docker) and no tokens are set in
the environment.
"""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import tarfile
import tempfile
from types import TracebackType
from typing import Dict, List, Optional, Type

from core.verify.local_runner import IMAGE as DOCKER_IMAGE
from core.verify.local_runner import resolve_docker

#: Sandbox image key → local Docker image (languages §1.6, L-J0).
#: Built by scripts/build-sandbox-image.sh <lang>; `image=` selects one.
SANDBOX_IMAGES = {
    "python": DOCKER_IMAGE,
    "node": "telemetry-agent-sandbox-node",
    "jvm": "telemetry-agent-sandbox-jvm",
    "go": "telemetry-agent-sandbox-go",
    "rust": "telemetry-agent-sandbox-rust",
    "php": "telemetry-agent-sandbox-php",
}

#: Raw bytes per Modal upload chunk (base64 argv stays far under ARG_MAX).
UPLOAD_CHUNK = 256 * 1024

MAX_OUTPUT_CHARS = 20000

def _check_relpath(relpath: str) -> str:
    """Guest-relative path; rejects absolute paths and `..` escapes."""
    if not relpath or relpath.startswith(("/", "\\")):
        raise ValueError(f"unsafe sandbox path: {relpath!r}")
    if ".." in relpath.split("/"):
        raise ValueError(f"unsafe sandbox path: {relpath!r}")
    return relpath

_APPEND_CHUNK = (
    "import base64, sys; "
    "open(sys.argv[1], 'ab').write(base64.b64decode(sys.argv[2]))"
)


def _modal_image(key: str):  # modal.Image; import is caller-side
    """Modal sandbox image per language (§1.1 toolchains, L-J3).

    Unknown keys fall back to python (never fail here — the pipeline
    picks only registered adapter images, and Docker is the fallback).
    """
    import modal

    if key == "node":
        return modal.Image.from_registry("node:20-slim").run_commands(
            "corepack enable"
        )
    if key == "jvm":
        return modal.Image.from_registry(
            "eclipse-temurin:21-jdk"
        ).apt_install("maven")
    if key == "go":
        return modal.Image.from_registry("golang:1.23-bookworm")
    if key == "rust":
        return modal.Image.from_registry(
            "rust:1-slim-bookworm"
        ).apt_install("ca-certificates")
    if key == "php":
        return (
            modal.Image.from_registry("php:8.3-cli-bookworm")
            .apt_install(
                "git", "unzip", "ca-certificates", "libicu-dev", "libzip-dev"
            )
            .run_commands(
                "docker-php-ext-install mbstring xml intl zip pdo_sqlite",
                "php -r \"copy('https://getcomposer.org/installer', "
                "'composer-setup.php');\" && "
                "php composer-setup.php --install-dir=/usr/bin "
                "--filename=composer && rm composer-setup.php",
            )
        )
    return modal.Image.debian_slim(python_version="3.11").pip_install("pytest")


def _append_cmd(path: str, encoded: str, portable: bool) -> List[str]:
    """Exec argv appending one base64 chunk to a guest file.

    Python guests keep the legacy `python -c` path (byte-identical);
    every other image uses sh + base64 (no guest Python assumed).
    """
    if not portable:
        return ["python", "-c", _APPEND_CHUNK, path, encoded]
    quoted_path = "'" + path.replace("'", "'\\''") + "'"
    quoted_blob = "'" + encoded.replace("'", "'\\''") + "'"
    return [
        "sh", "-c",
        f"printf %s {quoted_blob} | base64 -d >> {quoted_path}",
    ]


class SandboxUnavailable(RuntimeError):
    """Neither Modal nor Docker could run the snapshot."""


def safe_members(tar: tarfile.TarFile) -> List[tarfile.TarInfo]:
    """Members safe to extract: relative files/dirs, no escapes."""
    safe = []
    for member in tar.getmembers():
        name = member.name
        if not name or name.startswith(("/", "\\")) or ".." in name.split("/"):
            continue
        if not (member.isfile() or member.isdir()):
            continue
        safe.append(member)
    return safe


class RepoSandbox:
    """Exec + write_file against /work; close with terminate()."""

    backend = "unknown"

    def exec(
        self, cmd: List[str], timeout: int = 300, network: bool = False
    ) -> Dict[str, object]:
        raise NotImplementedError

    def write_file(self, relpath: str, content: str) -> None:
        raise NotImplementedError

    def read_file(self, relpath: str) -> Optional[str]:
        """File content from /work, or None when missing/unreadable."""
        raise NotImplementedError

    def terminate(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> "RepoSandbox":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> None:
        self.terminate()


class ModalRepoSandbox(RepoSandbox):
    backend = "modal"

    def __init__(self, sandbox: object, timeout_s: int) -> None:
        self._sandbox = sandbox
        self._timeout_s = timeout_s

    def exec(
        self, cmd: List[str], timeout: int = 300, network: bool = False
    ) -> Dict[str, object]:
        _ = network  # Modal sandboxes always have network
        process = self._sandbox.exec(
            "timeout", str(timeout), *cmd, workdir="/work"
        )
        process.wait()
        stdout = process.stdout.read()
        stderr = process.stderr.read()
        code = process.returncode
        timed_out = code == 124
        return {
            "returncode": code,
            "stdout": stdout[-MAX_OUTPUT_CHARS:],
            "stderr": stderr[-MAX_OUTPUT_CHARS:],
            "timed_out": timed_out,
        }

    def write_file(self, relpath: str, content: str) -> None:
        # Portable: sh + base64 only, no guest Python assumed (L-J0).
        rel = _check_relpath(relpath)
        target = f"/work/{rel}"
        parent = os.path.dirname(target)
        encoded = base64.b64encode(content.encode()).decode()
        quoted_parent = "'" + parent.replace("'", "'\\''") + "'"
        quoted_target = "'" + target.replace("'", "'\\''") + "'"
        quoted_blob = "'" + encoded.replace("'", "'\\''") + "'"
        process = self._sandbox.exec(
            "sh",
            "-c",
            f"mkdir -p -- {quoted_parent} && "
            f"printf %s {quoted_blob} | base64 -d > {quoted_target}",
        )
        process.wait()
        if process.returncode != 0:
            raise RuntimeError(
                f"Could not write {relpath} in sandbox: "
                f"{process.stderr.read()}"
            )

    def read_file(self, relpath: str) -> Optional[str]:
        rel = _check_relpath(relpath)
        process = self._sandbox.exec("cat", f"/work/{rel}", workdir="/work")
        process.wait()
        if process.returncode != 0:
            return None
        return process.stdout.read()

    def terminate(self) -> None:
        try:
            self._sandbox.terminate()
        except Exception:
            pass


class DockerRepoSandbox(RepoSandbox):
    backend = "docker"

    def __init__(
        self, workdir: str, docker: str, image: str = DOCKER_IMAGE
    ) -> None:
        self._workdir = workdir
        self._docker = docker
        self._image = image
        self._tmp: Optional[tempfile.TemporaryDirectory] = None

    @classmethod
    def create(
        cls, snapshot_tar: bytes, docker: str, image: str = "python"
    ) -> "DockerRepoSandbox":
        tmp = tempfile.TemporaryDirectory(prefix="ta-repo-")
        with tarfile.open(fileobj=io.BytesIO(snapshot_tar)) as tar:
            tar.extractall(path=tmp.name, members=safe_members(tar))
        box = cls(tmp.name, docker, SANDBOX_IMAGES.get(image, DOCKER_IMAGE))
        box._tmp = tmp
        return box

    def exec(
        self, cmd: List[str], timeout: int = 300, network: bool = False
    ) -> Dict[str, object]:
        env = dict(os.environ)
        bindir = os.path.dirname(self._docker)
        if bindir:
            env["PATH"] = f"{bindir}:{env.get('PATH', '')}"
        try:
            completed = subprocess.run(
                [
                    self._docker, "run", "--rm",
                    "--network", "bridge" if network else "none",
                    "--memory", "1g", "--memory-swap", "1g",
                    "--cpus", "1.0",
                    "--pids-limit", "128",
                    "-v", f"{self._workdir}:/work",
                    "-w", "/work",
                    "-e", "PYTHONDONTWRITEBYTECODE=1",
                    "-e", "HOME=/tmp",
                    "-e", "PYTHONPATH=/work/.deps",
                    "-e", "PIP_TARGET=/work/.deps",
                    "-e", "PIP_DISABLE_PIP_VERSION_CHECK=1",
                    # Throwaway run per exec: only /work persists, so JVM
                    # caches live there (go/rust add theirs in L-J4/L-D2).
                    "-e", "MAVEN_OPTS=-Dmaven.repo.local=/work/.m2",
                    "-e", "GRADLE_USER_HOME=/work/.gradle",
                    self._image,
                    *cmd,
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            out = (exc.stderr or "") + (exc.stdout or "")
            return {
                "returncode": 124,
                "stdout": "",
                "stderr": out[-MAX_OUTPUT_CHARS:],
                "timed_out": True,
            }
        output = (completed.stderr or "") + (completed.stdout or "")
        if "Unable to find image" in output:
            raise SandboxUnavailable(
                f"Docker image '{self._image}' is missing; run "
                "./scripts/build-sandbox-image.sh to rebuild it."
            )
        return {
            "returncode": completed.returncode,
            "stdout": (completed.stdout or "")[-MAX_OUTPUT_CHARS:],
            "stderr": (completed.stderr or "")[-MAX_OUTPUT_CHARS:],
            "timed_out": False,
        }

    def write_file(self, relpath: str, content: str) -> None:
        rel = _check_relpath(relpath)
        target = os.path.join(self._workdir, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "w", encoding="utf-8") as handle:
            handle.write(content)

    def read_file(self, relpath: str) -> Optional[str]:
        # The container bind-mounts this dir, so the host copy is current.
        rel = _check_relpath(relpath)
        target = os.path.join(self._workdir, rel)
        try:
            with open(target, encoding="utf-8") as handle:
                return handle.read()
        except OSError:
            return None

    def terminate(self) -> None:
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None


def _open_modal(
    snapshot_tar: bytes, timeout_s: int, image: str = "python"
) -> ModalRepoSandbox:
    import modal

    app = modal.App.lookup("telemetry-agent-sandbox", create_if_missing=True)
    sandbox = modal.Sandbox.create(
        app=app, image=_modal_image(image), timeout=timeout_s
    )
    portable = image != "python"
    try:
        box = ModalRepoSandbox(sandbox, timeout_s)
        box.exec(["mkdir", "-p", "/work", "/tmp/snap"], timeout=60)
        for offset in range(0, len(snapshot_tar), UPLOAD_CHUNK):
            chunk = snapshot_tar[offset : offset + UPLOAD_CHUNK]
            encoded = base64.b64encode(chunk).decode()
            process = sandbox.exec(
                *_append_cmd("/tmp/snap/snapshot.tar.gz", encoded, portable)
            )
            process.wait()
            if process.returncode != 0:
                raise RuntimeError(
                    "snapshot upload failed: " + process.stderr.read()
                )
        # snapshot.filter_snapshot already stripped the tarball's top dir.
        result = box.exec(
            ["tar", "xzf", "/tmp/snap/snapshot.tar.gz", "-C", "/work"],
            timeout=120,
        )
        if result["returncode"] != 0:
            raise RuntimeError(
                f"snapshot extract failed: {result['stderr']}"
            )
        return box
    except BaseException:
        try:
            sandbox.terminate()
        except Exception:
            pass
        raise


def _open_docker(snapshot_tar: bytes, image: str) -> DockerRepoSandbox:
    docker = resolve_docker()
    if docker is None:
        raise SandboxUnavailable(
            "Docker is not installed; cannot run repo verification."
        )
    return DockerRepoSandbox.create(snapshot_tar, docker, image)


def open_repo_sandbox(
    snapshot_tar: bytes, timeout_s: int = 1800, image: str = "python"
) -> RepoSandbox:
    """Upload the snapshot; Modal first, Docker on any Modal failure.

    `image` selects the language image (SANDBOX_IMAGES keys on Docker,
    `_modal_image` on Modal); unknown keys fall back to python.
    """
    if os.environ.get("TA_VERIFY", "").lower() == "local":
        return _open_docker(snapshot_tar, image)
    try:
        return _open_modal(snapshot_tar, timeout_s, image)
    except SandboxUnavailable:
        raise
    except Exception as exc:
        modal_reason = f"{type(exc).__name__}: {exc}"
    try:
        return _open_docker(snapshot_tar, image)
    except SandboxUnavailable as exc:
        raise SandboxUnavailable(
            f"Modal failed ({modal_reason}) and Docker is unavailable "
            f"({exc})"
        ) from exc


def selected_backend() -> str:
    """Backend `open_repo_sandbox` would try first (reporting only)."""
    if os.environ.get("TA_VERIFY", "").lower() == "local":
        return "docker"
    try:
        import modal  # noqa: F401
    except ImportError:
        return "docker"
    return "modal"
