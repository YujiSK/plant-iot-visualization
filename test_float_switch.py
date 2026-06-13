import unittest

from float_switch import majority_triggered
from send_sensor_raspberrypi2 import (
    calculate_remote_status,
    read_optional,
    read_with_retries,
)


class FloatSwitchTest(unittest.TestCase):
    def test_majority_triggered(self):
        self.assertTrue(majority_triggered([True, True, False]))

    def test_majority_not_triggered(self):
        self.assertFalse(majority_triggered([False, False, True]))

    def test_rejects_empty_samples(self):
        with self.assertRaises(ValueError):
            majority_triggered([])

    def test_remote_status_reports_low_water(self):
        score, message = calculate_remote_status(24.0, "bright", True)
        self.assertLessEqual(score, 25)
        self.assertIn("水位低下", message)

    def test_remote_status_is_stable(self):
        self.assertEqual(
            calculate_remote_status(24.0, "bright", False),
            (100, "安定しています"),
        )

    def test_optional_sensor_failure_returns_none(self):
        def fail():
            raise OSError("not connected")

        self.assertIsNone(read_optional("test", fail))

    def test_retry_recovers(self):
        values = iter([OSError("crc"), 26.5])

        def sometimes_fails():
            value = next(values)
            if isinstance(value, Exception):
                raise value
            return value

        self.assertEqual(
            read_with_retries("test", sometimes_fails, interval_seconds=0),
            26.5,
        )


if __name__ == "__main__":
    unittest.main()
