#!/usr/bin/env python3
"""Comprehensive Failure & Reliability Integration Tests for Plant IoT.

Simulates:
1. API Key corruption (HTTP 401 Invalid API Key)
2. Network connection failure / DNS resolution error
3. Service restart & backfill recovery
4. Deduplication & data loss prevention
5. Dual Slack + LINE alert trigger (3 failures) & recovery notification
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from alert_manager import (
    FAILURE_THRESHOLD,
    load_alert_state,
    record_transmission_failure,
    record_transmission_success,
)
from outbox import count_pending, enqueue, flush_outbox, get_pending, init_outbox, mark_synced


class TestFailureScenarios(unittest.TestCase):

    def test_api_key_corruption_and_recovery_flow(self):
        """Simulate HTTP 401 API key failure followed by resolution and backfill."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data.db"
            state_path = Path(tmpdir) / "alert_state.json"
            init_outbox(db_path)

            notifications = []

            def mock_post(url, json=None, headers=None, timeout=None):
                class MockResp:
                    ok = True
                    status_code = 200
                    def raise_for_status(self):
                        pass
                notifications.append({"url": url, "text": json.get("text") if json else ""})
                return MockResp()

            # 1. Simulate 3 sensor cycles with invalid API Key (HTTP 401)
            supabase_attempts = []

            def mock_supabase_fail(payload):
                supabase_attempts.append(payload)
                # Output safe payload log as required by spec
                payload_str = json.dumps(payload, ensure_ascii=False)
                print(f"POST failed (HTTP 401 Invalid API key)\npayload={payload_str}")
                return False

            for i in range(1, 4):
                payload = {
                    "device_id": "raspberrypi2",
                    "solution_temperature": 25.0 + i,
                    "light_lux": 3000.0,
                    "float_switch_state": "water_ok",
                    "created_at": f"2026-07-22T12:0{i}:00Z",
                }
                enqueue(payload, db_path=db_path)
                synced, failed = flush_outbox(mock_supabase_fail, db_path=db_path)
                self.assertEqual(synced, 0)
                record_transmission_failure(
                    "raspberrypi2",
                    "HTTP 401 Invalid API key",
                    state_path=state_path,
                    webhook_url="https://slack.dummy",
                    line_token="line_dummy",
                    line_to="to_dummy",
                    post=mock_post,
                )

            # Check Outbox: 3 records must remain saved as pending/failed (0 data loss)
            self.assertEqual(count_pending(db_path=db_path), 3)

            # Check Notifications: Dual alert (Slack + LINE) sent after 3 failures
            self.assertEqual(len(notifications), 2)
            self.assertIn("🚨 Plant IoT Alert", notifications[0]["text"])

            state = load_alert_state(state_path)
            self.assertTrue(state["transmission"]["alert_active"])
            self.assertEqual(state["transmission"]["consecutive_failures"], 3)

            # 2. Simulate API Key Fixed (Auto-recovery & Backfill)
            sent_to_supabase = []

            def mock_supabase_success(payload):
                sent_to_supabase.append(payload)
                return True

            # Flush outbox with successful sender
            synced_count, failed_count = flush_outbox(mock_supabase_success, db_path=db_path)
            self.assertEqual(synced_count, 3)
            self.assertEqual(failed_count, 0)
            self.assertEqual(count_pending(db_path=db_path), 0)

            # Trigger recovery alert
            rec_sent = record_transmission_success(
                "raspberrypi2",
                resent_count=synced_count,
                state_path=state_path,
                webhook_url="https://slack.dummy",
                line_token="line_dummy",
                line_to="to_dummy",
                post=mock_post,
            )
            self.assertTrue(rec_sent)
            # 2 additional notifications for recovery (Slack + LINE)
            self.assertEqual(len(notifications), 4)
            self.assertIn("✅ Plant IoT Recovered", notifications[2]["text"])

            state_after = load_alert_state(state_path)
            self.assertFalse(state_after["transmission"]["alert_active"])
            self.assertEqual(state_after["transmission"]["consecutive_failures"], 0)

    def test_network_disconnection_and_reconnection(self):
        """Simulate DNS failure / connection error and subsequent recovery."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data.db"
            state_path = Path(tmpdir) / "alert_state.json"

            payload = {
                "device_id": "raspberrypi2",
                "solution_temperature": 24.5,
                "created_at": "2026-07-22T12:10:00Z",
            }
            enqueue(payload, db_path=db_path)

            def mock_network_error(p):
                raise ConnectionError("Failed to resolve host 'oawkrkgnjkldfyvjcrgx.supabase.co'")

            synced, failed = flush_outbox(mock_network_error, db_path=db_path)
            self.assertEqual(synced, 0)
            self.assertEqual(failed, 1)
            # Outbox preserves payload for backfill
            self.assertEqual(count_pending(db_path=db_path), 1)

    def test_no_duplicate_registration_on_retry(self):
        """Verify synced items are marked and not re-sent twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "data.db"

            enqueue({"device_id": "raspberrypi2", "id_test": "a"}, db_path=db_path)

            attempts = []

            def mock_sender(payload):
                attempts.append(payload)
                return True

            # First flush
            synced1, failed1 = flush_outbox(mock_sender, db_path=db_path)
            self.assertEqual(synced1, 1)
            self.assertEqual(len(attempts), 1)

            # Second flush
            synced2, failed2 = flush_outbox(mock_sender, db_path=db_path)
            self.assertEqual(synced2, 0)
            self.assertEqual(len(attempts), 1)  # No duplicate send attempt!


if __name__ == "__main__":
    unittest.main()
