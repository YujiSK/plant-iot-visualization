import unittest
from datetime import datetime, timezone

from slack_observation_bot import (
    ObservationConfig,
    build_care_log_payload,
    extract_observation_photo,
    process_slack_event,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="OK"):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(self, sensor_rows=None, care_status=201, slack_ok=True):
        self.sensor_rows = sensor_rows if sensor_rows is not None else []
        self.care_status = care_status
        self.slack_ok = slack_ok
        self.posts = []
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return FakeResponse(payload=self.sensor_rows)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/rest/v1/care_logs"):
            return FakeResponse(status_code=self.care_status, text="care error")
        return FakeResponse(payload={"ok": self.slack_ok}, text="slack error")


def config():
    return ObservationConfig(
        supabase_url="https://example.supabase.co",
        supabase_key="anon-key",
        slack_bot_token="xoxb-token",
        signing_secret="secret",
        observation_channel_id="C_OBSERVE",
    )


def image_event(**overrides):
    base = {
        "type": "message",
        "channel": "C_OBSERVE",
        "user": "U123",
        "ts": "1781622600.000000",
        "files": [
            {
                "id": "F123",
                "name": "basil.jpg",
                "mimetype": "image/jpeg",
                "url_private": "https://files.slack.com/files-pri/T/F123/basil.jpg",
            }
        ],
    }
    base.update(overrides)
    return base


class SlackObservationBotTest(unittest.TestCase):
    def test_image_event_creates_care_log(self):
        observed = datetime.fromtimestamp(1781622600.0, tz=timezone.utc)
        http = FakeHttp(
            sensor_rows=[
                {
                    "id": 10,
                    "created_at": observed.isoformat(),
                    "vitality_score": 75,
                    "float_switch_state": "water_ok",
                    "solution_temperature": 23.8,
                    "light_lux": 0,
                    "message": "ok",
                }
            ]
        )

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["care_log_created"])
        self.assertTrue(result["nearest_sensor_log_found"])
        care_posts = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/care_logs")
        ]
        self.assertEqual(len(care_posts), 1)
        self.assertEqual(care_posts[0]["sensor_log_id"], 10)
        self.assertIn("slack_file_id=F123", care_posts[0]["note"])

    def test_text_only_event_is_ignored(self):
        event = image_event(files=[])

        self.assertIsNone(extract_observation_photo(event, "C_OBSERVE"))

    def test_other_channel_is_ignored(self):
        event = image_event(channel="C_OTHER")

        self.assertIsNone(extract_observation_photo(event, "C_OBSERVE"))

    def test_bot_message_is_ignored(self):
        event = image_event(bot_id="B123")

        self.assertIsNone(extract_observation_photo(event, "C_OBSERVE"))

    def test_supabase_insert_failure_does_not_raise(self):
        http = FakeHttp(care_status=500)

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "failed")
        self.assertFalse(result["care_log_created"])

    def test_no_nearest_sensor_log_still_creates_care_log(self):
        http = FakeHttp(sensor_rows=[])

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        self.assertFalse(result["nearest_sensor_log_found"])
        care_payload = http.posts[0][1]["json"]
        self.assertNotIn("sensor_log_id", care_payload)

    def test_slack_reply_failure_keeps_care_log(self):
        http = FakeHttp(slack_ok=False)

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["care_log_created"])
        self.assertFalse(result["reply_sent"])

    def test_payload_note_contains_slack_metadata_without_metadata_column(self):
        observation = extract_observation_photo(image_event(), "C_OBSERVE")
        payload = build_care_log_payload(observation, config())

        self.assertEqual(payload["action_type"], "checked")
        self.assertIn("slack_channel_id=C_OBSERVE", payload["note"])
        self.assertIn("slack_user_id=U123", payload["note"])
        self.assertIn("AI解析は未実施", payload["note"])


if __name__ == "__main__":
    unittest.main()
