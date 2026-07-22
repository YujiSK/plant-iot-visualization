import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from supabase_health_check import check_device_heartbeat, check_system_health, health_check, run_monitoring_cycle


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

    def test_heartbeat_thresholds(self):
        now = datetime.now(timezone.utc)
        recent_ts = (now - timedelta(minutes=5)).isoformat()
        old_ts = (now - timedelta(minutes=45)).isoformat()
        critical_ts = (now - timedelta(minutes=90)).isoformat()

        with patch.dict(
            "os.environ",
            {
                "SUPABASE_URL": "https://example.supabase.co",
                "SUPABASE_KEY": "sb_publishable_secretvalue",
            },
            clear=False,
        ):
            # 5 mins -> OK
            http1 = FakeHttp(FakeResponse(payload=[{"id": 1, "created_at": recent_ts}]))
            hb1 = check_device_heartbeat("raspberrypi2", http_client=http1)
            self.assertEqual(hb1["status"], "OK")

            # 45 mins -> WARNING
            http2 = FakeHttp(FakeResponse(payload=[{"id": 2, "created_at": old_ts}]))
            hb2 = check_device_heartbeat("raspberrypi2", http_client=http2)
            self.assertEqual(hb2["status"], "WARNING")

            # 90 mins -> CRITICAL
            http3 = FakeHttp(FakeResponse(payload=[{"id": 3, "created_at": critical_ts}]))
            hb3 = check_device_heartbeat("raspberrypi2", http_client=http3)
            self.assertEqual(hb3["status"], "CRITICAL")

    def test_system_health(self):
        health = check_system_health()
        self.assertIn("disk_percent", health)
        self.assertIn("service_name", health)
        self.assertIn("status", health)


if __name__ == "__main__":
    unittest.main()
