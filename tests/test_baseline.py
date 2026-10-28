"""P7: baseline learning, learner math, and gate baseline checks."""

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app, baseline_learners, baseline_sessions
from core.schemas.profile import (
    Baseline,
    FailureDefinition,
    HardLimit,
    Provenance,
    SystemProfile,
)
from core.setup.baseline import BaselineLearner, band, percentile
from core.setup.gate import (
    Candidate,
    baseline_band,
    evaluate,
    template_of,
)
from core.setup.modes import ModeState


def _prov():
    return Provenance(source_doc="spec.pdf", page_or_region="p.1", quote="q")


def _profile(**over):
    data = {
        "system_id": "sys-1",
        "name": "walk-in",
        "kind": "appliance",
        "appliance_type": "fridge",
        "status": "confirmed",
        "hard_limits": [
            HardLimit(
                metric="temp_c", op=">", threshold=8.0,
                provenance=_prov(),
            ).model_dump()
        ],
        "failure_definitions": [
            FailureDefinition(
                name="hot cabinet",
                metric="temp_c", op=">", threshold=5.5,
                duration_s=600.0,
                provenance=_prov(),
            ).model_dump()
        ],
    }
    data.update(over)
    return SystemProfile(**data)


class PercentileTests(unittest.TestCase):
    def test_band_edges(self):
        self.assertEqual(band([]), [0.0, 0.0])
        self.assertEqual(band([4.0]), [4.0, 4.0])
        vals = [float(i) for i in range(100)]
        lo, hi = band(vals)
        self.assertAlmostEqual(lo, 4.95, places=1)
        self.assertAlmostEqual(hi, 94.05, places=1)

    def test_percentile_median(self):
        self.assertEqual(percentile([1.0, 2.0, 3.0], 50.0), 2.0)


class LearnerTests(unittest.TestCase):
    def test_log_templates_normalize_and_rate(self):
        learner = BaselineLearner("sys-1", started_at=1000.0)
        learner.observe_log("ERROR order=a1 items=axle retry 3")
        learner.observe_log("ERROR order=b2 items=axle retry 9")
        learner.observe_log("INFO cache warm")
        done = learner.finish(now=1060.0)
        self.assertEqual(done.status, "ready")
        self.assertEqual(done.duration_s, 60.0)
        by_template = {item["template"]: item for item in done.log_templates}
        retry = template_of("ERROR order=a1 items=axle retry 3")
        self.assertEqual(by_template[retry]["count"], 2)
        self.assertEqual(by_template[retry]["rate_per_min"], 2.0)

    def test_sensor_bands_per_mode_and_stats(self):
        learner = BaselineLearner("sys-1", started_at=1000.0)
        for i in range(10):
            learner.observe_sensor("temp_c", 4.0, "", now=1000.0 + i)
        for i in range(10):
            learner.observe_sensor(
                "temp_c", 6.5, "defrost", now=1100.0 + i
            )
        done = learner.finish(now=1200.0)
        entry = done.sensor_bands["temp_c"]
        self.assertEqual(entry["all"], band([4.0] * 10 + [6.5] * 10))
        self.assertEqual(entry["defrost"], [6.5, 6.5])
        self.assertEqual(entry["stats"]["mean"], 5.25)
        self.assertGreaterEqual(entry["stats"]["roc_per_s"], 0.0)

    def test_shop_bands(self):
        learner = BaselineLearner("sys-1", started_at=1000.0)
        learner.observe_shop(0.005, 120.0, 30.0)
        learner.observe_shop(0.010, 140.0, 34.0)
        done = learner.finish(now=1060.0)
        self.assertEqual(
            done.metric_bands["error_rate"], band([0.005, 0.010])
        )
        self.assertEqual(done.metric_bands["p95_ms"], band([120.0, 140.0]))

    def test_patterns_learned_counts_sources(self):
        learner = BaselineLearner("sys-1", started_at=1000.0)
        self.assertEqual(learner.patterns_learned(), 0)
        learner.observe_log("INFO up")
        learner.observe_sensor("temp_c", 4.0)
        learner.observe_shop(0.0, 100.0, 20.0)
        self.assertEqual(learner.patterns_learned(), 3)


class BaselineBandTests(unittest.TestCase):
    def test_legacy_list(self):
        self.assertEqual(baseline_band([1.0, 6.0], ""), [1.0, 6.0])

    def test_per_mode_prefers_mode_then_all(self):
        entry = {"all": [1.0, 6.0], "defrost": [1.0, 7.0]}
        self.assertEqual(baseline_band(entry, "defrost"), [1.0, 7.0])
        self.assertEqual(baseline_band(entry, ""), [1.0, 6.0])
        self.assertEqual(baseline_band(entry, "other"), [1.0, 6.0])

    def test_stats_and_junk_resolve_none(self):
        self.assertIsNone(baseline_band({"stats": {}}, ""))
        self.assertIsNone(baseline_band([1.0], ""))
        self.assertIsNone(baseline_band("x", ""))
        self.assertIsNone(baseline_band(None, ""))


class BaselineGateTests(unittest.TestCase):
    def _ready(self, **over):
        data = {
            "status": "ready",
            "log_templates": [],
            "sensor_bands": {},
            "metric_bands": {},
        }
        data.update(over)
        return _profile(status="armed", baseline=Baseline(**data).model_dump())

    def test_rate_spike_does_not_suppress(self):
        sig = "ERROR order=a1 items=axle retry 3"
        profile = self._ready(
            log_templates=[
                {"template": template_of(sig), "rate_per_min": 0.2}
            ]
        )
        candidate = Candidate(
            system_id="sys-1", source="log", rule="retry_cluster",
            fingerprint="f1", signature=sig,
            metrics={"template_rate_per_min": 12.0},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertNotEqual(decision.decision, "suppress")

    def test_normal_rate_suppresses(self):
        sig = "ERROR order=a1 items=axle retry 3"
        profile = self._ready(
            log_templates=[
                {"template": template_of(sig), "rate_per_min": 0.2}
            ]
        )
        candidate = Candidate(
            system_id="sys-1", source="log", rule="retry_cluster",
            fingerprint="f1", signature=sig,
            metrics={"template_rate_per_min": 0.2},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "suppress")

    def test_sensor_band_suppresses(self):
        profile = self._ready(
            sensor_bands={"temp_c": {"all": [3.5, 4.5]}}
        )
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_c_high",
            fingerprint="f2", metrics={"temp_c": 4.0},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "suppress")
        self.assertIn("sensor band", decision.checks[-1].detail)

    def test_mode_band_prefers_mode(self):
        profile = self._ready(
            sensor_bands={
                "temp_c": {"all": [3.5, 4.5], "defrost": [3.5, 7.0]}
            }
        )
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_c_high",
            fingerprint="f3", metrics={"temp_c": 6.5}, mode="defrost",
        )
        decision = evaluate(
            candidate, profile, ModeState(mode="defrost")
        )
        self.assertEqual(decision.decision, "suppress")

    def test_metric_band_suppresses(self):
        profile = _profile(
            status="armed",
            kind="software",
            appliance_type=None,
            baseline=Baseline(
                status="ready",
                metric_bands={"error_rate": [0.0, 0.02]},
            ).model_dump(),
        )
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="error_spike",
            fingerprint="f4", metrics={"error_rate": 0.005},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "suppress")
        self.assertIn("metric band", decision.checks[-1].detail)


class BaselineApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        from apps.api.main import appliance_runs

        baseline_learners.clear()
        baseline_sessions.clear()
        appliance_runs.pop("gate-test-app", None)

    def test_start_observe_finish_round_trip(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    started = client.post(
                        "/api/systems/sys-1/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    self.assertEqual(started.status_code, 200)
                    body = started.json()
                    self.assertEqual(body["status"], "learning")
                    self.assertGreater(body["ends_at"], body["started_at"])
                    observed = client.post(
                        "/api/systems/sys-1/baseline/observe",
                        json={
                            "logs": ["INFO cache warm", "INFO cache warm"],
                            "sensors": [
                                {"metric": "temp_c", "value": 4.0},
                                {
                                    "metric": "temp_c",
                                    "value": 6.5,
                                    "mode": "defrost",
                                },
                            ],
                            "shop": {
                                "error_rate": 0.005,
                                "p95_ms": 120.0,
                                "orders_per_min": 30.0,
                            },
                        },
                    )
                    self.assertEqual(observed.status_code, 200)
                    self.assertEqual(
                        observed.json()["observations"], 5
                    )
                    state = client.get("/api/systems/sys-1/baseline")
                    self.assertEqual(state.json()["status"], "learning")
                    self.assertIsNotNone(state.json()["session"])
                    self.assertIs(
                        state.json()["session"]["blocked"], False
                    )
                    done = client.post(
                        "/api/systems/sys-1/baseline/finish"
                    )
        self.assertEqual(done.status_code, 200)
        finished = done.json()
        self.assertEqual(finished["status"], "confirmed")
        baseline = finished["baseline"]
        self.assertEqual(baseline["status"], "ready")
        self.assertEqual(len(baseline["log_templates"]), 1)
        self.assertIn("temp_c", baseline["sensor_bands"])
        self.assertIn("defrost", baseline["sensor_bands"]["temp_c"])
        self.assertIn("error_rate", baseline["metric_bands"])

    def test_finish_without_start_is_400(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    response = client.post(
                        "/api/systems/sys-1/baseline/finish"
                    )
                    self.assertEqual(response.status_code, 400)
                    missing = client.post(
                        "/api/systems/sys-nope/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    self.assertEqual(missing.status_code, 404)

    def test_hard_limit_beats_learning(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock

        from apps.api.main import appliance_runs
        from core.setup import store as setup_store

        async def fake_run(*args, **kwargs):
            appliance_runs["gate-test-app"] = {"result": None}
            return SimpleNamespace(status="PASS")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(
                    _profile(status="armed")
                )
                with patch(
                    "apps.api.main._run_appliance_from_telemetry",
                    new=AsyncMock(side_effect=fake_run),
                ):
                    with TestClient(app) as client:
                        client.post(
                            "/api/systems/sys-1/baseline/start",
                            json={"duration_s": 60.0},
                        )
                        response = client.post(
                            "/api/incidents/candidate",
                            json={
                                "system_id": "sys-1",
                                "source": "sensor",
                                "rule": "temp_c_high",
                                "fingerprint": "f9",
                                "metrics": {"temp_c": 9.5},
                                "durations": {"temp_c": 700.0},
                            },
                        )
        body = response.json()
        # Hard limits beat even learning: this must still act.
        self.assertEqual(body["decision"]["decision"], "act")

    def test_learning_observes_non_limit_breach(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(
                    _profile(status="armed")
                )
                with TestClient(app) as client:
                    client.post(
                        "/api/systems/sys-1/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    response = client.post(
                        "/api/incidents/candidate",
                        json={
                            "system_id": "sys-1",
                            "source": "sensor",
                            "rule": "temp_c_high",
                            "fingerprint": "f10",
                            "metrics": {"temp_c": 6.5},
                            "durations": {"temp_c": 700.0},
                        },
                    )
        body = response.json()
        self.assertEqual(body["decision"]["decision"], "observe")
        self.assertIn("learning", body["decision"]["reason"])

    def test_logs_and_telemetry_auto_feed(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    client.post(
                        "/api/systems/sys-1/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    client.post(
                        "/api/logs",
                        json={
                            "message": "WARN cache cold, warming",
                            "source": "shop",
                            "system_id": "sys-1",
                        },
                    )
                    client.post(
                        "/api/telemetry/appliance",
                        json={
                            "source_id": "probe",
                            "system_id": "sys-1",
                            "temperature_c": 4.1,
                            "current_a": 1.1,
                            "vibration_g": 0.02,
                        },
                    )
                    state = client.get("/api/systems/sys-1/baseline")
        self.assertGreaterEqual(state.json()["session"]["patterns"], 2)

    def test_shop_metrics_attributed_to_software_learner(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(
                    _profile(kind="software", appliance_type=None)
                )
                with TestClient(app) as client:
                    client.post(
                        "/api/systems/sys-1/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    response = client.post(
                        "/api/sim/events",
                        json={
                            "kind": "shop_metrics",
                            "payload": {
                                "orders_per_min": 30.0,
                                "error_rate": 0.005,
                                "p95_ms": 120.0,
                            },
                        },
                    )
                    self.assertEqual(response.status_code, 200)
                    done = client.post(
                        "/api/systems/sys-1/baseline/finish"
                    )
        self.assertIn(
            "error_rate", done.json()["baseline"]["metric_bands"]
        )

    def test_learning_suppresses_overlay_trigger(self):
        from unittest.mock import AsyncMock

        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile(status="armed"))
                with patch(
                    "apps.api.main._run_appliance_from_telemetry",
                    new=AsyncMock(),
                ) as run:
                    with TestClient(app) as client:
                        client.post(
                            "/api/systems/sys-1/baseline/start",
                            json={"duration_s": 60.0},
                        )
                        bodies = []
                        for _ in range(3):
                            response = client.post(
                                "/api/telemetry/appliance",
                                json={
                                    "source_id": "learn-probe",
                                    "system_id": "sys-1",
                                    "temperature_c": 6.0,
                                    "current_a": 1.1,
                                    "vibration_g": 0.02,
                                },
                            )
                            bodies.append(response.json())
        for body in bodies:
            self.assertIsNone(body["triggered"])
        run.assert_not_called()

    def test_start_broadcasts_progress_event(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                with TestClient(app) as client:
                    with client.websocket_connect("/api/ws") as ws:
                        client.post(
                            "/api/systems/sys-1/baseline/start",
                            json={"duration_s": 60.0},
                        )
                        event = ws.receive_json()
        self.assertEqual(event["kind"], "baseline_progress")
        self.assertEqual(event["payload"]["stage"], "started")

    def test_start_without_hard_limits_learns(self):
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(
                    _profile(status="draft", hard_limits=[])
                )
                with TestClient(app) as client:
                    started = client.post(
                        "/api/systems/sys-1/baseline/start",
                        json={"duration_s": 60.0},
                    )
                    self.assertEqual(started.status_code, 200)
                    self.assertEqual(started.json()["status"], "learning")
                    profile = client.get("/api/systems/sys-1/profile")
                    self.assertEqual(
                        profile.json()["profile"]["status"], "learning"
                    )
        self.assertIn("sys-1", baseline_learners)
        self.assertIn("sys-1", baseline_sessions)

    def test_finish_task_ticks_progress_without_observations(self):
        import asyncio
        import time as time_mod
        from unittest.mock import AsyncMock

        import apps.api.main as api_main
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                learner = BaselineLearner(
                    "sys-1", started_at=time_mod.time()
                )
                baseline_learners["sys-1"] = learner
                baseline_sessions["sys-1"] = {
                    "started_at": learner.started_at,
                    "duration_s": 0.4,
                    "return_to": "confirmed",
                    "last_pct": 0.0,
                }
                with patch.object(
                    api_main.hub, "broadcast", new=AsyncMock()
                ) as broadcast:
                    asyncio.run(
                        api_main._finish_baseline_after(
                            "sys-1", learner.started_at, 0.4
                        )
                    )
                payloads = [
                    call.args[0].payload
                    for call in broadcast.await_args_list
                ]
                stored = setup_store.get_profile("sys-1")
        assert stored is not None
        percents = [item["percent"] for item in payloads]
        self.assertTrue(
            any(0.0 < pct < 100.0 for pct in percents),
            f"no intermediate progress ticks: {percents}",
        )
        self.assertEqual(payloads[-1]["stage"], "finished")
        self.assertEqual(payloads[-1]["percent"], 100.0)
        self.assertEqual(stored.baseline.status, "ready")

    def test_finish_task_error_broadcasts_blocked(self):
        import asyncio
        import time as time_mod
        from unittest.mock import AsyncMock

        import apps.api.main as api_main
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(_profile())
                learner = BaselineLearner(
                    "sys-1", started_at=time_mod.time()
                )
                baseline_learners["sys-1"] = learner
                baseline_sessions["sys-1"] = {
                    "started_at": learner.started_at,
                    "duration_s": 0.05,
                    "return_to": "confirmed",
                    "last_pct": 0.0,
                }
                with patch.object(
                    api_main.hub, "broadcast", new=AsyncMock()
                ) as broadcast:
                    with patch.object(
                        api_main,
                        "_finish_baseline",
                        new=AsyncMock(side_effect=RuntimeError("boom")),
                    ):
                        with self.assertLogs(
                            "apps.api.main", level="ERROR"
                        ):
                            asyncio.run(
                                api_main._finish_baseline_after(
                                    "sys-1", learner.started_at, 0.05
                                )
                            )
                payloads = [
                    call.args[0].payload
                    for call in broadcast.await_args_list
                ]
        blocked = [
            item for item in payloads if item.get("stage") == "blocked"
        ]
        self.assertTrue(blocked, f"no blocked event: {payloads}")
        self.assertIn("boom", blocked[-1]["reason"])


if __name__ == "__main__":
    unittest.main()
