"""Orchestrator should speak OpenAI quota errors instead of crashing."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from orchestrator import (  # noqa: E402
    LlmUnavailableError,
    _create_response,
    is_fatal_llm_error,
    llm_error_speech,
)


QUOTA = Exception(
    "Error code: 429 - {'error': {'message': 'You have no credits remaining. "
    "Add credits to continue using the API at https://platform.openai.com/settings/"
    "organization/billing/.', 'type': 'insufficient_quota', 'param': None, "
    "'code': 'credit_balance_exhausted'}}"
)


class LlmErrorSpeechTests(unittest.TestCase):
    def test_credits_message_without_url(self) -> None:
        spoken = llm_error_speech(QUOTA)
        self.assertIn("no credits remaining", spoken.lower())
        self.assertNotIn("http", spoken)
        self.assertTrue(is_fatal_llm_error(QUOTA))

    def test_rate_limit_quota_is_fatal(self) -> None:
        err = type("RateLimitError", (Exception,), {"status_code": 429})(
            "Error code: 429 - credit_balance_exhausted"
        )
        self.assertTrue(is_fatal_llm_error(err))
        self.assertIn("credits", llm_error_speech(err).lower())

    def test_stream_iteration_quota_does_not_retry_sync(self) -> None:
        client = MagicMock()
        stream = MagicMock()
        stream.__iter__.side_effect = QUOTA
        client.responses.create.return_value = stream
        tts = MagicMock()
        with patch("orchestrator.TTS_STREAM", True), patch(
            "orchestrator.LowLatencyTTS", tts
        ):
            with self.assertRaises(LlmUnavailableError) as ctx:
                _create_response(client, llm_tts=tts, model="gpt-5-mini", input="hi")
        self.assertIn("credits", str(ctx.exception).lower())
        self.assertEqual(client.responses.create.call_count, 1)
        err = Exception("network timeout")
        self.assertFalse(is_fatal_llm_error(err))


class CreateResponseQuotaTests(unittest.TestCase):
    def test_stream_quota_does_not_retry_sync_create(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = QUOTA
        tts = MagicMock()
        with patch("orchestrator.TTS_STREAM", True), patch(
            "orchestrator.LowLatencyTTS", tts
        ):
            with self.assertRaises(LlmUnavailableError) as ctx:
                _create_response(client, llm_tts=tts, model="gpt-5-mini", input="hi")
        self.assertIn("credits", str(ctx.exception).lower())
        self.assertEqual(client.responses.create.call_count, 1)

    def test_nonstream_quota_raises_unavailable(self) -> None:
        client = MagicMock()
        client.responses.create.side_effect = QUOTA
        with patch("orchestrator.TTS_STREAM", False):
            with self.assertRaises(LlmUnavailableError):
                _create_response(client, llm_tts=None, model="gpt-5-mini", input="hi")


if __name__ == "__main__":
    unittest.main()
