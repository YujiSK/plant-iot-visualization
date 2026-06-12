import unittest

from bh1750 import raw_bytes_to_lux


class Bh1750Test(unittest.TestCase):
    def test_converts_raw_bytes_to_lux(self):
        self.assertEqual(raw_bytes_to_lux([0x01, 0x20]), 240.0)

    def test_zero_lux(self):
        self.assertEqual(raw_bytes_to_lux([0x00, 0x00]), 0.0)

    def test_rejects_invalid_length(self):
        with self.assertRaises(ValueError):
            raw_bytes_to_lux([0x01])


if __name__ == "__main__":
    unittest.main()

