"""Provider errors must translate to actionable failures, never raw SDK reprs."""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.infer.errors import translate


class FakeStatusError(Exception):
    def __init__(self, status_code, message="boom"):
        super().__init__(message)
        self.status_code = status_code


class TranslateTests(unittest.TestCase):
    def test_unauthorized_points_at_key(self) -> None:
        err = translate(
            FakeStatusError(401), provider="Baseten", action="generation"
        )
        self.assertIn("rejected the API key (401)", str(err))
        self.assertIn("Baseten", str(err))

    def test_not_found_points_at_model_id(self) -> None:
        err = translate(
            FakeStatusError(404, "model_not_found"),
            provider="Meta Model API",
            action="diagnosis",
        )
        self.assertIn("could not find the model (404)", str(err))
        self.assertIn("model id", str(err))

    def test_rate_limit_mentions_failover(self) -> None:
        err = translate(FakeStatusError(429), provider="Fireworks", action="x")
        self.assertIn("rate-limited", str(err))
        self.assertIn("fails over", str(err))

    def test_other_status_included(self) -> None:
        err = translate(FakeStatusError(500), provider="P", action="a")
        self.assertIn("(500)", str(err))

    def test_connection_failure_flagged_transient(self) -> None:
        class ConnectionFailed(Exception):
            pass

        err = translate(ConnectionFailed("reset"), provider="P", action="a")
        self.assertIn("transiently", str(err))

    def test_unknown_error_keeps_provider_and_action(self) -> None:
        err = translate(ValueError("weird"), provider="P", action="a")
        self.assertIn("P", str(err))
        self.assertIn("a", str(err))

    def test_long_detail_truncated(self) -> None:
        err = translate(ValueError("x" * 1000), provider="P", action="a")
        self.assertLess(len(str(err)), 500)
        self.assertIn("…", str(err))


class ClientWiringTests(unittest.TestCase):
    def _failing_client(self, exc):
        client = MagicMock()
        client.chat.completions.create.side_effect = exc
        return client

    def test_baseten_rate_limit_translates(self) -> None:
        from core.infer import baseten_client
        from core.schemas.diagnosis import Diagnosis

        diag = Diagnosis(
            summary="s", likely_cause="c", suggested_actions=[], confidence=0.5
        )
        with patch.dict(os.environ, {"BASETEN_API_KEY": "x"}), patch.object(
            baseten_client,
            "_client",
            return_value=self._failing_client(FakeStatusError(429)),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                baseten_client.generate_patch(diag)
        self.assertIn("rate-limited", str(ctx.exception))

    def test_meta_unauthorized_translates(self) -> None:
        from core.infer import meta_client

        with patch.dict(os.environ, {"MODEL_API_KEY": "bad"}), patch.object(
            meta_client,
            "_client",
            return_value=self._failing_client(FakeStatusError(401)),
        ):
            with self.assertRaises(RuntimeError) as ctx:
                meta_client.diagnose("{}")
        self.assertIn("rejected the API key (401)", str(ctx.exception))

    def test_missing_key_messages_preserved(self) -> None:
        from core.infer import baseten_client, fireworks_client, meta_client
        from core.schemas.diagnosis import Diagnosis

        diag = Diagnosis(
            summary="s", likely_cause="c", suggested_actions=[], confidence=0.5
        )
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError) as ctx:
                baseten_client.generate_patch(diag)
            self.assertIn("BASETEN_API_KEY", str(ctx.exception))
            with self.assertRaises(RuntimeError) as ctx:
                fireworks_client.generate_patch(diag)
            self.assertIn("FIREWORKS_API_KEY", str(ctx.exception))
            with self.assertRaises(RuntimeError) as ctx:
                meta_client.diagnose("{}")
            self.assertIn("MODEL_API_KEY", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
