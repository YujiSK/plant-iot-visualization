import unittest
from unittest.mock import patch

from supabase_health_check import health_check


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="OK"):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
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
        self.gets = []

    def get(self, url, **kwargs):
        self.gets.append((url, kwargs))
        return self.response


class SupabaseHealthCheckTest(unittest.TestCase):
    def test_health_check_uses_publishable_key_without_logging_secret(self):
        http = FakeHttp(
            FakeResponse(payload=[{"id": 123, "created_at": "2026-07-11T00:00:00Z"}])
        )

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_publishable_secretvalue",
            },
            clear=False,
        ):
            result = health_check(http_client=http)

        self.assertTrue(result["ok"])
        self.assertEqual(result["latest_sensor_log"]["id"], 123)
        self.assertEqual(len(http.gets), 1)
        headers = http.gets[0][1]["headers"]
        self.assertEqual(headers["apikey"], "sb_publishable_secretvalue")
        self.assertNotIn("secretvalue", result["key"])

    def test_health_check_raises_when_supabase_rejects_request(self):
        http = FakeHttp(FakeResponse(status_code=401, text="invalid key"))

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_publishable_secretvalue",
            },
            clear=False,
        ):
            with self.assertRaises(RuntimeError):
                health_check(http_client=http)


if __name__ == "__main__":
    unittest.main()
