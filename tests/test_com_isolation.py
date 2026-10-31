"""Org isolation (C-J3 acceptance; C-J4 adds the endpoint matrix).

C-J3 rows, all against the ta_test role (real RLS, never a superuser
bypass): direct-SQL cross-org reads/writes fail, a pause in org A
leaves org B running, and a cross-org websocket join is refused while
org events fan out to their own channel only.
"""

from __future__ import annotations

import asyncio
import os
import unittest
from unittest import mock

from tests.commerce_auth import test_env
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


if __name__ == "__main__":
    unittest.main()
