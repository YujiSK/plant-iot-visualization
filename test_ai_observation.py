import unittest

from ai_observation import (
    GEMINI_INTERACTIONS_URL,
    OPENAI_RESPONSES_URL,
    analyze_observation,
    build_gemini_observation_payload,
    build_openai_observation_payload,
    compare_observations,
    extract_ai_observation_from_note,
    format_comparison_for_slack,
    format_observation_for_slack,
    parse_openai_observation_response,
)


OBSERVATION_JSON = {
    "growth_stage": "true_leaf_1",
    "true_leaf_detected": True,
    "true_leaf_pair_count": 1,
    "cotyledon_visible": True,
    "plant_count_estimate": 18,
    "crowding": "medium",
    "leaf_color": "green",
    "leaf_size": "small",
    "wilting": False,
    "yellowing": False,
    "root_visibility": False,
    "root_length_estimate": None,
    "confidence": 0.8,
    "summary": "本葉が見えます",
    "next_action": "本葉対数を確認",
}


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
    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return self.response


class AiObservationTest(unittest.TestCase):
    def test_analyze_observation_returns_rule_based_json(self):
        result = analyze_observation(
            image_url="https://example.com/basil.jpg",
            nearest_sensor_log={
                "float_switch_state": "water_ok",
                "light_lux": 1200,
            },
            device_id="raspberrypi2",
            location_id="location-b",
            openai_api_key="",
            gemini_api_key="",
        )

        self.assertEqual(result["growth_stage"], "cotyledon")
        self.assertFalse(result["true_leaf_detected"])
        self.assertEqual(result["true_leaf_pair_count"], 0)
        self.assertTrue(result["cotyledon_visible"])
        self.assertEqual(result["plant_count_estimate"], 20)
        self.assertFalse(result["yellowing"])
        self.assertFalse(result["wilting"])
        self.assertEqual(result["crowding"], "medium")
        self.assertEqual(result["leaf_color"], "green")
        self.assertEqual(result["leaf_size"], "small")
        self.assertFalse(result["root_visibility"])
        self.assertGreater(result["confidence"], 0)

    def test_low_water_changes_next_action(self):
        result = analyze_observation(
            nearest_sensor_log={
                "float_switch_state": "low_water",
                "light_lux": 1200,
            }
        )

        self.assertIn("水位", result["next_action"])

    def test_slack_format_is_observation_support_not_diagnosis(self):
        text = format_observation_for_slack(
            {
                "growth_stage": "cotyledon",
                "true_leaf_detected": False,
                "true_leaf_pair_count": 0,
                "cotyledon_visible": True,
                "plant_count_estimate": 20,
                "yellowing": False,
                "wilting": False,
                "crowding": "medium",
                "leaf_color": "green",
                "leaf_size": "small",
                "root_visibility": False,
                "confidence": 0.55,
                "summary": "子葉が見えます",
                "next_action": "本葉の出現を確認してください",
            }
        )

        self.assertIn("AI観察支援", text)
        self.assertIn("生育段階: 子葉期", text)
        self.assertIn("本葉検出: なし", text)
        self.assertIn("推定株数: 約20", text)
        self.assertNotIn("診断", text)

    def test_openai_payload_uses_responses_vision_and_json_schema(self):
        payload = build_openai_observation_payload(
            image_url="data:image/jpeg;base64,ZmFrZQ==",
            nearest_sensor_log={"float_switch_state": "water_ok"},
            device_id="raspberrypi2",
            location_id="location-b",
            observed_at=None,
            model="gpt-4.1",
        )

        self.assertEqual(payload["model"], "gpt-4.1")
        content = payload["input"][0]["content"]
        self.assertEqual(content[1]["type"], "input_image")
        self.assertEqual(content[1]["image_url"], "data:image/jpeg;base64,ZmFrZQ==")
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")
        self.assertIn("growth_stage", payload["text"]["format"]["schema"]["properties"])

    def test_parse_openai_observation_response_output_text(self):
        parsed = parse_openai_observation_response(
            {"output_text": __import__("json").dumps(OBSERVATION_JSON)}
        )

        self.assertEqual(parsed["growth_stage"], "true_leaf_1")
        self.assertTrue(parsed["true_leaf_detected"])

    def test_openai_provider_success(self):
        http = FakeHttp(FakeResponse(payload={"output_text": __import__("json").dumps(OBSERVATION_JSON)}))

        result = analyze_observation(
            image_bytes=b"fake-image",
            image_mimetype="image/jpeg",
            ai_vision_provider="openai",
            openai_api_key="openai-key",
            openai_model="gpt-4.1",
            http_client=http,
        )

        self.assertEqual(http.posts[0][0], OPENAI_RESPONSES_URL)
        self.assertEqual(result["growth_stage"], "true_leaf_1")
        self.assertTrue(result["true_leaf_detected"])

    def test_openai_429_failure(self):
        http = FakeHttp(FakeResponse(status_code=429, payload={}, text="rate limited"))

        with self.assertRaises(RuntimeError):
            analyze_observation(
                image_bytes=b"fake-image",
                ai_vision_provider="openai",
                openai_api_key="openai-key",
                http_client=http,
            )

    def test_gemini_payload_uses_inline_image_and_schema(self):
        payload = build_gemini_observation_payload(
            image_bytes=b"fake-image",
            image_mimetype="image/jpeg",
            nearest_sensor_log={"float_switch_state": "water_ok"},
            device_id="raspberrypi2",
            location_id="location-b",
            observed_at=None,
            model="gemini-3.5-flash",
        )

        self.assertEqual(payload["model"], "gemini-3.5-flash")
        self.assertEqual(payload["input"][1]["type"], "image")
        self.assertEqual(payload["response_format"]["mime_type"], "application/json")

    def test_gemini_provider_success(self):
        http = FakeHttp(FakeResponse(payload={"output_text": __import__("json").dumps(OBSERVATION_JSON)}))

        result = analyze_observation(
            image_bytes=b"fake-image",
            image_mimetype="image/jpeg",
            ai_vision_provider="gemini",
            gemini_api_key="gemini-key",
            gemini_model="gemini-3.5-flash",
            http_client=http,
        )

        self.assertEqual(http.posts[0][0], GEMINI_INTERACTIONS_URL)
        self.assertEqual(result["growth_stage"], "true_leaf_1")
        self.assertEqual(result["true_leaf_pair_count"], 1)

    def test_gemini_api_failure(self):
        http = FakeHttp(FakeResponse(status_code=500, payload={}, text="gemini error"))

        with self.assertRaises(RuntimeError):
            analyze_observation(
                image_bytes=b"fake-image",
                ai_vision_provider="gemini",
                gemini_api_key="gemini-key",
                http_client=http,
            )

    def test_invalid_provider_setting(self):
        with self.assertRaises(ValueError):
            analyze_observation(
                image_bytes=b"fake-image",
                ai_vision_provider="unknown",
            )

    def test_extract_ai_observation_from_note(self):
        note = (
            "observed_at=2026-06-17 15:16:00 JST\n"
            'ai_observation_json={"growth_stage":"cotyledon","crowding":"medium"}'
        )

        result = extract_ai_observation_from_note(note)

        self.assertEqual(result["growth_stage"], "cotyledon")
        self.assertEqual(result["crowding"], "medium")

    def test_broken_ai_json_returns_none(self):
        result = extract_ai_observation_from_note("ai_observation_json={broken")

        self.assertIsNone(result)

    def test_compare_without_previous(self):
        result = compare_observations(
            {"growth_stage": "cotyledon", "plant_count_estimate": 20},
            None,
            None,
        )

        self.assertFalse(result["has_previous"])
        self.assertIn("前回観察記録", result["summary"])

    def test_compare_with_previous(self):
        result = compare_observations(
            {
                "growth_stage": "cotyledon",
                "true_leaf_pair_count": 0,
                "plant_count_estimate": 20,
                "crowding": "medium",
                "next_action": "本葉の出現を確認してください",
            },
            {
                "growth_stage": "cotyledon",
                "true_leaf_pair_count": 0,
                "plant_count_estimate": 20,
                "crowding": "medium",
            },
            "2026-06-17 15:16:00 JST",
        )

        self.assertTrue(result["has_previous"])
        self.assertEqual(result["growth_stage_change"], "cotyledon -> cotyledon")
        self.assertEqual(result["plant_count_change"], "20 -> 20")
        self.assertEqual(result["crowding_change"], "medium -> medium")

    def test_compare_growth_stage_change(self):
        result = compare_observations(
            {"growth_stage": "true_leaf_1", "plant_count_estimate": 20},
            {"growth_stage": "cotyledon", "plant_count_estimate": 20},
        )

        self.assertEqual(result["growth_stage_change"], "cotyledon -> true_leaf_1")
        self.assertIn("生育段階", result["summary"])

    def test_compare_plant_count_change(self):
        result = compare_observations(
            {"growth_stage": "cotyledon", "plant_count_estimate": 22},
            {"growth_stage": "cotyledon", "plant_count_estimate": 20},
        )

        self.assertEqual(result["plant_count_change"], "20 -> 22")
        self.assertIn("推定株数", result["summary"])

    def test_compare_crowding_change(self):
        result = compare_observations(
            {
                "growth_stage": "cotyledon",
                "true_leaf_pair_count": 0,
                "plant_count_estimate": 20,
                "crowding": "high",
            },
            {
                "growth_stage": "cotyledon",
                "true_leaf_pair_count": 0,
                "plant_count_estimate": 20,
                "crowding": "medium",
            },
        )

        self.assertEqual(result["crowding_change"], "medium -> high")
        self.assertIn("密集度", result["summary"])

    def test_format_comparison_for_slack(self):
        text = format_comparison_for_slack(
            {
                "has_previous": True,
                "previous_observed_at": "2026-06-17 15:16:00 JST",
                "growth_stage_change": "cotyledon -> cotyledon",
                "true_leaf_pair_count_change": "0 -> 0",
                "plant_count_change": "20 -> 20",
                "crowding_change": "medium -> medium",
                "summary": "本葉の出現を確認してください",
            }
        )

        self.assertIn("前回との比較", text)
        self.assertIn("子葉期 → 子葉期", text)
        self.assertIn("約20 → 約20", text)


if __name__ == "__main__":
    unittest.main()
