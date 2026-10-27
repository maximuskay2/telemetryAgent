"""Analyzer must route only to Meta models (hackathon compliance).

`core/infer/analyzer.py` backs `POST /api/diagnose`. Any non-Meta fallback
model here would violate the "Meta models only" rule, so these tests pin:
no keys -> not-configured diagnosis pointing at MODEL_API_KEY, and a
Fireworks key alone must never trigger an HTTP inference call.
"""

import os
import unittest
from unittest.mock import patch

from core.infer import analyzer
from core.schemas.diagnosis import Diagnosis
from core.schemas.telemetry import SoftwareTelemetry


class MetaOnlyTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_keys_returns_not_configured_pointing_at_meta(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            result = await analyzer.diagnose("deadlock log")
        self.assertIsInstance(result, Diagnosis)
        self.assertEqual(result.confidence, 0.0)
        self.assertIn("MODEL_API_KEY", result.likely_cause + result.summary)

    async def test_fireworks_key_alone_never_calls_http_inference(self) -> None:
        with patch.dict(os.environ, {"FIREWORKS_API_KEY": "x"}, clear=True):
            with patch(
                "httpx.AsyncClient", side_effect=AssertionError("must not call")
            ) as client:
                result = await analyzer.diagnose("deadlock log")
        client.assert_not_called()
        self.assertEqual(result.confidence, 0.0)

    async def test_meta_key_routes_to_muse_spark(self) -> None:
        expected = Diagnosis(
            summary="Deadlock",
            likely_cause="Lock ordering inversion",
            suggested_actions=["Fix order"],
            confidence=0.9,
        )
        with patch.dict(os.environ, {"MODEL_API_KEY": "k"}, clear=True):
            with patch(
                "core.infer.meta_client.diagnose", return_value=expected
            ) as diag:
                result = await analyzer.diagnose("deadlock log")
        self.assertEqual(result, expected)
        sent = SoftwareTelemetry.model_validate_json(diag.call_args.args[0])
        self.assertEqual((sent.source_id, sent.raw_log), ("diagnose", "deadlock log"))


if __name__ == "__main__":
    unittest.main()
