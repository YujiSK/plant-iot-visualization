#!/usr/bin/env python3
"""Unit tests for outbox.py using unittest."""

import tempfile
import unittest
from pathlib import Path

from outbox import count_pending, enqueue, flush_outbox, get_pending, init_outbox, mark_failed, mark_synced


class TestOutbox(unittest.TestCase):

    def test_enqueue_and_get_pending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_data.db"
            init_outbox(db_path)

            payload1 = {"device_id": "raspberrypi2", "temp": 25.0}
            payload2 = {"device_id": "raspberrypi2", "temp": 26.0}

            id1 = enqueue(payload1, db_path=db_path)
            id2 = enqueue(payload2, db_path=db_path)

            self.assertGreater(id1, 0)
            self.assertGreater(id2, id1)
            self.assertEqual(count_pending(db_path=db_path), 2)

            pending = get_pending(limit=10, db_path=db_path)
            self.assertEqual(len(pending), 2)
            self.assertEqual(pending[0]["payload"]["temp"], 25.0)
            self.assertEqual(pending[1]["payload"]["temp"], 26.0)

    def test_mark_synced_and_failed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_data.db"

            id1 = enqueue({"device_id": "raspberrypi2", "val": 1}, db_path=db_path)
            id2 = enqueue({"device_id": "raspberrypi2", "val": 2}, db_path=db_path)

            mark_synced(id1, db_path=db_path)
            self.assertEqual(count_pending(db_path=db_path), 1)

            mark_failed(id2, "connection error", db_path=db_path)
            pending = get_pending(limit=10, db_path=db_path)
            self.assertEqual(len(pending), 1)
            self.assertEqual(pending[0]["status"], "failed")
            self.assertEqual(pending[0]["retry_count"], 1)

    def test_flush_outbox(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test_data.db"

            enqueue({"device_id": "raspi", "num": 10}, db_path=db_path)
            enqueue({"device_id": "raspi", "num": 20}, db_path=db_path)

            sent_items = []

            def mock_send(payload):
                if payload["num"] == 10:
                    sent_items.append(payload)
                    return True
                raise RuntimeError("simulated error")

            synced, failed = flush_outbox(mock_send, db_path=db_path)
            self.assertEqual(synced, 1)
            self.assertEqual(failed, 1)
            self.assertEqual(len(sent_items), 1)
            self.assertEqual(count_pending(db_path=db_path), 1)


if __name__ == "__main__":
    unittest.main()
