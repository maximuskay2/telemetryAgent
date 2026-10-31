"""Session/device auth + request resolution (C-J2, §8.3 frozen shape).

The middleware resolves every request to (org_id, user_id, role, auth_mode)
on `request.state` and enforces auth ONLY on the C-J2-owned paths (the
commerce router + approve/disapprove/pause/execute). Every other route
passes through with its existing gates until C-J3 threads org scoping.

Self-hosted (no DATABASE_URL): transparent — today's behaviour exactly,
state.org_id "self", mode "open".

Session users carry a provider JWT (Clerk, RS256 via JWKS) and name their
org per request with X-Org-Id (org switcher); membership — and therefore
the role — is read per request, so a removed member dies immediately.
Device tokens (ta_dev_) resolve org+user from the token row. Provisioning
is just-in-time: the first verified JWT creates the user row.
"""

from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from core.commerce import models

#: Paths that never need session auth (§8.3, exact; C-J3 secures /api/ws).
PUBLIC_PATHS = (
    "/api/health",
    "/forwarder.py",
    "/api/sim/*",
    "/api/demo/*",
    "/api/samples/*",
    "/api/run",
    "/api/run/*",
    "/api/logs",
    "/api/diagnose",
    "/api/telemetry/*",
    "/api/pairing",
    "/api/ingest/*",
    "/api/devices/*/commands",
    "/api/devices/*/commands/*/ack",
    "/api/devices/*/readings",
    "/api/devices/claim",
    "/api/invites/*/accept",
)

#: Paths the C-J2 middleware enforces (everything else passes through
#: with its existing gates until C-J3). Claim/accept routes are public —
#: they authenticate via the code/token in the body, not a bearer token.
ENFORCED_PREFIXES = (
    "/api/orgs",
    "/api/admin/",
)

ORG_HEADER = "X-Org-Id"
DEVICE_PREFIX = models.DEVICE_KEY_PREFIX
INGEST_PREFIX = "ta_live_"


class AuthError(Exception):
    """Carries an HTTP status + detail for the middleware/routes."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


@dataclass
class AuthContext:
    org_id: str = ""
    user_id: str = ""
    role: str = ""
    auth_mode: str = "open"  # session|device|ingest|open
    email: str = ""


def is_public(path: str) -> bool:
    return any(fnmatch.fnmatch(path, pat) for pat in PUBLIC_PATHS)


def _is_enforced(path: str) -> bool:
    return any(
        path == prefix.rstrip("/") or path.startswith(prefix)
        for prefix in ENFORCED_PREFIXES
    )


# --- session tokens ------------------------------------------------------


def _test_secret() -> str:
    return os.environ.get("TA_AUTH_TEST_ISSUER", "").strip()


def verify_session_token(token: str) -> Dict[str, str]:
    """{external_id, email} for a valid session JWT, else AuthError(401)."""
    import jwt

    secret = _test_secret()
    if secret:
        try:
            claims = jwt.decode(
                token, secret, algorithms=["HS256"],
                options={"require": ["sub", "exp"]},
            )
        except Exception as exc:
            raise AuthError(401, "bad session token") from exc
        return {
            "external_id": f"test|{claims['sub']}",
            "email": str(claims.get("email", "") or ""),
        }
    jwks_url = os.environ.get("CLERK_JWKS_URL", "").strip()
    if not jwks_url:
        raise AuthError(401, "sign-in is not configured here")
    try:
        key = _signing_key(jwks_url, token)
        claims = jwt.decode(
            token, key, algorithms=["RS256"],
            options={"require": ["sub", "exp"]},
        )
    except AuthError:
        raise
    except Exception as exc:
        raise AuthError(401, "bad session token") from exc
    email = str(claims.get("email", "") or "")
    if not email:
        email = _clerk_email(str(claims["sub"]))
    return {"external_id": f"clerk|{claims['sub']}", "email": email}


_jwks_clients: Dict[str, Any] = {}


def clear_jwks_cache() -> None:
    _jwks_clients.clear()


def _signing_key(jwks_url: str, token: str):
    """Provider public key for the token (client cached per process)."""
    from jwt import PyJWKClient

    client = _jwks_clients.get(jwks_url)
    if client is None:
        client = PyJWKClient(jwks_url)
        _jwks_clients[jwks_url] = client
    try:
        return client.get_signing_key_from_jwt(token).key
    except Exception as exc:
        raise AuthError(401, "unknown signing key") from exc


def _clerk_email(sub: str) -> str:
    """Backfill email from the Clerk API (cached in the user row after)."""
    import httpx

    secret = os.environ.get("CLERK_SECRET_KEY", "").strip()
    base = os.environ.get("CLERK_API_URL", "https://api.clerk.com/v1").strip()
    base = base.rstrip("/")
    if not base.endswith("/v1"):
        base += "/v1"
    if not secret:
        return ""
    try:
        response = httpx.get(
            f"{base}/users/{sub}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=10,
        )
        response.raise_for_status()
        addresses = response.json().get("email_addresses", [])
    except Exception:
        return ""
    for entry in addresses:
        if entry.get("id") == response.json().get(
            "primary_email_address_id"
        ):
            return str(entry.get("email_address", "") or "")
    return str(addresses[0].get("email_address", "") or "") if addresses else ""


# --- resolution ------------------------------------------------------------


def provision_user(store, external_id: str, email: str):
    """Fetch-or-create the user row; backfill a newly known email."""
    user = store.get_user_by_external(external_id)
    if user is not None:
        return user
    name = email.split("@")[0] if email else ""
    return store.create_user(external_id, email, name)


def _header(headers, name: str) -> str:
    """Case-tolerant header read (Starlette Headers or a plain dict)."""
    if isinstance(headers, dict):
        lowered = {
            str(key).lower(): value for key, value in headers.items()
        }
        return str(lowered.get(name.lower(), "") or "").strip()
    get = getattr(headers, "get", None)
    if get is None:
        return ""
    try:
        return str(get(name, "") or "").strip()
    except TypeError:
        return ""


def _bearer(headers) -> str:
    scheme, _, value = _header(headers, "authorization").partition(" ")
    if scheme.lower() != "bearer" or not value.strip():
        return ""
    return value.strip()


def resolve_request(store, path: str, headers) -> AuthContext:
    """Resolve auth for one request (pure; no FastAPI needed).

    Raises AuthError(401/403/400) only for enforced paths; public and
    pass-through paths resolve best-effort and never raise.
    """
    from core.connections import store as connection_store

    ctx = AuthContext()
    if is_public(path):
        return ctx
    token = _bearer(headers)
    enforced = _is_enforced(path)
    if not token:
        if enforced:
            raise AuthError(401, "sign-in required")
        return ctx
    if token.startswith(DEVICE_PREFIX):
        row = store.get_device_token_by_hash(
            connection_store.hash_key(token)
        )
        if row is None or row.get("revoked_at"):
            if enforced:
                raise AuthError(401, "unknown or revoked device token")
            return ctx
        scoped = store.scoped(row["org_id"], row["user_id"])
        membership = scoped.get_membership(row["org_id"], row["user_id"])
        if membership is None:
            if enforced:
                raise AuthError(403, "no longer a member of this org")
            return ctx
        scoped.touch_device_token(row["id"])
        return AuthContext(
            org_id=row["org_id"],
            user_id=row["user_id"],
            role=str(membership.get("role", "")),
            auth_mode="device",
        )
    if token.startswith(INGEST_PREFIX):
        # Ingest keys authenticate ingest/device-key routes only, which are
        # public and resolve the key themselves. Anywhere else: reject.
        if enforced:
            raise AuthError(401, "ingest keys cannot sign in")
        return ctx
    try:
        identity = verify_session_token(token)
    except AuthError:
        if enforced:
            raise
        return ctx
    user = provision_user(
        store, identity["external_id"], identity["email"]
    )
    org_id = _header(headers, ORG_HEADER)
    if not org_id:
        return AuthContext(
            user_id=user["id"], auth_mode="session", email=user["email"]
        )
    membership = store.scoped(org_id, user["id"]).get_membership(
        org_id, user["id"]
    )
    if membership is None:
        if enforced:
            raise AuthError(403, "no longer a member of this org")
        return AuthContext(
            user_id=user["id"], auth_mode="session", email=user["email"]
        )
    return AuthContext(
        org_id=org_id,
        user_id=user["id"],
        role=str(membership.get("role", "")),
        auth_mode="session",
        email=user["email"],
    )


def require_roles(ctx: AuthContext, *roles: str) -> None:
    """Raise 403 unless the caller holds one of `roles` (owner passes all)."""
    if ctx.role == "owner":
        return
    if ctx.role not in roles:
        raise AuthError(403, "this needs a higher org role")


def hosted() -> bool:
    """True when org data lives in Postgres (DATABASE_URL set)."""
    return bool(os.environ.get("DATABASE_URL", "").strip())


def req_ctx(request) -> AuthContext:
    """Commerce auth context for this request (empty when self-hosted)."""
    return getattr(request.state, "auth", None) or AuthContext()


def need(request, *roles: str) -> AuthContext:
    """Role guard for product mutations.

    Self-hosted: no-op (existing open/code gates apply). Hosted: session
    or device auth + org membership + one of `roles` (owner passes all).
    Raises AuthError(401/403), or AuthError(400) without an org selected.
    """
    ctx = req_ctx(request)
    if not hosted():
        return ctx
    if not ctx.user_id:
        raise AuthError(401, "sign-in required")
    if not ctx.org_id:
        raise AuthError(400, "X-Org-Id required")
    require_roles(ctx, *roles)
    return ctx


def read_org(request) -> str:
    """Org scope for demo-channel reads ("" = demo/self-hosted)."""
    if not hosted():
        return ""
    return req_ctx(request).org_id or ""


def resolve_ws_token(
    store, token: str, org_id: str = ""
) -> AuthContext:
    """Join-channel auth for /api/ws?token= (&org= for sessions).

    Device tokens join their org; session tokens join the named org they
    belong to. Raises AuthError(401/403) — the route closes the socket.
    """
    from core.connections import store as connection_store

    if token.startswith(DEVICE_PREFIX):
        row = store.get_device_token_by_hash(
            connection_store.hash_key(token)
        )
        if row is None or row.get("revoked_at"):
            raise AuthError(401, "unknown or revoked device token")
        if org_id and org_id != row["org_id"]:
            raise AuthError(403, "device token belongs to another org")
        scoped = store.scoped(row["org_id"], row["user_id"])
        membership = scoped.get_membership(row["org_id"], row["user_id"])
        if membership is None:
            raise AuthError(403, "no longer a member of this org")
        scoped.touch_device_token(row["id"])
        return AuthContext(
            org_id=row["org_id"],
            user_id=row["user_id"],
            role=str(membership.get("role", "")),
            auth_mode="device",
        )
    identity = verify_session_token(token)
    user = provision_user(
        store, identity["external_id"], identity["email"]
    )
    if not org_id:
        raise AuthError(401, "org query param required")
    membership = store.scoped(org_id, user["id"]).get_membership(
        org_id, user["id"]
    )
    if membership is None:
        raise AuthError(403, "no longer a member of this org")
    return AuthContext(
        org_id=org_id,
        user_id=user["id"],
        role=str(membership.get("role", "")),
        auth_mode="session",
        email=user["email"],
    )


def authorize_action_run(ctx: AuthContext, entry: Dict[str, Any]) -> None:
    """Gate approve/disapprove/pause/execute on an in-memory run entry.

    Entries without an org (sim/demo runs) stay public per the §8.3 demo
    channel. Entries tagged org_id (org runs; the pipeline tags them at
    C-J3) need member+.
    """
    org_id = str(entry.get("org_id", "") or "")
    if not org_id or org_id == models.DEMO_ORG_ID:
        return
    if not ctx.user_id:
        raise AuthError(401, "sign-in required")
    if ctx.org_id != org_id:
        raise AuthError(403, "this run belongs to another org")
    require_roles(ctx, "admin", "member")
