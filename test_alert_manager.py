#!/usr/bin/env python3
"""Unit tests for alert_manager.py using unittest."""

import json
import tempfile
import unittest
from pathlib import Path

from alert_manager import (
    FAILURE_THRESHOLD,
    load_alert_state,
    record_transmission_failure,
    record_transmission_success,
)


class TestAlertManager(unittest.TestCase):

    def test_failure_threshold_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "alert_state.json"
            broadcast_calls = []

            def mock_post(url, json=None, headers=None, timeout=None):
                class MockResponse:
                    ok = True
                    status_code = 200
                    def raise_for_status(self):
                        pass
                broadcast_calls.append({"url": url, "json": json})
                return MockResponse()

            # Failures 1 and 2 should NOT trigger alert
            alert1 = record_transmission_failure(
                "raspberrypi2",
                "HTTP 401 Unauthorized",
                state_path=state_path,
                webhook_url="https://slack.dummy",
                line_token="line_token_dummy",
                line_to="line_to_dummy",
                post=mock_post,
            )
            self.assertFalse(alert1)
            self.assertEqual(len(broadcast_calls), 0)

            alert2 = record_transmission_failure(
                "raspberrypi2",
                "HTTP 401 Unauthorized",
                state_path=state_path,
                webhook_url="https://slack.dummy",
                line_token="line_token_dummy",
                line_to="line_to_dummy",
                post=mock_post,
            )
            self.assertFalse(alert2)

            # Failure 3 MUST trigger alert
            alert3 = record_transmission_failure(
                "raspberrypi2",
                "HTTP 401 Unauthorized",
                state_path=state_path,
                webhook_url="https://slack.dummy",
                line_token="line_token_dummy",
                line_to="line_to_dummy",
                post=mock_post,
            )
            self.assertTrue(alert3)
            # Should have called both Slack and LINE (2 calls total)
            self.assertEqual(len(broadcast_calls), 2)
            self.assertIn("🚨 Plant IoT Alert", broadcast_calls[0]["json"]["text"])

            state = load_alert_state(state_path)
            self.assertTrue(state["transmission"]["alert_active"])

            # Next success MUST trigger recovery alert
            rec = record_transmission_success(
                "raspberrypi2",
                resent_count=15,
                state_path=state_path,
                webhook_url="https://slack.dummy",
                line_token="line_token_dummy",
                line_to="line_to_dummy",
                post=mock_post,
            )
            self.assertTrue(rec)
            # 2 more calls for recovery message (Slack + LINE)
            self.assertEqual(len(broadcast_calls), 4)
            self.assertIn("✅ Plant IoT Recovered", broadcast_calls[2]["json"]["text"])

            state = load_alert_state(state_path)
            self.assertFalse(state["transmission"]["alert_active"])
            self.assertEqual(state["transmission"]["consecutive_failures"], 0)


if __name__ == "__main__":
    unittest.main()
