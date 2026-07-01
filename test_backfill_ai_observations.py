import hashlib
import unittest
from unittest.mock import patch

from backfill_ai_observations import (
    build_backfill_payload,
    load_backfill_candidates,
    parse_note_metadata,
    run_backfill,
)
from slack_observation_bot import ImageIdentity, ObservationConfig


class FakeResponse:
    def __init__(
        self,
        status_code=200,
        payload=None,
        text="OK",
        content=b"historical-image",
        headers=None,
    ):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300
        self.content = content
        self.headers = headers or {"Content-Type": "image/png"}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeHttp:
    def __init__(
        self,
        care_rows=None,
        plant_rows=None,
        download_status=200,
        plant_status=201,
    ):
        self.care_rows = care_rows if care_rows is not None else []
        self.plant_rows = plant_rows if plant_rows is not None else []
        self.download_status = download_status
        self.plant_status = plant_status
        self.gets = []
        self.posts = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        if "files.slack.com" in url:
            return FakeResponse(status_code=self.download_status)
        if "/rest/v1/plant_observations" in url:
            return FakeResponse(payload=self.plant_rows)
        if "/rest/v1/care_logs" in url:
            return FakeResponse(payload=self.care_rows)
        return FakeResponse(payload=[])

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(status_code=self.plant_status, text="insert failed")


def config():
    return ObservationConfig(
        supabase_url="https://example.supabase.co",
        supabase_key="anon-key",
        slack_bot_token="xoxb-token",
        signing_secret="secret",
        observation_channel_id="C_OBSERVE",
        ai_vision_provider="gemini",
        gemini_api_key="gemini-key",
        gemini_vision_model="gemini-3.5-flash",
    )


def care_row(
    *,
    care_id="care-1",
    created_at="2026-06-17T06:16:00Z",
    slack_ts="1781622600.000000",
    file_id="F123",
    with_ai=False,
):
    note = "\n".join(
        [
            "Slackに植物観察写真が投稿されました。",
            "observed_at=2026-06-17 15:16:00 JST",
            "device_id=raspberrypi2",
            "location_id=location-b",
            f"slack_ts={slack_ts}",
            f"slack_file_id={file_id}",
            "slack_file_name=basil.png",
            "slack_file_mimetype=image/png",
            f"slack_file_url=https://files.slack.com/files-pri/T/{file_id}/basil.png",
            "nearest_sensor_log_time=2026-06-17T06:15:00+00:00",
            "nearest_vitality_score=100",
            "nearest_float_switch_state=water_ok",
            "nearest_solution_temperature=25.0",
            "nearest_light_lux=300.0",
        ]
    )
    if with_ai:
        note += '\nai_observation_json={"growth_stage":"cotyledon"}'
    else:
        note += "\nai_observation_error=RuntimeError: vision unavailable"
    return {
        "id": care_id,
        "created_at": created_at,
        "note": note,
        "sensor_log_id": 10,
        "message": "Slack写真投稿による観察記録",
    }


def ai_observation():
    return {
        "growth_stage": "true_leaf_1",
        "true_leaf_detected": True,
        "true_leaf_pair_count": 1,
        "cotyledon_visible": True,
        "plant_count_estimate": 8,
        "crowding": "medium",
        "leaf_color": "green",
        "leaf_size": "small",
        "wilting": False,
        "yellowing": False,
        "root_visibility": False,
        "root_length_estimate": None,
        "confidence": 0.85,
        "summary": "true leaves visible",
        "next_action": "continue observation",
    }


class BackfillAIObservationsTest(unittest.TestCase):
    def test_metadata_parsing(self):
        metadata = parse_note_metadata(care_row()["note"])

        self.assertEqual(metadata["slack_file_id"], "F123")
        self.assertEqual(metadata["nearest_light_lux"], "300.0")

    def test_chronological_ordering_and_limit(self):
        rows = [
            care_row(care_id="new", created_at="2026-07-01T00:00:00Z", slack_ts="2"),
            care_row(care_id="old", created_at="2026-06-01T00:00:00Z", slack_ts="1"),
        ]
        http = FakeHttp(care_rows=rows)

        candidates = load_backfill_candidates(config(), http_client=http, limit=1)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].care_log_id, "old")

    def test_targeted_slack_file_id_filtering(self):
        rows = [
            care_row(care_id="first", file_id="F_FIRST"),
            care_row(care_id="target", file_id="F_TARGET"),
        ]
        http = FakeHttp(care_rows=rows)

        candidates = load_backfill_candidates(
            config(), http_client=http, slack_file_id="F_TARGET"
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].care_log_id, "target")

    def test_dry_run_does_not_call_external_services(self):
        http = FakeHttp(care_rows=[care_row()])

        stats = run_backfill(config=config(), dry_run=True, http_client=http)

        self.assertEqual(stats.candidates_found, 1)
        self.assertEqual(stats.plan[0]["action"], "process")
        self.assertEqual([url for url, _ in http.gets if "files.slack.com" in url], [])
        self.assertEqual(http.posts, [])

    def test_duplicate_slack_file_id_skip(self):
        http = FakeHttp(
            care_rows=[care_row()],
            plant_rows=[{"raw_ai_json": {"slack_file_id": "F123"}}],
        )

        stats = run_backfill(config=config(), dry_run=True, http_client=http)

        self.assertEqual(stats.plan[0]["action"], "skip")
        self.assertEqual(stats.plan[0]["reason"], "duplicate_slack_file_id")
        self.assertEqual(stats.skipped_duplicate_file_id, 1)

    def test_targeted_already_processed_target_skips_safely(self):
        http = FakeHttp(
            care_rows=[care_row(file_id="F_TARGET")],
            plant_rows=[{"raw_ai_json": {"slack_file_id": "F_TARGET"}}],
        )

        stats = run_backfill(
            config=config(),
            dry_run=False,
            slack_file_id="F_TARGET",
            http_client=http,
        )

        self.assertEqual(stats.candidates_found, 1)
        self.assertEqual(stats.skipped_duplicate_file_id, 1)
        self.assertEqual(
            [url for url, _ in http.gets if "files.slack.com" in url],
            [],
        )
        self.assertEqual(http.posts, [])

    def test_duplicate_slack_ts_in_same_dry_run_is_skipped(self):
        http = FakeHttp(
            care_rows=[
                care_row(care_id="first", slack_ts="1781622600.000000", file_id="F1"),
                care_row(care_id="retry", slack_ts="1781622600.000000", file_id="F2"),
            ]
        )

        stats = run_backfill(config=config(), dry_run=True, http_client=http)

        self.assertEqual(stats.plan[0]["action"], "process")
        self.assertEqual(stats.plan[1]["action"], "skip")
        self.assertEqual(stats.plan[1]["reason"], "duplicate_slack_ts")
        self.assertEqual(stats.skipped_existing, 1)

    def test_duplicate_image_sha256_skip(self):
        image_sha256 = hashlib.sha256(b"historical-image").hexdigest()
        http = FakeHttp(
            care_rows=[care_row(file_id="F_NEW")],
            plant_rows=[{"raw_ai_json": {"slack_file_id": "F_OLD", "image_sha256": image_sha256}}],
        )

        with patch(
            "backfill_ai_observations.analyze_observation",
            return_value=ai_observation(),
        ):
            stats = run_backfill(config=config(), dry_run=False, http_client=http)

        self.assertEqual(stats.skipped_duplicate_sha256, 1)
        self.assertEqual(http.posts, [])

    def test_ai_failure_handling(self):
        http = FakeHttp(care_rows=[care_row()])

        with patch(
            "backfill_ai_observations.analyze_observation",
            side_effect=RuntimeError("ai failed"),
        ):
            stats = run_backfill(config=config(), dry_run=False, http_client=http)

        self.assertEqual(stats.failed_ai, 1)
        self.assertEqual(http.posts, [])

    def test_targeted_gemini_failure_does_not_insert(self):
        http = FakeHttp(care_rows=[care_row(file_id="F_TARGET")])

        with patch(
            "backfill_ai_observations.analyze_observation",
            side_effect=RuntimeError("gemini high demand"),
        ):
            stats = run_backfill(
                config=config(),
                dry_run=False,
                slack_file_id="F_TARGET",
                http_client=http,
            )

        self.assertEqual(stats.candidates_found, 1)
        self.assertEqual(stats.failed_ai, 1)
        self.assertEqual(http.posts, [])

    def test_successful_insert_payload(self):
        http = FakeHttp(care_rows=[care_row()])

        with patch(
            "backfill_ai_observations.analyze_observation",
            return_value=ai_observation(),
        ):
            stats = run_backfill(config=config(), dry_run=False, http_client=http)

        self.assertEqual(stats.processed_success, 1)
        self.assertEqual(len(http.posts), 1)
        payload = http.posts[0][1]["json"]
        self.assertEqual(payload["growth_stage"], "true_leaf_1")
        self.assertTrue(payload["raw_ai_json"]["backfilled"])
        self.assertEqual(payload["raw_ai_json"]["provider"], "gemini")
        self.assertEqual(payload["raw_ai_json"]["slack_file_id"], "F123")
        self.assertEqual(
            payload["raw_ai_json"]["image_sha256"],
            hashlib.sha256(b"historical-image").hexdigest(),
        )

    def test_targeted_success_inserts_one_row_without_slack_reply(self):
        http = FakeHttp(
            care_rows=[
                care_row(care_id="other", file_id="F_OTHER"),
                care_row(care_id="target", file_id="F_TARGET"),
            ]
        )

        with patch(
            "backfill_ai_observations.analyze_observation",
            return_value=ai_observation(),
        ):
            stats = run_backfill(
                config=config(),
                dry_run=False,
                slack_file_id="F_TARGET",
                http_client=http,
            )

        self.assertEqual(stats.candidates_found, 1)
        self.assertEqual(stats.processed_success, 1)
        self.assertEqual(len(http.posts), 1)
        self.assertTrue(http.posts[0][0].endswith("/rest/v1/plant_observations"))
        payload = http.posts[0][1]["json"]
        self.assertEqual(payload["raw_ai_json"]["slack_file_id"], "F_TARGET")
        self.assertNotIn("chat.postMessage", http.posts[0][0])

    def test_build_payload_sets_backfilled_true(self):
        candidate = load_backfill_candidates(
            config(), http_client=FakeHttp(care_rows=[care_row()])
        )[0]

        payload = build_backfill_payload(
            candidate=candidate,
            config=config(),
            ai_observation=ai_observation(),
            image_identity=ImageIdentity(
                sha256="abc123", byte_size=10, mime_type="image/png"
            ),
        )

        self.assertTrue(payload["raw_ai_json"]["backfilled"])


if __name__ == "__main__":
    unittest.main()
