"""Org isolation: C-J3 acceptance + C-J4 two-org endpoint matrix.

All against the ta_test role (real RLS, never a superuser bypass):
direct-SQL cross-org reads/writes fail, a pause in org A leaves org B
running, cross-org websocket joins are refused while org events fan
out to their own channel only, and org B cannot read/list/test/delete/
approve org A's anything by direct ID or guessing.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from tests.commerce_auth import mint, test_env
from tests.commerce_db import db_available, fixture


def _two_orgs(url: str) -> dict:
    from core.commerce import repo as repo_module

    store = repo_module.PostgresBackend(url)
    users = {}
    orgs = {}
    for key, external in (("a", "test|iso-a"), ("b", "test|iso-b")):
        user = store.create_user(external, f"{key}@x.co", key.upper())
        users[key] = user
        orgs[key] = store.create_org(f"Org {key.upper()}", user["id"])
    return {"store": store, "users": users, "orgs": orgs}


class RlsBypassTests(unittest.TestCase):
    def test_direct_sql_cannot_cross_orgs(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        from core.commerce import db as db_module

        with fixture() as url:
            ctx = _two_orgs(url)
            org_a = ctx["orgs"]["a"]["id"]
            org_b = ctx["orgs"]["b"]["id"]
            user_a = ctx["users"]["a"]["id"]
            scoped_a = ctx["store"].scoped(org_a, user_a)
            scoped_a.save_system(
                org_a, {"system_id": "sys-a", "status": "active"}
            )
            scoped_a.create_connection(
                org_a, "sys-a", "device", {}, None
            )
            scoped_a.audit(org_a, {"actor": "t", "action": "x"})
            scoped_a.stamp_rate(org_a, "sys-a")
            scoped_a.set_pause(org_a, True)
            _row, _token = scoped_a.create_device_token(
                org_a, user_a, "phone"
            )

            conn = db_module.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT set_config('app.org_id', %s, true)",
                        (org_b,),
                    )
                    # B sees none of A's rows, in any org table.
                    for table, column in (
                        ("systems", "id"),
                        ("connections", "id"),
                        ("audit", "action"),
                        ("rate_stamps", "system_id"),
                        ("pause_state", "paused"),
                        ("device_tokens", "id"),
                    ):
                        cur.execute(
                            f"SELECT {column} FROM {table} "
                            "WHERE org_id = %s",
                            (org_a,),
                        )
                        self.assertEqual(
                            cur.fetchall(), [], f"{table} leaked"
                        )
                    # B cannot insert/update/delete as A either.
                    import psycopg

                    with self.assertRaises(
                        psycopg.errors.InsufficientPrivilege
                    ):
                        cur.execute(
                            "INSERT INTO systems (id, org_id) "
                            "VALUES ('sys-evil', %s)",
                            (org_a,),
                        )
                    conn.rollback()
                    cur.execute(
                        "SELECT set_config('app.org_id', %s, true)",
                        (org_b,),
                    )
                    with self.assertRaises(
                        psycopg.errors.InsufficientPrivilege
                    ):
                        cur.execute(
                            "INSERT INTO connections "
                            "(id, org_id, system_id) "
                            "VALUES ('conn-evil', %s, 'sys-a')",
                            (org_a,),
                        )
                    conn.rollback()
                    cur.execute(
                        "SELECT set_config('app.org_id', %s, true)",
                        (org_b,),
                    )
                    with self.assertRaises(
                        psycopg.errors.InsufficientPrivilege
                    ):
                        cur.execute(
                            "INSERT INTO audit (org_id) VALUES (%s)",
                            (org_a,),
                        )
                    conn.rollback()
                    cur.execute(
                        "SELECT set_config('app.org_id', %s, true)",
                        (org_b,),
                    )
                    cur.execute(
                        "UPDATE systems SET status = 'evil' "
                        "WHERE id = 'sys-a'"
                    )
                    self.assertEqual(cur.rowcount, 0)
                    cur.execute(
                        "DELETE FROM audit WHERE org_id = %s", (org_a,)
                    )
                    self.assertEqual(cur.rowcount, 0)
            finally:
                conn.close()

            # And A's own rows survived untouched.
            self.assertEqual(
                scoped_a.get_system(org_a, "sys-a")["status"], "active"
            )
            self.assertEqual(len(scoped_a.list_audit(org_a)), 1)


class PauseIsolationTests(unittest.TestCase):
    def test_pause_in_a_leaves_b_running(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        from core.actions import mitigate as mitigate_module

        with fixture() as url:
            ctx = _two_orgs(url)
            org_a = ctx["orgs"]["a"]["id"]
            org_b = ctx["orgs"]["b"]["id"]
            with mock.patch.dict(
                os.environ, {"DATABASE_URL": url}
            ):
                mitigate_module.set_paused(True, org_a)
                self.assertTrue(mitigate_module.is_paused(org_a))
                self.assertFalse(mitigate_module.is_paused(org_b))
                mitigate_module.set_paused(False, org_a)
                self.assertFalse(mitigate_module.is_paused(org_a))
                self.assertFalse(mitigate_module.is_paused(org_b))


class WsIsolationTests(unittest.TestCase):
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
        ctx = _two_orgs(url)
        self.org_a = ctx["orgs"]["a"]["id"]
        self.org_b = ctx["orgs"]["b"]["id"]
        user_a = ctx["users"]["a"]["id"]
        user_b = ctx["users"]["b"]["id"]
        _row, self.token_a = ctx["store"].scoped(
            self.org_a, user_a
        ).create_device_token(self.org_a, user_a, "a-phone")
        _row, self.token_b = ctx["store"].scoped(
            self.org_b, user_b
        ).create_device_token(self.org_b, user_b, "b-phone")

    def test_device_token_joins_own_org_only(self) -> None:
        import apps.api.main as api_main

        with self.client.websocket_connect(
            f"/api/ws?token={self.token_b}"
        ):
            channels = api_main.hub._channels
            self.assertTrue(
                channels.get(self.org_b),
                "B's socket never joined B's channel",
            )
            self.assertFalse(
                channels.get(self.org_a),
                "B's socket leaked into A's channel",
            )

    def test_cross_org_join_is_refused(self) -> None:
        from starlette.testclient import WebSocketDisconnect

        with self.assertRaises(WebSocketDisconnect) as raised:
            with self.client.websocket_connect(
                f"/api/ws?token={self.token_a}&org={self.org_b}"
            ):
                pass
        self.assertEqual(raised.exception.code, 4403)

    def test_emit_for_reaches_only_the_org_channel(self) -> None:
        import apps.api.main as api_main
        from core.schemas.events import SimEvent

        class _Stub:
            def __init__(self) -> None:
                self.sent: list = []

            async def accept(self) -> None:
                return None

            async def send_json(self, payload: dict) -> None:
                self.sent.append(payload)

        async def _scenario() -> tuple:
            fresh = api_main.EventHub()
            stub_a, stub_b, stub_demo = _Stub(), _Stub(), _Stub()
            await fresh.connect(stub_a, self.org_a)
            await fresh.connect(stub_b, self.org_b)
            await fresh.connect(stub_demo, "demo")
            with mock.patch.object(api_main, "hub", fresh):
                await api_main.emit_for(
                    self.org_a, SimEvent(kind="action_tick", payload={"n": 1})
                )
                await api_main.emit_for(
                    self.org_b, SimEvent(kind="action_tick", payload={"n": 2})
                )
            return stub_a.sent, stub_b.sent, stub_demo.sent

        sent_a, sent_b, sent_demo = asyncio.run(_scenario())
        self.assertEqual([p["payload"] for p in sent_a], [{"n": 1}])
        self.assertEqual([p["payload"] for p in sent_b], [{"n": 2}])
        self.assertEqual(sent_demo, [])


class TwoOrgMatrixTests(unittest.TestCase):
    """C-J4: org B cannot touch org A's anything (HTTP + ingest + pause).

    Reads mask foreign IDs as 404 (no oracle); org-membership routes
    answer 403 to non-members. Seeds are per-test (fresh fixture PG +
    scrubbed in-memory stores); no model calls (readings stay below the
    watcher streak, repo-fix needs an armed profile).
    """

    def setUp(self) -> None:
        if not db_available():
            self.skipTest("no postgres (TEST_DATABASE_URL)")
        self._fix = fixture()
        url = self._fix.__enter__()
        self.addCleanup(self._fix.__exit__, None, None, None)
        patcher = mock.patch.dict(
            os.environ, {"DATABASE_URL": url, **test_env()}
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        from fastapi.testclient import TestClient

        from apps.api.main import app

        self.client = TestClient(app)
        self._client_ctx = self.client.__enter__()
        self.addCleanup(self.client.__exit__, None, None, None)
        # Org A (victim) + org B (attacker), both owner-led.
        self.org_a = self._org("u-matrix-a", "a@x.co", "Org A")
        self.org_b = self._org("u-matrix-b", "b@x.co", "Org B")
        self.sys_a = self._system("u-matrix-a", "a@x.co", self.org_a)
        self.sys_b = self._system("u-matrix-b", "b@x.co", self.org_b)
        self.conn_a, self.key_a = self._conn(
            "u-matrix-a", self.org_a, self.sys_a, "device"
        )
        self.conn_b, self.key_b = self._conn(
            "u-matrix-b", self.org_b, self.sys_b, "device"
        )
        self.logs_a, self.logs_key_a = self._conn(
            "u-matrix-a", self.org_a, self.sys_a, "logs"
        )
        self._seed_run()
        self.addCleanup(self._scrub_memory)

    # -- helpers ------------------------------------------------------

    def _headers(self, sub: str, email: str, org_id: str = "") -> dict:
        headers = {"Authorization": f"Bearer {mint(sub, email)}"}
        if org_id:
            headers["X-Org-Id"] = org_id
        return headers

    def _org(self, sub: str, email: str, name: str) -> str:
        response = self.client.post(
            "/api/orgs", json={"name": name},
            headers=self._headers(sub, email),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["org"]["id"]

    def _system(self, sub: str, email: str, org_id: str) -> str:
        response = self.client.post(
            "/api/systems",
            json={"name": f"Sys {email}", "kind": "appliance",
                  "appliance_type": "fridge"},
            headers=self._headers(sub, email, org_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["system_id"]

    def _conn(self, sub: str, org_id: str, system_id: str,
             kind: str) -> tuple:
        email = f"{sub.rsplit('-', 1)[-1]}@x.co"
        response = self.client.post(
            "/api/connections",
            json={"system_id": system_id, "kind": kind, "config": {}},
            headers=self._headers(sub, email, org_id),
        )
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        return body["connection"]["id"], body["key"]

    def _seed_run(self) -> None:
        import time as time_module

        import apps.api.main as api_main
        from core.actions.auto_action import PendingAction
        from core.schemas.remediation import ExecutionResult

        self.run_a = "run-matrix-a1"
        api_main.software_runs[self.run_a] = {
            "result": ExecutionResult(
                status="PASS", stdout="", stderr="", attempts=1,
                model_used="mocked", run_id=self.run_a,
            ),
            "gate": {"system_id": self.sys_a, "decision": "act"},
            "org_id": self.org_a,
        }
        now = time_module.time()
        api_main.pending_actions[self.run_a] = PendingAction(
            run_id=self.run_a, domain="software", action="deploy x",
            opened_at=now, deadline=now + 60.0,
        )
        api_main._record_gate_decision(
            self.sys_a,
            {"decision": "act", "rule": "matrix", "signature": "seed"},
            self.org_a,
        )

    def _scrub_memory(self) -> None:
        import apps.api.main as api_main
        from core.devices import queue as device_queue

        api_main.software_runs.pop(self.run_a, None)
        api_main.pending_actions.pop(self.run_a, None)
        api_main.gate_decisions = type(api_main.gate_decisions)(
            [item for item in api_main.gate_decisions
             if item.get("org_id") != self.org_a],
            maxlen=api_main.gate_decisions.maxlen,
        )
        device_queue.reset()

    # -- org / member / device / usage routes: 403 for outsiders ------

    def test_org_routes_reject_foreign_org(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        org_a = self.org_a
        self.assertEqual(
            self.client.get(
                f"/api/orgs/{org_a}", headers=headers_b
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/orgs/{org_a}", headers=headers_b
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/orgs/{org_a}/members", headers=headers_b
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{org_a}/invites",
                json={"email": "mallory@evil.co"},
                headers=headers_b,
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/orgs/{org_a}/members/user_nope", headers=headers_b
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{org_a}/transfer",
                json={"user_id": "user_nope"}, headers=headers_b,
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{org_a}/devices/pair",
                json={"label": "x"}, headers=headers_b,
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.get(
                f"/api/orgs/{org_a}/devices", headers=headers_b
            ).status_code, 403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{org_a}/devices/dev_nope/revoke",
                headers=headers_b,
            ).status_code, 403,
        )
        # Same 403 for a REAL token id (no existence oracle).
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        code = self.client.post(
            f"/api/orgs/{org_a}/devices/pair", json={"label": "a-phone"},
            headers=headers_a,
        ).json()["code"]
        self.client.post(
            "/api/devices/claim", json={"code": code},
            headers=self._headers("u-matrix-a", "a@x.co"),
        )
        token_id = self.client.get(
            f"/api/orgs/{org_a}/devices", headers=headers_a
        ).json()["devices"][0]["id"]
        self.assertEqual(
            self.client.post(
                f"/api/orgs/{org_a}/devices/{token_id}/revoke",
                headers=headers_b,
            ).status_code, 403,
        )
        kept_token = self.client.get(
            f"/api/orgs/{org_a}/devices", headers=headers_a
        ).json()["devices"][0]
        self.assertFalse(kept_token["revoked"])
        self.assertEqual(
            self.client.get(
                f"/api/orgs/{org_a}/usage", headers=headers_b
            ).status_code, 403,
        )
        # And A's org survives the attempt (no delete, no transfer).
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        got = self.client.get(
            f"/api/orgs/{org_a}", headers=headers_a
        )
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got.json()["role"], "owner")

    # -- systems: foreign ids look unknown -----------------------------

    def test_system_routes_hide_foreign_systems(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        listed = self.client.get("/api/systems", headers=headers_b)
        self.assertEqual(listed.status_code, 200)
        ids = [s["system_id"] for s in listed.json()["systems"]]
        self.assertIn(self.sys_b, ids)
        self.assertNotIn(self.sys_a, ids)

        sys_a = self.sys_a
        self.assertEqual(
            self.client.get(
                f"/api/systems/{sys_a}/profile", headers=headers_b
            ).status_code, 404,
        )
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        profile = self.client.get(
            f"/api/systems/{sys_a}/profile", headers=headers_a
        ).json()["profile"]
        self.assertEqual(
            self.client.put(
                f"/api/systems/{sys_a}/profile", json=profile,
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/profile/confirm",
                json={"confirmed_by": "b"}, headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/arm", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/disarm", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/systems/{sys_a}", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/systems/{sys_a}/mode", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/mode", json={"mode": ""},
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/start", json={},
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/finish",
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/systems/{sys_a}/baseline", headers=headers_b
            ).status_code, 404,
        )
        # Idle learner: 400 for everyone (owner included — no oracle).
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/observe", json={},
                headers=headers_b,
            ).status_code, 400,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/observe", json={},
                headers=headers_a,
            ).status_code, 400,
        )
        # Active A learner: B's observations are refused, A's flow works.
        started = self.client.post(
            f"/api/systems/{sys_a}/baseline/start", json={},
            headers=headers_a,
        )
        self.assertEqual(started.status_code, 200, started.text)
        import apps.api.main as api_main

        before = api_main.baseline_learners[sys_a].observations
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/observe",
                json={"logs": ["tainted"]},
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            api_main.baseline_learners[sys_a].observations, before
        )
        own_feed = self.client.post(
            f"/api/systems/{sys_a}/baseline/observe",
            json={"logs": ["INFO ok"]},
            headers=headers_a,
        )
        self.assertEqual(own_feed.status_code, 200)
        finished = self.client.post(
            f"/api/systems/{sys_a}/baseline/finish",
            headers=headers_b,
        )
        self.assertEqual(finished.status_code, 404)
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/baseline/finish",
                headers=headers_a,
            ).status_code, 200,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/feedback",
                json={"fingerprint": "f", "signature": "s"},
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/systems/{sys_a}/feedback", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/feedback/fid_nope/confirm",
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/systems/{sys_a}/feedback/fid_nope",
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/documents",
                files=[("files", ("doc.txt", b"spec", "text/plain"))],
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/systems/{sys_a}/profile/sample",
                json={"sample": "coldchain"}, headers=headers_b,
            ).status_code, 404,
        )
        # A's system survives (still there, still a draft).
        kept = self.client.get(
            f"/api/systems/{sys_a}/profile", headers=headers_a
        )
        self.assertEqual(kept.status_code, 200)
        self.assertEqual(kept.json()["profile"]["status"], "draft")

    # -- connections ----------------------------------------------------

    def test_connection_routes_hide_foreign_connections(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        listed = self.client.get("/api/connections", headers=headers_b)
        self.assertEqual(listed.status_code, 200)
        ids = [c["id"] for c in listed.json()["connections"]]
        self.assertIn(self.conn_b, ids)
        self.assertNotIn(self.conn_a, ids)
        filtered = self.client.get(
            "/api/connections", params={"system_id": self.sys_a},
            headers=headers_b,
        )
        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.json()["connections"], [])

        self.assertEqual(
            self.client.post(
                "/api/connections",
                json={"system_id": self.sys_a, "kind": "device",
                      "config": {}},
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/connections/{self.conn_a}/test",
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/connections/{self.conn_a}", headers=headers_b
            ).status_code, 404,
        )
        # A's connection survives (still listed for A).
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        kept = self.client.get("/api/connections", headers=headers_a)
        self.assertIn(
            self.conn_a, [c["id"] for c in kept.json()["connections"]]
        )

    # -- runs / actions / options / decisions ----------------------------

    def test_runs_actions_options_masked(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        runs = self.client.get("/api/runs", headers=headers_b)
        self.assertEqual(runs.status_code, 200)
        self.assertNotIn(
            self.run_a, [r["run_id"] for r in runs.json()["runs"]]
        )
        self.assertEqual(
            self.client.get(
                f"/api/runs/{self.run_a}", headers=headers_b
            ).status_code, 404,
        )
        actions = self.client.get("/api/actions", headers=headers_b)
        self.assertEqual(actions.status_code, 200)
        self.assertNotIn(
            self.run_a,
            [a["run_id"] for a in actions.json()["open"]],
        )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{self.run_a}/approve",
                json={"device": "b-phone"}, headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{self.run_a}/disapprove",
                json={"device": "b-phone"}, headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/incidents/{self.run_a}/options",
                headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/incidents/{self.run_a}/options/opt_nope/execute",
                headers=headers_b,
            ).status_code, 404,
        )
        decisions = self.client.get(
            "/api/gate/decisions", headers=headers_b
        )
        self.assertEqual(decisions.status_code, 200)
        self.assertNotIn(
            self.sys_a,
            [d.get("system_id") for d in decisions.json()["decisions"]],
        )
        # A's own reads still work (positive control).
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        self.assertEqual(
            self.client.get(
                f"/api/runs/{self.run_a}", headers=headers_a
            ).status_code, 200,
        )

    def test_id_guessing_on_unknown_ids(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        nope = "nope-guess-12345"
        self.assertEqual(
            self.client.get(
                f"/api/runs/{nope}", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{nope}/approve",
                json={"device": "b-phone"}, headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/actions/{nope}/disapprove",
                json={"device": "b-phone"}, headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/incidents/{nope}/options", headers=headers_b,
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.get(
                f"/api/systems/{nope}/profile", headers=headers_b
            ).status_code, 404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/connections/{nope}", headers=headers_b
            ).status_code, 404,
        )

    # -- ingest ----------------------------------------------------------

    def test_ingest_with_a_key_never_lands_in_b(self) -> None:
        logs = self.client.post(
            "/api/ingest/logs",
            json={
                "service": "web",
                "lines": [
                    {"message": "INFO booted"},
                    {"message": (
                        "Traceback (most recent call last):\n"
                        '  File "/srv/app.py", line 1, in main\n'
                        "    1/0\n"
                        "ZeroDivisionError: division by zero"
                    )},
                ],
            },
            headers={"Authorization": f"Bearer {self.logs_key_a}"},
        )
        self.assertEqual(logs.status_code, 200, logs.text)
        self.assertEqual(logs.json()["accepted"], 2)
        sentry = self.client.post(
            f"/api/ingest/sentry/{self.logs_key_a}",
            json={"message": "boom"},
            headers={"Authorization": f"Bearer {self.logs_key_a}"},
        )
        # A logs key is not a sentry key: rejected, nothing lands.
        self.assertEqual(sentry.status_code, 401)

        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        runs = self.client.get("/api/runs", headers=headers_b)
        self.assertNotIn(
            self.sys_a,
            [
                (r.get("gate") or {}).get("system_id")
                for r in runs.json()["runs"]
            ],
        )
        decisions = self.client.get(
            "/api/gate/decisions", headers=headers_b
        )
        self.assertNotIn(
            self.sys_a,
            [d.get("system_id") for d in decisions.json()["decisions"]],
        )

    def test_device_readings_land_in_owner_org_only(self) -> None:
        import apps.api.main as api_main

        device_a = "dev-matrix-a1"
        readings = self.client.post(
            f"/api/devices/{device_a}/readings",
            json={"temperature_c": 7.0, "current_a": 1.2},
            headers={"Authorization": f"Bearer {self.key_a}"},
        )
        self.assertEqual(readings.status_code, 200, readings.text)
        self.assertTrue(readings.json()["accepted"])
        # The breach gated a decision tagged with A's org.
        tagged = [
            item for item in api_main.gate_decisions
            if item.get("system_id") == self.sys_a
        ]
        self.assertTrue(tagged, "no gate decision recorded")
        self.assertEqual(tagged[-1].get("org_id"), self.org_a)

        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        decisions = self.client.get(
            "/api/gate/decisions", headers=headers_b
        )
        self.assertNotIn(
            self.sys_a,
            [d.get("system_id") for d in decisions.json()["decisions"]],
        )
        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        own = self.client.get("/api/gate/decisions", headers=headers_a)
        self.assertIn(
            self.sys_a,
            [d.get("system_id") for d in own.json()["decisions"]],
        )

    def test_device_queue_cross_use_blocked(self) -> None:
        from core.devices import queue as device_queue

        device_a = "dev-matrix-a2"
        device_queue.note_device_seen(self.sys_a, device_a)
        queued = device_queue.enqueue(
            device_a, self.run_a, "opt_defrost", "defrost", {}
        )
        # B's key on A's device path: the link check refuses.
        refused = self.client.get(
            f"/api/devices/{device_a}/commands",
            headers={"Authorization": f"Bearer {self.key_b}"},
        )
        self.assertEqual(refused.status_code, 404)
        refused_ack = self.client.post(
            f"/api/devices/{device_a}/commands/{queued['id']}/ack",
            json={"ok": True},
            headers={"Authorization": f"Bearer {self.key_b}"},
        )
        self.assertEqual(refused_ack.status_code, 404)
        # A's own key still drains its queue (positive control).
        own = self.client.get(
            f"/api/devices/{device_a}/commands",
            headers={"Authorization": f"Bearer {self.key_a}"},
        )
        self.assertEqual(own.status_code, 200)
        self.assertEqual(
            [c["id"] for c in own.json()["commands"]], [queued["id"]]
        )

    # -- pause ------------------------------------------------------------

    def test_pause_in_a_does_not_affect_b(self) -> None:
        from core.devices import queue as device_queue

        headers_a = self._headers("u-matrix-a", "a@x.co", self.org_a)
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        device_a = "dev-matrix-a3"
        device_b = "dev-matrix-b3"
        device_queue.note_device_seen(self.sys_a, device_a)
        device_queue.note_device_seen(self.sys_b, device_b)
        cmd_a = device_queue.enqueue(
            device_a, self.run_a, "opt_defrost", "defrost", {}
        )
        cmd_b = device_queue.enqueue(
            device_b, "run-matrix-b9", "opt_defrost", "defrost", {}
        )
        paused = self.client.post(
            "/api/actions/pause", json={"paused": True},
            headers=headers_a,
        )
        self.assertEqual(paused.status_code, 200)
        self.assertTrue(paused.json()["paused"])

        state_b = self.client.get("/api/actions/pause", headers=headers_b)
        self.assertEqual(state_b.status_code, 200)
        self.assertFalse(state_b.json()["paused"])
        withheld = self.client.get(
            f"/api/devices/{device_a}/commands",
            headers={"Authorization": f"Bearer {self.key_a}"},
        )
        self.assertEqual(withheld.json(), {"commands": []})
        served = self.client.get(
            f"/api/devices/{device_b}/commands",
            headers={"Authorization": f"Bearer {self.key_b}"},
        )
        self.assertEqual(
            [c["id"] for c in served.json()["commands"]], [cmd_b["id"]]
        )
        self.assertTrue(cmd_a["id"])

        unpaused = self.client.post(
            "/api/actions/pause", json={"paused": False},
            headers=headers_a,
        )
        self.assertFalse(unpaused.json()["paused"])

    # -- admin --------------------------------------------------------------

    def test_admin_costs_rejects_non_admin(self) -> None:
        headers_b = self._headers("u-matrix-b", "b@x.co", self.org_b)
        self.assertEqual(
            self.client.get(
                "/api/admin/costs", headers=headers_b
            ).status_code, 403,
        )


if __name__ == "__main__":
    unittest.main()
