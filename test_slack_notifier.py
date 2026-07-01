import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import send_sensor_raspberrypi2
from slack_notifier import LINE_PUSH_MESSAGE_URL, load_notification_state, process_notifications


class FakeResponse:
    def __init__(self, error=None):
        self.error = error

    def raise_for_status(self):
        if self.error:
            raise self.error


def payload(float_state):
    return {
        "device_id": "raspberrypi2",
        "location_id": "location-b",
        "float_switch_state": float_state,
        "vitality_score": 25 if float_state == "low_water" else 100,
        "solution_temperature": 26.5,
        "light_lux": 250.0,
    }


class SlackNotifierTest(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.state_path = Path(self.temporary_directory.name) / "state.json"
        self.messages = []

    def tearDown(self):
        self.temporary_directory.cleanup()

    def post_success(self, url, json, timeout, headers=None):
        self.messages.append(json["text"])
        return FakeResponse()

    def process(self, float_state):
        return process_notifications(
            payload(float_state),
            state_path=self.state_path,
            webhook_url="https://example.invalid/slack",
            line_channel_access_token="",
            line_to_id="",
            post=self.post_success,
        )

    def test_water_ok_to_low_water_sends_alert(self):
        self.process("water_ok")
        self.process("low_water")

        self.assertEqual(len(self.messages), 1)
        self.assertIn("Plant IoT Alert", self.messages[0])
        self.assertIn("培地表面の湿潤状態", self.messages[0])

    def test_low_water_sends_line_when_configured(self):
        posts = []

        def post(url, json, timeout, headers=None):
            posts.append((url, json, headers))
            return FakeResponse()

        process_notifications(
            payload("low_water"),
            state_path=self.state_path,
            webhook_url="https://example.invalid/slack",
            line_channel_access_token="line-token",
            line_to_id="U123",
            post=post,
        )

        self.assertEqual([post[0] for post in posts], [
            "https://example.invalid/slack",
            LINE_PUSH_MESSAGE_URL,
        ])
        self.assertEqual(posts[1][1]["to"], "U123")
        self.assertEqual(
            posts[1][2],
            {"Authorization": "Bearer line-token"},
        )
        self.assertIn("Plant IoT Alert", posts[1][1]["messages"][0]["text"])

    def test_line_failure_does_not_retry_after_slack_success(self):
        def post(url, json, timeout, headers=None):
            if url == LINE_PUSH_MESSAGE_URL:
                raise RuntimeError("line unavailable")
            return FakeResponse()

        process_notifications(
            payload("low_water"),
            state_path=self.state_path,
            webhook_url="https://example.invalid/slack",
            line_channel_access_token="line-token",
            line_to_id="U123",
            post=post,
        )

        state = load_notification_state(self.state_path)
        self.assertTrue(state["low_water"]["active"])

    def test_continuing_low_water_does_not_duplicate(self):
        self.process("low_water")
        self.process("low_water")

        self.assertEqual(len(self.messages), 1)

    def test_recovery_requires_two_consecutive_water_ok_readings(self):
        self.process("low_water")
        self.process("water_ok")
        self.assertEqual(len(self.messages), 1)

        self.process("water_ok")
        self.assertEqual(len(self.messages), 2)
        self.assertIn("Plant IoT Recovery", self.messages[1])

    def test_continuing_water_ok_does_not_notify(self):
        self.process("water_ok")
        self.process("water_ok")

        self.assertEqual(self.messages, [])

    def test_missing_webhook_does_not_mark_alert_active(self):
        process_notifications(
            payload("low_water"),
            state_path=self.state_path,
            webhook_url="",
            line_channel_access_token="",
            line_to_id="",
        )

        state = load_notification_state(self.state_path)
        self.assertFalse(state["low_water"]["active"])

    def test_failed_slack_send_is_retried(self):
        def post_failure(url, json, timeout, headers=None):
            raise RuntimeError("network unavailable")

        process_notifications(
            payload("low_water"),
            state_path=self.state_path,
            webhook_url="https://example.invalid/slack",
            line_channel_access_token="",
            line_to_id="",
            post=post_failure,
        )
        self.process("low_water")

        self.assertEqual(len(self.messages), 1)

    def test_primary_device_is_ignored(self):
        primary_payload = payload("low_water")
        primary_payload["device_id"] = "raspi"
        process_notifications(
            primary_payload,
            state_path=self.state_path,
            webhook_url="https://example.invalid/slack",
            line_channel_access_token="",
            line_to_id="",
            post=self.post_success,
        )

        self.assertEqual(self.messages, [])

    def test_slack_failure_does_not_cancel_supabase_send(self):
        sent_payloads = []
        sensor_payload = payload("low_water")

        with (
            patch.object(send_sensor_raspberrypi2, "build_payload", return_value=sensor_payload),
            patch.object(
                send_sensor_raspberrypi2,
                "send_to_supabase",
                side_effect=lambda value: sent_payloads.append(value),
            ),
            patch.object(
                send_sensor_raspberrypi2,
                "process_notifications",
                side_effect=RuntimeError("slack failed"),
            ),
        ):
            send_sensor_raspberrypi2.process_sensor_cycle()

        self.assertEqual(sent_payloads, [sensor_payload])


if __name__ == "__main__":
    unittest.main()
