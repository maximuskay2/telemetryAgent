"""Production-route contracts (production-roadmap §3.4, frozen at H0).

Every model here mirrors the §3.4 JSONC sketches exactly. John mirrors them
in `apps/web/app/types/production.ts` and `apps/mobile/lib/models/`.
R-1: a contract change needs BOTH agents to agree plus a one-line note in
the roadmap §8 log — never change this file alone after the H0 commit.

Secrets are never returned by the API: connections expose only `secret_hint`,
and an ingest/device key is shown once, on create.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

ConnectionKind = Literal["logs", "sentry", "github", "railway", "webhook", "device"]
ConnectionStatus = Literal["waiting", "ok", "error"]
OptionKind = Literal["open_pr", "rollback", "restart", "remote", "manual", "dispatch"]
OptionStatus = Literal[
    "available", "sent", "done", "failed", "expired", "cancelled"
]
DeviceAction = Literal["defrost", "setpoint", "power_cycle", "backup_on"]
RunDomain = Literal["software", "appliance"]


class Connection(BaseModel):
    id: str = Field(min_length=1)
    system_id: str = Field(min_length=1)
    kind: ConnectionKind
    config: dict = Field(default_factory=dict)
    secret_hint: str = ""
    status: ConnectionStatus = "waiting"
    detail: str = ""
    last_seen: float = 0.0


class ConnectionCreate(BaseModel):
    system_id: str = Field(min_length=1, max_length=100)
    kind: ConnectionKind
    config: dict = Field(default_factory=dict)
    secret: Optional[str] = Field(default=None, max_length=500)


class ConnectionCreated(BaseModel):
    connection: Connection
    key: Optional[str] = Field(
        default=None, description="Shown once on create, never again"
    )


class ConnectionList(BaseModel):
    connections: list[Connection] = Field(default_factory=list)


class TestPermissions(BaseModel):
    read: bool = False
    pull_requests: bool = False


class ConnectionTest(BaseModel):
    ok: bool
    detail: str = ""
    permissions: Optional[TestPermissions] = None


class IngestLine(BaseModel):
    ts: float = 0.0
    level: str = "INFO"
    message: str = Field(min_length=1, max_length=20000)


class IngestLogsIn(BaseModel):
    service: str = Field(min_length=1, max_length=100)
    release: str = ""
    commit: str = ""
    lines: list[IngestLine] = Field(min_length=1, max_length=500)


class IngestResult(BaseModel):
    accepted: int
    candidates: int = 0


class SentryAccepted(BaseModel):
    accepted: int


class OptionSafety(BaseModel):
    ok: bool
    reason: str = ""


class Option(BaseModel):
    id: str = Field(min_length=1)
    kind: OptionKind
    title: str = Field(min_length=1)
    detail: str = ""
    url: str = ""
    safety: OptionSafety = Field(default_factory=lambda: OptionSafety(ok=True))
    status: OptionStatus = "available"


class OptionsResult(BaseModel):
    run_id: str
    domain: RunDomain
    options: list[Option] = Field(default_factory=list)


class OptionExecuted(BaseModel):
    status: str
    command_id: str = ""


class DeviceCommand(BaseModel):
    id: str = Field(min_length=1)
    action: DeviceAction
    params: dict = Field(default_factory=dict)
    expires_at: float = 0.0


class CommandList(BaseModel):
    commands: list[DeviceCommand] = Field(default_factory=list)


class CommandAck(BaseModel):
    ok: bool
    detail: str = ""


class AckResult(BaseModel):
    status: str


class EnabledResult(BaseModel):
    enabled: bool


class PauseState(BaseModel):
    paused: bool


class SuiteSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    new_failures: int = 0


class MitigationSummary(BaseModel):
    action: str = ""
    status: str = ""


class SoftwareRunResult(BaseModel):
    """Additive optional fields on a software run (James fills, John reads)."""

    pr_url: str = ""
    repo: str = ""
    suite: Optional[SuiteSummary] = None
    mitigation: Optional[MitigationSummary] = None


# --- H0 stub fixtures ------------------------------------------------------
# The stub routers return these verbatim so John can build against stable
# shapes before the real logic lands. Scalar values follow §3.4.

FIXTURE_CONNECTION: dict = {
    "id": "con_ab12",
    "system_id": "acme-api-9f2c",
    "kind": "logs",
    "config": {"service": "api"},
    "secret_hint": "****abcd",
    "status": "waiting",
    "detail": "",
    "last_seen": 1730200000.0,
}

#: The one key the H0 auth stub accepts (J-R0 gates it behind TA_FIXTURE_KEYS).
FIXTURE_KEY = "ta_live_fixture"

#: System the fixture key authenticates as in the H0 stubs.
FIXTURE_SYSTEM_ID = "acme-api-9f2c"

FIXTURE_CONNECTION_TEST: dict = {
    "ok": True,
    "detail": "stub: reachable",
    "permissions": {"read": True, "pull_requests": True},
}

FIXTURE_INGEST_RESULT: dict = {"accepted": 3, "candidates": 1}

FIXTURE_SENTRY_RESULT: dict = {"accepted": 1}

FIXTURE_OPTION: dict = {
    "id": "opt_1",
    "kind": "open_pr",
    "title": "Open fix PR",
    "detail": "Verified fix: reproduce test fails, patch passes, suite green",
    "url": "https://github.com/acme/api/pull/7",
    "safety": {"ok": True, "reason": ""},
    "status": "available",
}

FIXTURE_DEVICE_COMMAND: dict = {
    "id": "cmd_1",
    "action": "defrost",
    "params": {},
    "expires_at": 1730200120.0,
}

FIXTURE_SUITE: dict = {"passed": 212, "failed": 0, "new_failures": 0}
