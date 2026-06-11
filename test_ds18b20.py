import unittest
from pathlib import Path
from unittest.mock import Mock

from ds18b20 import find_sensor_file, parse_w1_slave_text, read_temperature


VALID_READING = """\
9e 01 4b 46 7f ff 02 10 56 : crc=56 YES
9e 01 4b 46 7f ff 02 10 56 t=25875
"""


class Ds18b20Test(unittest.TestCase):
    def test_parse_valid_reading(self):
        self.assertEqual(parse_w1_slave_text(VALID_READING), 25.875)

    def test_rejects_failed_crc(self):
        with self.assertRaises(ValueError):
            parse_w1_slave_text(VALID_READING.replace("YES", "NO"))

    def test_find_and_read_first_sensor(self):
        sensor_file = Mock(spec=Path)
        sensor_file.is_file.return_value = True
        sensor_file.read_text.return_value = VALID_READING
        devices_root = Mock(spec=Path)
        devices_root.glob.return_value = [sensor_file]

        self.assertEqual(find_sensor_file(devices_root), sensor_file)
        self.assertEqual(read_temperature(devices_root), 25.875)


if __name__ == "__main__":
    unittest.main()
