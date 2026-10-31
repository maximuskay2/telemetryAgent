"""Commerce API: auth resolution + org/member/device/usage routes (C-J2).

Resolution unit tests run on the file backend (no Postgres). Route tests
run hosted (DATABASE_URL → ta_test role) through TestClient and skip when
Postgres is unreachable. Self-hosted transparency is covered by the
pre-existing suite (no DATABASE_URL anywhere there).
"""

from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from tests.commerce_auth import TEST_SECRET, mint, test_env
from tests.commerce_db import app_url, db_available, fixture


def _file_store(tmp: str):
    from core.commerce import repo as repo_module

    return repo_module.FileBackend(root=None, org_id="", user_id="")


class ResolveUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.mkdtemp(prefix="ta-com-auth-")
        self.addCleanup(
            lambda: __import__("shutil").rmtree(tmp, ignore_errors=True)
        )
        env = {"TA_DATA_DIR": tmp, **test_env()}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("DATABASE_URL", None)
        from core.commerce import repo as repo_module

        self.store = repo_module.FileBackend()
        self.user = self.store.create_user("test|u1", "a@x.co", "A")
        self.org = self.store.create_org("Acme", self.user["id"])

    def _resolve(self, path, headers=None):
        from core.commerce import auth as auth_module

        return auth_module.resolve_request(
            self.store, path, headers or {}
        )

    def test_public_path_open_with_garbage_token(self) -> None:
        ctx = self._resolve(
            "/api/health", {"Authorization": "Bearer [REDACTED]"}
        )
        self.assertEqual(ctx.auth_mode, "open")
        ctx = self._resolve("/api/sim/shop/load", {})
        self.assertEqual(ctx.auth_mode, "open")

    def test_enforced_path_needs_token(self) -> None:
        from core.commerce import auth as auth_module

        with self.assertRaises(auth_module.AuthError) as raised:
            self._resolve("/api/orgs", {})
        self.assertEqual(raised.exception.status, 401)

    def test_session_provisions_user_and_checks_membership(self) -> None:
        from core.commerce import auth as auth_module

        token = mint("u9", "new@x.co")
        ctx = self._resolve(
            "/api/orgs",
            {"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(ctx.auth_mode, "session")
        self.assertTrue(ctx.user_id)
        # Unknown org for this user → 403 on enforced paths.
        with self.assertRaises(auth_module.AuthError) as raised:
            self._resolve(
                "/api/orgs",
                {
                    "Authorization": f"Bearer {token}",
                    "X-Org-Id": self.org["id"],
                },
            )
        self.assertEqual(raised.exception.status, 403)
        # Owner resolves with role.
        ctx = self._resolve(
            "/api/orgs",
            {
                "Authorization": f"Bearer {mint('u1', 'a@x.co')}",
                "X-Org-Id": self.org["id"],
            },
        )
        self.assertEqual(ctx.role, "owner")
        self.assertEqual(ctx.org_id, self.org["id"])

    def test_device_token_lifecycle(self) -> None:
        from core.commerce import auth as auth_module

        _row, token = self.store.create_device_token(
            self.org["id"], self.user["id"], "Pixel"
        )
        ctx = self._resolve(
            "/api/orgs", {"Authorization": f"Bearer {token}"}
        )
        self.assertEqual(ctx.auth_mode, "device")
        self.assertEqual(ctx.org_id, self.org["id"])
        self.assertEqual(ctx.role, "owner")
        # Revoked → 401; removed member → 403.
        rows = self.store.list_device_tokens(self.org["id"])
        self.store.revoke_device_token(rows[0]["id"], self.org["id"])
        with self.assertRaises(auth_module.AuthError) as raised:
            self._resolve("/api/orgs", {"Authorization": f"Bearer {token}"})
        self.assertEqual(raised.exception.status, 401)

        _row2, token2 = self.store.create_device_token(
            self.org["id"], self.user["id"], "Pixel2"
        )
        self.store.remove_membership(self.org["id"], self.user["id"])
        with self.assertRaises(auth_module.AuthError) as raised:
            self._resolve("/api/orgs", {"Authorization": f"Bearer {token2}"})
        self.assertEqual(raised.exception.status, 403)

    def test_ingest_key_cannot_sign_in(self) -> None:
        from core.commerce import auth as auth_module

        _row, key = self.store.create_connection(
            "self", "shop-1", "logs", {}, None
        )
        with self.assertRaises(auth_module.AuthError) as raised:
            self._resolve("/api/orgs", {"Authorization": f"Bearer {key}"})
        self.assertEqual(raised.exception.status, 401)

    def test_bad_token_raises_only_on_enforced(self) -> None:
        from core.commerce import auth as auth_module

        headers = {"Authorization": "Bearer [REDACTED]"}
        with self.assertRaises(auth_module.AuthError):
            self._resolve("/api/orgs", headers)
        ctx = self._resolve("/api/systems", headers)
        self.assertEqual(ctx.auth_mode, "open")

    def test_authorize_action_run(self) -> None:
        from core.commerce import auth as auth_module

        # Demo entries (no org tag) stay public.
        auth_module.authorize_action_run(auth_module.AuthContext(), {})
        auth_module.authorize_action_run(
            auth_module.AuthContext(), {"org_id": "demo"}
        )
        member = auth_module.AuthContext(
            org_id=self.org["id"],
            user_id=self.user["id"],
            role="member",
            auth_mode="session",
        )
        auth_module.authorize_action_run(
            member, {"org_id": self.org["id"]}
        )
        viewer = auth_module.AuthContext(
            org_id=self.org["id"],
            user_id=self.user["id"],
            role="viewer",
            auth_mode="session",
        )
        with self.assertRaises(auth_module.AuthError) as raised:
            auth_module.authorize_action_run(
                viewer, {"org_id": self.org["id"]}
            )
        self.assertEqual(raised.exception.status, 403)
        with self.assertRaises(auth_module.AuthError) as raised:
            auth_module.authorize_action_run(
                auth_module.AuthContext(), {"org_id": self.org["id"]}
            )
        self.assertEqual(raised.exception.status, 401)
        with self.assertRaises(auth_module.AuthError) as raised:
            auth_module.authorize_action_run(
                member, {"org_id": "org_other"}
            )
        self.assertEqual(raised.exception.status, 403)

    def test_require_roles_owner_passes(self) -> None:
        from core.commerce import auth as auth_module

        owner = auth_module.AuthContext(role="owner")
        auth_module.require_roles(owner, "admin")
        member = auth_module.AuthContext(role="member")
        with self.assertRaises(auth_module.AuthError):
            auth_module.require_roles(member, "admin")

    def test_test_issuer_rejects_bad_and_expired(self) -> None:
        from core.commerce import auth as auth_module

        with self.assertRaises(auth_module.AuthError):
            auth_module.verify_session_token("nope")
        with self.assertRaises(auth_module.AuthError):
            auth_module.verify_session_token(
                mint("u1", "a@x.co", secret="wrong-secret")
            )
        with self.assertRaises(auth_module.AuthError):
            auth_module.verify_session_token(
                mint("u1", "a@x.co", ttl_s=-10)
            )
        identity = auth_module.verify_session_token(mint("u1", "a@x.co"))
        self.assertEqual(identity["external_id"], "test|u1")


class CommerceRoutesTests(unittest.TestCase):
    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        self._fix = fixture()
        url = self._fix.__enter__()
        self.addCleanup(self._fix.__exit__, None, None, None)
        env = {"DATABASE_URL": url, **test_env()}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        from fastapi.testclient import TestClient

        from apps.api.main import app

        self.client = TestClient(app)
        self._client_ctx = self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)

    def _headers(self, sub, email="", org_id=""):
        headers = {"Authorization": f"Bearer {mint(sub, email)}"}
        if org_id:
            headers["X-Org-Id"] = org_id
        return headers

    def _org(self, sub="u1", email="a@x.co", name="Acme"):
        response = self.client.post(
            "/api/orgs", json={"name": name}, headers=self._headers(sub, email)
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["org"]

    def test_org_crud_and_auth_doors(self) -> None:
        self.assertEqual(self.client.post("/api/orgs").status_code, 401)
        self.assertEqual(self.client.get("/api/orgs").status_code, 401)
        org = self._org()
        self.assertEqual(org["role"], "owner")

        listed = self.client.get(
            "/api/orgs", headers=self._headers("u1", "a@x.co")
        )
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(
            [item["id"] for item in listed.json()["orgs"]], [org["id"]]
        )
        got = self.client.get(
            f"/api/orgs/{org['id']}", headers=self._headers("u1", "a@x.co")
        )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["role"], "owner")

        # Another signed-in user sees nothing of this org.
        other = self.client.get(
            f"/api/orgs/{org['id']}", headers=self._headers("u2", "b@x.co")
        )
        self.assertEqual(other.status_code, 403)

        # Non-owner cannot delete; owner gets a grace window.
        nope = self.client.delete(
            f"/api/orgs/{org['id']}", headers=self._headers("u2", "b@x.co")
        )
        self.assertEqual(nope.status_code, 403)
        deleted = self.client.delete(
            f"/api/orgs/{org['id']}", headers=self._headers("u1", "a@x.co")
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertTrue(deleted.json()["deleted"])
        self.assertGreater(deleted.json()["grace_until"], 0)

    def test_invite_accept_remove_flow(self) -> None:
        org = self._org()
        owner = self._headers("u1", "a@x.co")
        invite = self.client.post(
            f"/api/orgs/{org['id']}/invites",
            json={"email": "b@x.co", "role": "member"},
            headers=owner,
        )
        self.assertEqual(invite.status_code, 200, invite.text)
        token = invite.json()["invite"]["token"]

        # Wrong person cannot take it.
        taken = self.client.post(
            f"/api/invites/{token}/accept",
            headers=self._headers("u3", "c@x.co"),
        )
        self.assertEqual(taken.status_code, 403)
        accepted = self.client.post(
            f"/api/invites/{token}/accept",
            headers=self._headers("u2", "b@x.co"),
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["org_id"], org["id"])
        again = self.client.post(
            f"/api/invites/{token}/accept",
            headers=self._headers("u2", "b@x.co"),
        )
        self.assertEqual(again.status_code, 409)

        members = self.client.get(
            f"/api/orgs/{org['id']}/members", headers=owner
        )
        self.assertEqual(len(members.json()["members"]), 2)

        # Removed member's session dies immediately.
        users = members.json()["members"]
        user_b = next(m for m in users if m["email"] == "b@x.co")["user_id"]
        removed = self.client.delete(
            f"/api/orgs/{org['id']}/members/{user_b}", headers=owner
        )
        self.assertEqual(removed.status_code, 200)
        dead = self.client.get(
            f"/api/orgs/{org['id']}/members",
            headers=self._headers("u2", "b@x.co"),
        )
        self.assertEqual(dead.status_code, 403)

        # Sole owner cannot be removed.
        users = self.client.get(
            f"/api/orgs/{org['id']}/members", headers=owner
        ).json()["members"]
        user_a = next(m for m in users if m["email"] == "a@x.co")["user_id"]
        stuck = self.client.delete(
            f"/api/orgs/{org['id']}/members/{user_a}", headers=owner
        )
        self.assertEqual(stuck.status_code, 409)

    def test_transfer_ownership(self) -> None:
        org = self._org()
        owner = self._headers("u1", "a@x.co")
        invite = self.client.post(
            f"/api/orgs/{org['id']}/invites",
            json={"email": "b@x.co", "role": "admin"},
            headers=owner,
        )
        token = invite.json()["invite"]["token"]
        self.client.post(
            f"/api/invites/{token}/accept",
            headers=self._headers("u2", "b@x.co"),
        )
        members = self.client.get(
            f"/api/orgs/{org['id']}/members", headers=owner
        ).json()["members"]
        user_b = next(m for m in members if m["email"] == "b@x.co")["user_id"]

        # Non-owner cannot transfer.
        nope = self.client.post(
            f"/api/orgs/{org['id']}/transfer",
            json={"user_id": "usr_x"},
            headers=self._headers("u2", "b@x.co"),
        )
        self.assertEqual(nope.status_code, 403)
        done = self.client.post(
            f"/api/orgs/{org['id']}/transfer",
            json={"user_id": user_b},
            headers=owner,
        )
        self.assertEqual(done.status_code, 200)
        members = self.client.get(
            f"/api/orgs/{org['id']}/members",
            headers=self._headers("u2", "b@x.co"),
        ).json()["members"]
        roles = {m["email"]: m["role"] for m in members}
        self.assertEqual(roles, {"a@x.co": "admin", "b@x.co": "owner"})

    def test_pair_claim_revoke_device(self) -> None:
        org = self._org()
        owner = self._headers("u1", "a@x.co", org["id"])
        paired = self.client.post(
            f"/api/orgs/{org['id']}/devices/pair",
            json={"label": "Pixel"},
            headers=owner,
        )
        self.assertEqual(paired.status_code, 200, paired.text)
        code = paired.json()["code"]
        claimed = self.client.post("/api/devices/claim", json={"code": code})
        self.assertEqual(claimed.status_code, 200, claimed.text)
        device_token = claimed.json()["device_token"]
        self.assertTrue(device_token.startswith("ta_dev_"))

        # The device token authenticates as the user in its org.
        me = self.client.get(
            f"/api/orgs/{org['id']}",
            headers={"Authorization": f"Bearer {device_token}"},
        )
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["role"], "owner")

        devices = self.client.get(
            f"/api/orgs/{org['id']}/devices", headers=owner
        )
        self.assertEqual(len(devices.json()["devices"]), 1)
        device_id = devices.json()["devices"][0]["id"]
        revoked = self.client.post(
            f"/api/orgs/{org['id']}/devices/{device_id}/revoke",
            headers=owner,
        )
        self.assertEqual(revoked.status_code, 200)
        dead = self.client.get(
            f"/api/orgs/{org['id']}",
            headers={"Authorization": f"Bearer {device_token}"},
        )
        self.assertEqual(dead.status_code, 401)

        # Unknown codes and double claims fail cleanly.
        self.assertEqual(
            self.client.post(
                "/api/devices/claim", json={"code": "000-000"}
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                "/api/devices/claim", json={"code": code}
            ).status_code,
            404,
        )

    def test_viewer_approve_forbidden_member_passes_auth(self) -> None:
        import apps.api.main as api_main

        org = self._org()
        owner = self._headers("u1", "a@x.co")
        invite = self.client.post(
            f"/api/orgs/{org['id']}/invites",
            json={"email": "v@x.co", "role": "viewer"},
            headers=owner,
        )
        self.client.post(
            f"/api/invites/{invite.json()['invite']['token']}/accept",
            headers=self._headers("u9", "v@x.co"),
        )
        run_id = "run-comviewer-1"
        api_main.software_runs[run_id] = {
            "org_id": org["id"],
            "target": "shop",
        }
        try:
            viewer = self.client.post(
                f"/api/actions/{run_id}/approve",
                json={"device": "web"},
                headers=self._headers("u9", "v@x.co", org["id"]),
            )
            self.assertEqual(viewer.status_code, 403)
            member = self.client.post(
                f"/api/actions/{run_id}/approve",
                json={"device": "web"},
                headers=self._headers("u1", "a@x.co", org["id"]),
            )
            # Auth passes (404: no pending veto window for this run).
            self.assertEqual(member.status_code, 404)
            demo = self.client.post(
                "/api/actions/run-demo-1/approve",
                json={"device": "web"},
            )
            # Unknown runs keep the existing 404 (no oracle either way).
            self.assertEqual(demo.status_code, 404)
        finally:
            api_main.software_runs.pop(run_id, None)

    def test_pause_needs_admin_hosted(self) -> None:
        org = self._org()
        owner = self._headers("u1", "a@x.co")
        invite = self.client.post(
            f"/api/orgs/{org['id']}/invites",
            json={"email": "m@x.co", "role": "member"},
            headers=owner,
        )
        self.client.post(
            f"/api/invites/{invite.json()['invite']['token']}/accept",
            headers=self._headers("u8", "m@x.co"),
        )
        self.assertEqual(
            self.client.post(
                "/api/actions/pause", json={"paused": True}
            ).status_code,
            401,
        )
        member = self.client.post(
            "/api/actions/pause",
            json={"paused": True},
            headers=self._headers("u8", "m@x.co", org["id"]),
        )
        self.assertEqual(member.status_code, 403)
        admin = self.client.post(
            "/api/actions/pause",
            json={"paused": True},
            headers=self._headers("u1", "a@x.co", org["id"]),
        )
        self.assertEqual(admin.status_code, 200)
        self.assertTrue(admin.json()["paused"])
        self.client.post(
            "/api/actions/pause",
            json={"paused": False},
            headers=self._headers("u1", "a@x.co", org["id"]),
        )

    def test_usage_and_admin_shapes(self) -> None:
        org = self._org()
        owner = self._headers("u1", "a@x.co")
        usage = self.client.get(
            f"/api/orgs/{org['id']}/usage", headers=owner
        )
        self.assertEqual(usage.status_code, 200, usage.text)
        for key in (
            "fix_runs_used", "fix_runs_limit", "cost_used_usd",
            "cost_ceiling_usd", "systems_used", "systems_limit",
            "devices_used", "devices_limit", "by_language",
        ):
            self.assertIn(key, usage.json())

        self.assertEqual(
            self.client.get("/api/admin/costs", headers=owner).status_code,
            403,
        )
        with mock.patch.dict(
            os.environ, {"COMMERCE_ADMIN_EMAILS": "a@x.co"}
        ):
            admin = self.client.get("/api/admin/costs", headers=owner)
        self.assertEqual(admin.status_code, 200, admin.text)
        for key in (
            "by_org", "by_language", "top_spenders", "provider_credit"
        ):
            self.assertIn(key, admin.json())


class SelfHostedTests(unittest.TestCase):
    def test_commerce_routes_need_sign_in_without_database(self) -> None:
        from fastapi.testclient import TestClient

        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            from apps.api.main import app

            with TestClient(app) as client:
                response = client.post("/api/orgs", json={"name": "x"})
        self.assertEqual(response.status_code, 401)


class ClerkApiUrlTests(unittest.TestCase):
    def _called_url(self, api_url: str) -> str:
        from core.commerce import auth as auth_module

        seen: dict = {}

        class _Response:
            def raise_for_status(self) -> None:
                return None

            def json(self) -> dict:
                return {
                    "primary_email_address_id": "e1",
                    "email_addresses": [
                        {"id": "e1", "email_address": "a@x.co"}
                    ],
                }

        def _fake_get(url: str, **kwargs):
            seen["url"] = url
            return _Response()

        with mock.patch.dict(
            os.environ,
            {"CLERK_SECRET_KEY": "sk_test_x", "CLERK_API_URL": api_url},
        ), mock.patch("httpx.get", side_effect=_fake_get):
            email = auth_module._clerk_email("user_1")
        self.assertEqual(email, "a@x.co")
        return seen["url"]

    def test_bare_host_gets_v1(self) -> None:
        self.assertEqual(
            self._called_url("https://api.clerk.com"),
            "https://api.clerk.com/v1/users/user_1",
        )

    def test_explicit_v1_untouched(self) -> None:
        self.assertEqual(
            self._called_url("https://api.clerk.com/v1/"),
            "https://api.clerk.com/v1/users/user_1",
        )


if __name__ == "__main__":
    unittest.main()
