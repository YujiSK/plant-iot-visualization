import unittest
from datetime import datetime

from vitality import (
    calculate_basil_vitality,
    calculate_vitality,
    generate_message,
    is_core_daylight,
    score_humidity,
    score_light_lux,
    score_solution_temperature,
    score_temp,
)


class VitalityTest(unittest.TestCase):
    def test_score_temp_ranges(self):
        self.assertEqual(score_temp(26), 100)
        self.assertEqual(score_temp(20), 70)
        self.assertEqual(score_temp(31), 40)

    def test_score_humidity_ranges(self):
        self.assertEqual(score_humidity(50), 100)
        self.assertEqual(score_humidity(35), 70)
        self.assertEqual(score_humidity(80), 40)

    def test_calculate_vitality_weights_temperature_and_humidity(self):
        self.assertEqual(calculate_vitality(26, 50), 100)
        self.assertEqual(calculate_vitality(31, 50), 64)
        self.assertEqual(calculate_vitality(26, 30), 76)

    def test_generate_message_priorities(self):
        self.assertEqual(generate_message(26, 30), "乾燥しています")
        self.assertEqual(generate_message(31, 50), "温度が高めです")
        self.assertEqual(generate_message(26, 50), "安定しています")

    def test_solution_temperature_ranges(self):
        self.assertEqual(score_solution_temperature(24), 100)
        self.assertEqual(score_solution_temperature(28), 80)
        self.assertEqual(score_solution_temperature(31), 25)
        self.assertEqual(score_solution_temperature(8), 10)

    def test_light_is_only_evaluated_during_core_daylight(self):
        self.assertFalse(is_core_daylight(datetime(2026, 6, 13, 7, 0)))
        self.assertTrue(is_core_daylight(datetime(2026, 6, 13, 12, 0)))
        self.assertEqual(score_light_lux(10000), 100)
        self.assertEqual(score_light_lux(1000), 35)

    def test_low_water_cannot_be_hidden_by_good_other_values(self):
        score, message = calculate_basil_vitality(
            solution_temperature=24,
            light_lux=20000,
            float_switch_triggered=True,
            observed_at=datetime(2026, 6, 13, 12, 0),
        )
        self.assertLessEqual(score, 25)
        self.assertIn("水位低下", message)

    def test_nighttime_darkness_does_not_reduce_vitality(self):
        score, message = calculate_basil_vitality(
            solution_temperature=24,
            light_lux=0,
            float_switch_triggered=False,
            observed_at=datetime(2026, 6, 13, 2, 0),
        )
        self.assertEqual((score, message), (100, "安定しています"))

    def test_hot_solution_and_low_water_are_compound_stress(self):
        score, message = calculate_basil_vitality(
            solution_temperature=31,
            light_lux=20000,
            float_switch_triggered=True,
            observed_at=datetime(2026, 6, 13, 12, 0),
        )
        self.assertLessEqual(score, 15)
        self.assertIn("複合ストレス", message)


if __name__ == "__main__":
    unittest.main()
