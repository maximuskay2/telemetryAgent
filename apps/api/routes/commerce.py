"""Orgs, members, invites, devices, usage, admin routes (C-J2, §8.4 frozen).

Session JWT (or device token) on every route here except claim/accept,
which authenticate via the code/token in the body. Roles follow the §8.3
matrix; membership is read per request, so removal bites immediately.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from core.commerce import auth as auth_module
from core.commerce import repo as repo_module

router = APIRouter()

_GRACE_S = 30 * 86400


def _store():
    return repo_module.get_store()


async def _call(func, *args, **kwargs):
    return await asyncio.to_thread(func, *args, **kwargs)


def _ctx(request: Request) -> auth_module.AuthContext:
    ctx = getattr(request.state, "auth", None)
    if ctx is None:
        return auth_module.AuthContext()
    return ctx


async def _role_in(request: Request, org_id: str) -> str:
    """Role of the caller in `org_id` (401/403 when missing).

    The middleware resolves the caller; the path org is verified here
    because session callers name their org per request (X-Org-Id) and the
    path may name another. Device tokens are org-bound.
    """
    ctx = _ctx(request)
    if not ctx.user_id:
        raise HTTPException(status_code=401, detail="sign-in required")
    if ctx.auth_mode == "device" and ctx.org_id != org_id:
        raise HTTPException(
            status_code=403, detail="device token belongs to another org"
        )
    membership = await _call(
        _store().scoped(org_id, ctx.user_id).get_membership,
        org_id,
        ctx.user_id,
    )
    if membership is None:
        raise HTTPException(
            status_code=403, detail="no longer a member of this org"
        )
    return str(membership.get("role", ""))


def _needs(*roles: str):
    """Route guard factory: caller must hold one of `roles` (owner passes)."""

    async def guard(request: Request, org_id: str) -> str:
        role = await _role_in(request, org_id)
        if role == "owner":
            return role
        if role not in roles:
            raise HTTPException(
                status_code=403, detail="this needs a higher org role"
            )
        return role

    return guard


_need_member = _needs("admin", "member", "viewer")
_need_actor = _needs("admin", "member")
_need_admin = _needs("admin")


async def _session_user(request: Request) -> dict:
    """User for a bearer session JWT (claim/accept routes; public paths)."""
    scheme, _, token = request.headers.get("authorization", "").partition(
        " "
    )
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="sign-in required")
    try:
        identity = await _call(
            auth_module.verify_session_token, token.strip()
        )
    except auth_module.AuthError as exc:
        raise HTTPException(
            status_code=exc.status, detail=exc.detail
        ) from exc
    store = _store()
    return await _call(
        auth_module.provision_user,
        store,
        identity["external_id"],
        identity["email"],
    )


class OrgCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class InviteCreateIn(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    role: str = Field(default="member", max_length=20)


class TransferIn(BaseModel):
    user_id: str = Field(min_length=1, max_length=100)


class PairIn(BaseModel):
    label: str = Field(default="", max_length=120)


class ClaimIn(BaseModel):
    code: str = Field(min_length=1, max_length=20)


def _org_json(row: dict, role: str = "") -> dict:
    out = {
        "id": row.get("id", ""),
        "name": row.get("name", ""),
        "created_at": row.get("created_at", 0.0),
    }
    if role:
        out["role"] = role
    return out


@router.post("/api/orgs")
async def create_org(request: Request, payload: OrgCreateIn) -> dict:
    ctx = _ctx(request)
    if not ctx.user_id:
        raise HTTPException(status_code=401, detail="sign-in required")
    store = _store().scoped("", ctx.user_id)
    row = await _call(store.create_org, payload.name.strip(), ctx.user_id)
    await _call(store.scoped(row["id"], ctx.user_id).get_allowance, row["id"])
    return {"org": _org_json(row, "owner")}


@router.get("/api/orgs")
async def list_orgs(request: Request) -> dict:
    ctx = _ctx(request)
    if not ctx.user_id:
        raise HTTPException(status_code=401, detail="sign-in required")
    store = _store().scoped("", ctx.user_id)
    rows = await _call(store.list_orgs_for_user)
    return {"orgs": [_org_json(row, str(row.get("role", ""))) for row in rows]}


@router.get("/api/orgs/{org_id}")
async def get_org(request: Request, org_id: str) -> dict:
    role = await _role_in(request, org_id)
    ctx = _ctx(request)
    row = await _call(
        _store().scoped(org_id, ctx.user_id).get_org, org_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="unknown org")
    return {"org": _org_json(row), "role": role}


@router.delete("/api/orgs/{org_id}")
async def delete_org(request: Request, org_id: str) -> dict:
    role = await _role_in(request, org_id)
    if role != "owner":
        raise HTTPException(
            status_code=403, detail="only the owner deletes the org"
        )
    ctx = _ctx(request)
    grace_until = time.time() + _GRACE_S
    ok = await _call(
        _store().scoped(org_id, ctx.user_id).soft_delete_org,
        org_id,
        grace_until,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="unknown org")
    return {"deleted": True, "grace_until": grace_until}


@router.get("/api/orgs/{org_id}/members")
async def list_members(request: Request, org_id: str) -> dict:
    await _need_member(request, org_id)
    ctx = _ctx(request)
    rows = await _call(
        _store().scoped(org_id, ctx.user_id).list_members, org_id
    )
    return {
        "members": [
            {
                "user_id": row.get("user_id", ""),
                "email": row.get("email", ""),
                "name": row.get("name", ""),
                "role": row.get("role", ""),
            }
            for row in rows
        ]
    }


@router.post("/api/orgs/{org_id}/invites")
async def create_invite(
    request: Request, org_id: str, payload: InviteCreateIn
) -> dict:
    await _need_admin(request, org_id)
    wanted = payload.role.strip().lower()
    if wanted not in ("admin", "member", "viewer"):
        raise HTTPException(status_code=400, detail="bad role")
    ctx = _ctx(request)
    store = _store().scoped(org_id, ctx.user_id)
    _row, token = await _call(
        store.create_invite, org_id, payload.email.strip(), wanted
    )
    return {"invite": {"token": token, "expires_at": time.time() + 7 * 86400}}


@router.post("/api/invites/{token}/accept")
async def accept_invite(request: Request, token: str) -> dict:
    user = await _session_user(request)
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    store = _store()
    invite = await _call(store.get_invite_by_hash, digest)
    if invite is None:
        raise HTTPException(status_code=404, detail="unknown invite")
    if invite.get("accepted_at"):
        raise HTTPException(status_code=409, detail="invite already used")
    if float(invite.get("expires_at", 0.0) or 0.0) <= time.time():
        raise HTTPException(status_code=410, detail="invite expired")
    both_known = invite.get("email") and user.get("email")
    if both_known and invite["email"].lower() != user["email"].lower():
        raise HTTPException(
            status_code=403, detail="this invite is for someone else"
        )
    org_id = str(invite.get("org_id", ""))
    scoped = store.scoped(org_id, user["id"])
    await _call(
        scoped.add_membership, org_id, user["id"], str(invite.get("role"))
    )
    await _call(store.scoped(org_id, user["id"]).mark_invite_accepted, digest)
    return {"org_id": org_id, "role": str(invite.get("role", ""))}


@router.delete("/api/orgs/{org_id}/members/{user_id}")
async def remove_member(request: Request, org_id: str, user_id: str) -> dict:
    role = await _need_admin(request, org_id)
    ctx = _ctx(request)
    store = _store().scoped(org_id, ctx.user_id)
    target = await _call(store.get_membership, org_id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not a member")
    if target.get("role") == "owner":
        if role != "owner":
            raise HTTPException(
                status_code=403, detail="only an owner removes an owner"
            )
        members = await _call(store.list_members, org_id)
        owners = [m for m in members if m.get("role") == "owner"]
        if len(owners) <= 1:
            raise HTTPException(
                status_code=409,
                detail="transfer ownership first (sole owner)",
            )
    await _call(store.remove_membership, org_id, user_id)
    return {"removed": True}


@router.post("/api/orgs/{org_id}/transfer")
async def transfer_ownership(
    request: Request, org_id: str, payload: TransferIn
) -> dict:
    role = await _role_in(request, org_id)
    if role != "owner":
        raise HTTPException(
            status_code=403, detail="only the owner transfers ownership"
        )
    ctx = _ctx(request)
    store = _store().scoped(org_id, ctx.user_id)
    target = await _call(store.get_membership, org_id, payload.user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="not a member")
    await _call(store.set_role, org_id, payload.user_id, "owner")
    await _call(store.set_role, org_id, ctx.user_id, "admin")
    return {"ok": True}


@router.post("/api/orgs/{org_id}/devices/pair")
async def pair_device(
    request: Request, org_id: str, payload: PairIn
) -> dict:
    await _need_actor(request, org_id)
    ctx = _ctx(request)
    store = _store().scoped(org_id, ctx.user_id)
    _row, code = await _call(
        store.create_pairing_code,
        org_id,
        ctx.user_id,
        payload.label.strip(),
    )
    return {"code": code, "expires_at": time.time() + 600}


@router.post("/api/devices/claim")
async def claim_device(request: Request, payload: ClaimIn) -> dict:
    store = _store()
    claimed = await _call(store.claim_pairing_code, payload.code.strip())
    if claimed is None:
        raise HTTPException(
            status_code=404, detail="unknown or expired code"
        )
    scoped = store.scoped(claimed["org_id"], claimed["user_id"])
    row, token = await _call(
        scoped.create_device_token,
        claimed["org_id"],
        claimed["user_id"],
        str(claimed.get("label", "")),
    )
    _ = row
    return {"device_token": token, "org_id": claimed["org_id"]}


@router.get("/api/orgs/{org_id}/devices")
async def list_devices(request: Request, org_id: str) -> dict:
    await _need_member(request, org_id)
    ctx = _ctx(request)
    rows = await _call(
        _store().scoped(org_id, ctx.user_id).list_device_tokens, org_id
    )
    return {
        "devices": [
            {
                "id": row.get("id", ""),
                "label": row.get("label", ""),
                "created_at": row.get("created_at", 0.0),
                "last_used_at": row.get("last_used_at") or 0.0,
                "revoked": bool(row.get("revoked_at")),
            }
            for row in rows
        ]
    }


@router.post("/api/orgs/{org_id}/devices/{device_id}/revoke")
async def revoke_device(
    request: Request, org_id: str, device_id: str
) -> dict:
    ctx = _ctx(request)
    if not ctx.user_id:
        raise HTTPException(status_code=401, detail="sign-in required")
    store = _store().scoped(org_id, ctx.user_id)
    rows = await _call(store.list_device_tokens, org_id)
    target = next((r for r in rows if r.get("id") == device_id), None)
    if target is None:
        raise HTTPException(status_code=404, detail="unknown device")
    if target.get("user_id") != ctx.user_id:
        role = await _role_in(request, org_id)
        if role not in ("owner", "admin"):
            raise HTTPException(
                status_code=403, detail="only the owner or an admin revokes"
            )
    await _call(store.revoke_device_token, device_id, org_id)
    return {"revoked": True}


@router.get("/api/orgs/{org_id}/usage")
async def org_usage(request: Request, org_id: str, period: str = "month") -> dict:
    await _need_member(request, org_id)
    from core.commerce import usage as usage_module

    return await _call(usage_module.usage_summary, org_id, period)


@router.get("/api/admin/costs")
async def admin_costs(request: Request) -> dict:
    ctx = _ctx(request)
    if not ctx.user_id or not ctx.email:
        raise HTTPException(status_code=403, detail="admins only")
    admins = {
        item.strip().lower()
        for item in os.environ.get("COMMERCE_ADMIN_EMAILS", "").split(",")
        if item.strip()
    }
    if ctx.email.lower() not in admins:
        raise HTTPException(status_code=403, detail="admins only")
    from core.commerce import usage as usage_module

    return await _call(usage_module.admin_cost_overview)
