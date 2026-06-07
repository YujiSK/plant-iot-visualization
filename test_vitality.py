import unittest

from vitality import calculate_vitality, generate_message, score_humidity, score_temp


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


if __name__ == "__main__":
    unittest.main()
