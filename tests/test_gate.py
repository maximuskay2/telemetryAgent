"""P5 gate tests: one per check, in check order."""

import unittest

from core.schemas.profile import (
    Baseline,
    ExpectedBehaviour,
    FailureDefinition,
    HardLimit,
    ModeRelaxation,
    Provenance,
    SystemProfile,
)
from core.setup.gate import (
    Candidate,
    evaluate,
    relax_matches,
    template_of,
)
from core.setup.modes import ModeState


def _prov(doc="coldchain_spec_sheet.pdf", region="p.1"):
    return Provenance(source_doc=doc, page_or_region=region, quote="q")


def make_profile(**over):
    data = {
        "system_id": "sys-1",
        "name": "walk-in",
        "kind": "appliance",
        "appliance_type": "fridge",
        "status": "armed",
        "hard_limits": [],
        "expected_behaviours": [],
        "modes": [],
        "baseline": Baseline(status="none").model_dump(),
        "failure_definitions": [],
    }
    data.update(over)
    return SystemProfile(**data)


def armed_profile():
    return make_profile(
        hard_limits=[
            HardLimit(
                metric="temp_c", op=">", threshold=8.0,
                provenance=_prov(),
            ).model_dump()
        ],
        expected_behaviours=[
            ExpectedBehaviour(
                name="defrost cycle",
                signature="fridge defrost",
                allowed_effect="temp_c up to 7 C",
                max_duration_s=1200.0,
                provenance=_prov(),
            ).model_dump()
        ],
        modes=[
            ModeRelaxation(
                mode="defrost", relaxes=["temp_c up to 7 C"],
                provenance=_prov(),
            ).model_dump()
        ],
        failure_definitions=[
            FailureDefinition(
                name="hot cabinet",
                metric="temp_c", op=">", threshold=5.5,
                duration_s=600.0,
                provenance=_prov(region="p.2"),
            ).model_dump()
        ],
    )


class GateOrderTests(unittest.TestCase):
    def test_hard_limit_beats_expected_behaviour(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="fridge defrost",
            fingerprint="f1", metrics={"temp_c": 9.0},
            durations={"temp_c": 60.0}, mode="defrost",
        )
        decision = evaluate(candidate, profile, ModeState(mode="defrost"))
        self.assertEqual(decision.decision, "act")
        self.assertIn("Hard limit", decision.reason)
        self.assertIn("coldchain_spec_sheet.pdf", decision.citation)
        self.assertEqual(decision.checks[0].name, "hard_limit")
        self.assertEqual(decision.checks[0].result, "trigger")

    def test_armed_within_impact_acts_with_citation(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f2", metrics={"temp_c": 6.2},
            durations={"temp_c": 700.0},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "act")
        self.assertIn("hot cabinet", decision.reason)
        self.assertEqual(decision.citation, "coldchain_spec_sheet.pdf p.2")

    def test_unarmed_observes_with_setup_needed(self):
        profile = make_profile(status="draft")
        candidate = Candidate(
            system_id="sys-1", source="log", rule="deadlock",
            fingerprint="f3",
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "observe")
        self.assertIn("Setup needed", decision.reason)
        self.assertEqual(decision.recheck_in_s, 30.0)

    def test_missing_profile_observes(self):
        candidate = Candidate(
            system_id="sys-9", source="log", rule="deadlock",
            fingerprint="f9",
        )
        decision = evaluate(candidate, None, ModeState())
        self.assertEqual(decision.decision, "observe")
        self.assertIn("Setup needed", decision.reason)

    def test_expected_behaviour_within_duration_suppresses(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="log", rule="fridge defrost",
            fingerprint="f4", metrics={"temp_c": 6.5},
            durations={"temp_c": 300.0}, mode="defrost",
        )
        decision = evaluate(candidate, profile, ModeState(mode="defrost"))
        self.assertEqual(decision.decision, "suppress")
        self.assertIn("defrost cycle", decision.reason)
        self.assertIn("coldchain_spec_sheet.pdf", decision.citation)

    def test_mode_relax_under_bound_suppresses(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f5", metrics={"temp_c": 6.5},
            durations={"temp_c": 120.0}, mode="defrost",
        )
        self.assertTrue(relax_matches("temp_c up to 7 C", candidate))
        decision = evaluate(candidate, profile, ModeState(mode="defrost"))
        self.assertEqual(decision.decision, "suppress")
        self.assertIn("Mode defrost explains it", decision.reason)

    def test_mode_relax_over_bound_does_not_suppress(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f6", metrics={"temp_c": 7.5},
            durations={"temp_c": 120.0}, mode="defrost",
        )
        self.assertFalse(relax_matches("temp_c up to 7 C", candidate))
        decision = evaluate(candidate, profile, ModeState(mode="defrost"))
        self.assertNotEqual(decision.decision, "suppress")

    def test_expected_over_allowed_effect_does_not_suppress(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="fridge defrost",
            fingerprint="f13", metrics={"temp_c": 7.5},
            durations={"temp_c": 300.0},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "observe")
        expected = [
            c for c in decision.checks if c.name == "expected"
        ]
        self.assertTrue(
            any("exceeded allowed effect" in c.detail for c in expected)
        )

    def test_overrun_expected_duration_acts(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="fridge defrost",
            fingerprint="f7", metrics={"temp_c": 7.5},
            durations={"temp_c": 1500.0}, mode="defrost",
        )
        decision = evaluate(candidate, profile, ModeState(mode="defrost"))
        self.assertEqual(decision.decision, "act")
        self.assertIn("hot cabinet", decision.reason)

    def test_overrun_mode_is_an_anomaly(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f8", metrics={"temp_c": 6.5},
            durations={"temp_c": 120.0}, mode="defrost",
        )
        mode = ModeState(mode="defrost", overrun=True, max_duration_s=1200.0)
        decision = evaluate(candidate, profile, mode)
        # Never suppressed; at minimum an observe naming the overrun.
        self.assertEqual(decision.decision, "observe")
        self.assertIn("overran", decision.reason)
        mode_check = next(
            c for c in decision.checks if c.name == "mode"
        )
        self.assertEqual(mode_check.result, "trigger")

    def test_overrun_with_impact_acts(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f8b", metrics={"temp_c": 6.5},
            durations={"temp_c": 700.0}, mode="defrost",
        )
        mode = ModeState(mode="defrost", overrun=True, max_duration_s=1200.0)
        decision = evaluate(candidate, profile, mode)
        self.assertEqual(decision.decision, "act")
        self.assertIn("hot cabinet", decision.reason)

    def test_baseline_template_suppresses(self):
        signature = "ERROR order=a1 items=axle retry 3"
        profile = make_profile(
            hard_limits=[
                HardLimit(
                    metric="temp_c", op=">", threshold=8.0,
                    provenance=_prov(),
                ).model_dump()
            ],
            baseline=Baseline(
                status="ready",
                log_templates=[
                    {"template": template_of(signature), "rate_per_min": 0.2}
                ],
            ).model_dump(),
        )
        candidate = Candidate(
            system_id="sys-1", source="log", rule="retry_cluster",
            fingerprint="f10", signature=signature,
            window="ERROR order=b2 items=axle retry 3",
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "suppress")
        self.assertEqual(decision.citation, "baseline")

    def test_no_impact_observes(self):
        profile = armed_profile()
        candidate = Candidate(
            system_id="sys-1", source="sensor", rule="temp_high",
            fingerprint="f11", metrics={"temp_c": 5.8},
            durations={"temp_c": 60.0},
        )
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "observe")
        self.assertIn("No impact yet", decision.reason)
        self.assertEqual(decision.recheck_in_s, 30.0)

    def test_payload_has_reason_and_citation(self):
        decision = evaluate(
            Candidate(
                system_id="sys-1", source="log", rule="deadlock",
                fingerprint="f12",
            ),
            make_profile(status="draft"),
            ModeState(),
        )
        payload = decision.payload()
        self.assertIn("reason", payload)
        self.assertIn("citation", payload)
        self.assertEqual(payload["system_id"], "sys-1")
        self.assertEqual(payload["fingerprint"], "f12")
        self.assertTrue(payload["checks"])

    def test_log_template_normalizes_ids(self):
        self.assertEqual(
            template_of("ERROR order=a1 items=axle retry 3"),
            template_of("ERROR order=b2 items=axle retry 9"),
        )
        self.assertNotEqual(
            template_of("ERROR order=a1 items=axle retry 3"),
            template_of("Deadlock detected on inventory_items"),
        )


if __name__ == "__main__":
    unittest.main()


class SensorWatchTests(unittest.TestCase):
    def test_in_band_feeds_propose_nothing(self):
        from core.setup.sensor_watch import SignalWatch

        watch = SignalWatch("sys-1")
        self.assertIsNone(watch.feed("temp_c", 4.0, 100.0))
        self.assertIsNone(watch.feed("temp_c", 4.1, 101.0))

    def test_breach_proposes_candidate_with_duration(self):
        from core.setup.sensor_watch import SignalWatch

        watch = SignalWatch("sys-1")
        first = watch.feed("temp_c", 7.0, 100.0)
        assert first is not None
        self.assertEqual(first.rule, "temp_c_high")
        self.assertEqual(first.durations["temp_c"], 0.0)
        second = watch.feed("temp_c", 7.1, 160.0)
        assert second is not None
        self.assertEqual(second.durations["temp_c"], 60.0)
        self.assertEqual(second.metrics["temp_c"], 7.1)

    def test_return_to_band_resets_duration(self):
        from core.setup.sensor_watch import SignalWatch

        watch = SignalWatch("sys-1")
        watch.feed("temp_c", 7.0, 100.0)
        self.assertIsNone(watch.feed("temp_c", 4.0, 112.0))
        again = watch.feed("temp_c", 7.0, 200.0)
        assert again is not None
        self.assertEqual(again.durations["temp_c"], 0.0)

    def test_door_open_pulse_does_not_page(self):
        from core.setup.sensor_watch import SignalWatch

        watch = SignalWatch(
            "sys-1", bands={"door_open_s": (0.0, 5.0)}
        )
        candidate = watch.feed("door_open_s", 12.0, 100.0)
        assert candidate is not None
        profile = make_profile(
            hard_limits=[
                HardLimit(
                    metric="temp_c", op=">", threshold=8.0,
                    provenance=_prov(),
                ).model_dump()
            ],
            failure_definitions=[
                FailureDefinition(
                    name="door left open",
                    metric="door_open_s", op=">", threshold=30.0,
                    duration_s=60.0,
                    provenance=_prov(),
                ).model_dump()
            ],
        )
        watch.feed("door_open_s", 0.0, 112.0)
        decision = evaluate(candidate, profile, ModeState())
        self.assertEqual(decision.decision, "observe")


class CandidateApiTests(unittest.TestCase):
    def tearDown(self) -> None:
        from apps.api.main import signal_watches, software_runs

        signal_watches.clear()
        software_runs.pop("gate-test", None)

    def _software_profile(self):
        return make_profile(
            kind="software",
            appliance_type=None,
            hard_limits=[
                HardLimit(
                    metric="error_rate", op=">", threshold=0.9,
                    provenance=_prov(),
                ).model_dump()
            ],
            failure_definitions=[
                FailureDefinition(
                    name="checkout errors",
                    metric="error_rate", op=">", threshold=0.2,
                    duration_s=600.0,
                    provenance=_prov(),
                ).model_dump()
            ],
        )

    def test_unknown_system_observes_without_run(self):
        import tempfile
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from apps.api.main import app

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/incidents/candidate",
                        json={
                            "system_id": "sys-unknown",
                            "rule": "deadlock",
                            "fingerprint": "f1",
                        },
                    )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"]["decision"], "observe")
        self.assertIsNone(body["run_id"])

    def test_suppress_broadcasts_gate_decision(self):
        import tempfile
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from apps.api.main import app
        from core.setup import modes as setup_modes
        from core.setup import store as setup_store

        profile = armed_profile()
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(profile)
                setup_modes.set_mode("sys-1", "defrost")
                with TestClient(app) as client:
                    with client.websocket_connect("/api/ws") as ws:
                        response = client.post(
                            "/api/incidents/candidate",
                            json={
                                "system_id": "sys-1",
                                "source": "sensor",
                                "rule": "temp_c_high",
                                "fingerprint": "f1",
                                "metrics": {"temp_c": 6.5},
                                "durations": {"temp_c": 120.0},
                            },
                        )
                        event = ws.receive_json()
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"]["decision"], "suppress")
        self.assertIsNone(body["run_id"])
        self.assertEqual(event["kind"], "gate_decision")
        self.assertEqual(event["payload"]["decision"], "suppress")
        self.assertIn("citation", event["payload"])

    def test_act_starts_run_with_gate_attached(self):
        import tempfile
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from apps.api.main import app, software_runs
        from core.setup import store as setup_store

        async def fake_run(request):
            software_runs["gate-test"] = {
                "target": "inventory", "result": None
            }
            return SimpleNamespace(status="fixed")

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(self._software_profile())
                with patch(
                    "apps.api.main.run_agent",
                    new=AsyncMock(side_effect=fake_run),
                ):
                    with TestClient(app) as client:
                        response = client.post(
                            "/api/incidents/candidate",
                            json={
                                "system_id": "sys-1",
                                "rule": "retry_cluster",
                                "fingerprint": "f2",
                                "signature": "retries on checkout",
                                "window": "ERROR retry 1\nERROR retry 2",
                                "metrics": {"error_rate": 0.5},
                                "durations": {"error_rate": 700.0},
                            },
                        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"]["decision"], "act")
        self.assertEqual(body["run_id"], "gate-test")
        self.assertEqual(
            software_runs["gate-test"]["gate"]["decision"], "act"
        )

    def test_sensor_ingest_suppresses_overlay_trigger(self):
        import tempfile
        from unittest.mock import AsyncMock, patch

        from fastapi.testclient import TestClient

        from apps.api.main import app
        from core.setup import modes as setup_modes
        from core.setup import store as setup_store

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                setup_store.save_profile(armed_profile())
                setup_modes.set_mode("sys-1", "defrost")
                with patch(
                    "apps.api.main._run_appliance_from_telemetry",
                    new=AsyncMock(),
                ) as run:
                    with TestClient(app) as client:
                        bodies = []
                        for _ in range(3):
                            response = client.post(
                                "/api/telemetry/appliance",
                                json={
                                    "source_id": "gate-probe",
                                    "system_id": "sys-1",
                                    "temperature_c": 6.5,
                                    "current_a": 1.1,
                                    "vibration_g": 0.02,
                                },
                            )
                            bodies.append(response.json())
        for body in bodies:
            self.assertIsNone(body["triggered"])
            self.assertEqual(body["gate"]["decision"], "suppress")
        run.assert_not_called()

    def test_sensor_ingest_without_system_has_no_gate(self):
        import tempfile
        from unittest.mock import patch

        from fastapi.testclient import TestClient

        from apps.api.main import app

        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict("os.environ", {"TA_DATA_DIR": tmp}):
                with TestClient(app) as client:
                    response = client.post(
                        "/api/telemetry/appliance",
                        json={
                            "source_id": "gate-probe-2",
                            "temperature_c": 3.5,
                            "current_a": 1.1,
                            "vibration_g": 0.02,
                        },
                    )
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["gate"])
