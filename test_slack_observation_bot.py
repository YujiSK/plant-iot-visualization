import unittest
from unittest.mock import patch
from datetime import datetime, timezone
import hashlib

from slack_observation_bot import (
    ObservationConfig,
    build_care_log_payload,
    extract_observation_photo,
    fetch_previous_ai_observation,
    process_slack_event,
)


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        payload=None,
        text="OK",
        content=b"fake-image",
        headers=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300
        self.content = content
        self.headers = headers or {"Content-Type": "image/jpeg"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(
        self,
        sensor_rows=None,
        care_rows=None,
        plant_rows=None,
        care_status=201,
        plant_observation_status=201,
        slack_ok=True,
    ):
        self.sensor_rows = sensor_rows if sensor_rows is not None else []
        self.care_rows = care_rows if care_rows is not None else []
        self.plant_rows = plant_rows if plant_rows is not None else []
        self.care_status = care_status
        self.plant_observation_status = plant_observation_status
        self.slack_ok = slack_ok
        self.posts = []
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if "files.slack.com" in url:
            return FakeResponse(
                content=b"fake-image", headers={"Content-Type": "image/jpeg"}
            )
        if "/rest/v1/plant_observations" in url:
            return FakeResponse(payload=self.plant_rows)
        if "/rest/v1/care_logs" in url:
            return FakeResponse(payload=self.care_rows)
        return FakeResponse(payload=self.sensor_rows)

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        if url.endswith("/rest/v1/care_logs"):
            return FakeResponse(status_code=self.care_status, text="care error")
        if url.endswith("/rest/v1/plant_observations"):
            return FakeResponse(
                status_code=self.plant_observation_status,
                text="plant observation error",
            )
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


def previous_care_row(note_suffix=""):
    note = (
        "observed_at=2026-06-17 15:16:00 JST\n"
        'ai_observation_json={"crowding":"medium","growth_stage":"cotyledon",'
        '"plant_count_estimate":20}'
    )
    return {"created_at": "2026-06-17T06:16:00Z", "note": note + note_suffix}


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
        self.assertTrue(result["plant_observation_created"])
        care_posts = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/care_logs")
        ]
        self.assertEqual(len(care_posts), 1)
        self.assertEqual(care_posts[0]["sensor_log_id"], 10)
        self.assertIn("slack_file_id=F123", care_posts[0]["note"])
        self.assertIn("ai_observation_json=", care_posts[0]["note"])
        self.assertIn("observation_comparison_json=", care_posts[0]["note"])
        plant_observation_posts = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/plant_observations")
        ]
        self.assertEqual(len(plant_observation_posts), 1)
        self.assertEqual(plant_observation_posts[0]["sensor_log_id"], 10)
        self.assertEqual(plant_observation_posts[0]["growth_stage"], "cotyledon")
        self.assertIn("raw_ai_json", plant_observation_posts[0])
        raw_ai_json = plant_observation_posts[0]["raw_ai_json"]
        self.assertEqual(raw_ai_json["slack_ts"], "1781622600.000000")
        self.assertEqual(raw_ai_json["slack_file_id"], "F123")
        self.assertEqual(raw_ai_json["slack_file_name"], "basil.jpg")
        self.assertEqual(raw_ai_json["image_byte_size"], len(b"fake-image"))
        self.assertEqual(raw_ai_json["image_mime_type"], "image/jpeg")
        self.assertEqual(raw_ai_json["provider"], "openai")
        self.assertEqual(raw_ai_json["model"], "gpt-4.1")
        self.assertEqual(
            raw_ai_json["image_sha256"], hashlib.sha256(b"fake-image").hexdigest()
        )
        slack_posts = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url == "https://slack.com/api/chat.postMessage"
        ]
        self.assertEqual(len(slack_posts), 1)
        self.assertIn("AI観察支援", slack_posts[0]["text"])
        self.assertIn("生育段階: 子葉期", slack_posts[0]["text"])
        self.assertIn("前回との比較", slack_posts[0]["text"])

    def test_slack_reply_success_is_logged(self):
        http = FakeHttp()

        with self.assertLogs("slack_observation", level="WARNING") as logs:
            result = process_slack_event(image_event(), config(), http_client=http)

        self.assertTrue(result["reply_sent"])
        text = "\n".join(logs.output)
        self.assertIn("Slack reply sent", text)
        self.assertIn("channel=C_OBSERVE", text)
        self.assertIn("thread_ts=1781622600.000000", text)
        self.assertNotIn("xoxb-token", text)

    def test_duplicate_slack_event_is_skipped_before_ai_work(self):
        http = FakeHttp(
            care_rows=[
                {
                    "id": "care-1",
                    "note": "slack_ts=1781622600.000000",
                }
            ]
        )

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["skip_reason"], "duplicate_slack_ts")
        self.assertEqual(
            [url for url, _ in http.gets if "files.slack.com" in url],
            [],
        )
        self.assertEqual(http.posts, [])

    def test_duplicate_slack_file_id_is_skipped_before_download(self):
        http = FakeHttp(
            plant_rows=[
                {
                    "raw_ai_json": {
                        "slack_file_id": "F123",
                        "image_sha256": "other",
                    }
                }
            ]
        )

        result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["skip_reason"], "duplicate_slack_file_id")
        self.assertEqual(
            [url for url, _ in http.gets if "files.slack.com" in url],
            [],
        )
        self.assertEqual(http.posts, [])

    def test_duplicate_image_sha256_is_skipped_after_download(self):
        image_sha256 = hashlib.sha256(b"fake-image").hexdigest()
        http = FakeHttp(
            plant_rows=[
                {
                    "raw_ai_json": {
                        "slack_file_id": "F999",
                        "image_sha256": image_sha256,
                    }
                }
            ]
        )

        event = image_event()
        event["files"][0]["id"] = "F_NEW"
        result = process_slack_event(event, config(), http_client=http)

        self.assertEqual(result["status"], "duplicate")
        self.assertEqual(result["skip_reason"], "duplicate_image_sha256")
        self.assertEqual(
            len([url for url, _ in http.gets if "files.slack.com" in url]),
            1,
        )
        self.assertEqual(http.posts, [])

    def test_different_image_sha256_is_processed(self):
        http = FakeHttp(
            plant_rows=[
                {
                    "raw_ai_json": {
                        "slack_file_id": "F999",
                        "image_sha256": "different",
                    }
                }
            ]
        )

        event = image_event()
        event["files"][0]["id"] = "F_NEW"
        result = process_slack_event(event, config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        plant_observation_posts = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/plant_observations")
        ]
        self.assertEqual(len(plant_observation_posts), 1)

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
        self.assertIn("device_id=raspberrypi2", payload["note"])
        self.assertIn("location_id=location-b", payload["note"])
        self.assertIn("slack_channel_id=C_OBSERVE", payload["note"])
        self.assertIn("slack_user_id=U123", payload["note"])
        self.assertIn("AI観察支援", payload["note"])

    def test_ai_observation_failure_keeps_care_log(self):
        http = FakeHttp()

        with patch(
            "slack_observation_bot.analyze_observation",
            side_effect=RuntimeError("vision unavailable"),
        ):
            result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["care_log_created"])
        self.assertFalse(result["ai_observation_created"])
        care_payload = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/care_logs")
        ][0]
        self.assertIn("ai_observation_error=RuntimeError", care_payload["note"])
        slack_reply = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url == "https://slack.com/api/chat.postMessage"
        ][0]
        self.assertIn("AI観察支援: 今回は取得できませんでした", slack_reply["text"])

    def test_fetch_previous_ai_observation_skips_broken_json(self):
        http = FakeHttp(
            care_rows=[
                {"created_at": "2026-06-17T07:00:00Z", "note": "ai_observation_json={"},
                previous_care_row(),
            ]
        )

        previous, observed_at = fetch_previous_ai_observation(config(), http_client=http)

        self.assertEqual(previous["growth_stage"], "cotyledon")
        self.assertEqual(observed_at, "2026-06-17 15:16:00 JST")

    def test_fetch_previous_ai_observation_prefers_plant_observations(self):
        http = FakeHttp(
            plant_rows=[
                {
                    "observed_at": "2026-07-01T02:00:00Z",
                    "raw_ai_json": {
                        "growth_stage": "true_leaf_1",
                        "plant_count_estimate": 18,
                    },
                }
            ],
            care_rows=[previous_care_row()],
        )

        previous, observed_at = fetch_previous_ai_observation(config(), http_client=http)

        self.assertEqual(previous["growth_stage"], "true_leaf_1")
        self.assertEqual(observed_at, "2026-07-01T02:00:00Z")

    def test_observation_comparison_failure_keeps_care_log(self):
        http = FakeHttp()

        with patch(
            "slack_observation_bot.compare_observations",
            side_effect=RuntimeError("compare unavailable"),
        ):
            result = process_slack_event(image_event(), config(), http_client=http)

        self.assertEqual(result["status"], "recorded")
        self.assertTrue(result["care_log_created"])
        self.assertFalse(result["observation_comparison_created"])
        care_payload = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url.endswith("/rest/v1/care_logs")
        ][0]
        self.assertIn(
            "observation_comparison_error=RuntimeError", care_payload["note"]
        )
        slack_reply = [
            kwargs["json"]
            for url, kwargs in http.posts
            if url == "https://slack.com/api/chat.postMessage"
        ][0]
        self.assertIn("前回との比較: 今回は取得できませんでした", slack_reply["text"])


if __name__ == "__main__":
    unittest.main()
