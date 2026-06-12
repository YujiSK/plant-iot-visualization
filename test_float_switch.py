import unittest

from float_switch import majority_triggered
from send_sensor_raspberrypi2 import calculate_remote_status


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
        self.assertEqual(score, 40)
        self.assertIn("水位低下", message)

    def test_remote_status_is_stable(self):
        self.assertEqual(
            calculate_remote_status(24.0, "bright", False),
            (100, "安定しています"),
        )


if __name__ == "__main__":
    unittest.main()
