import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.reconstruct_historical_sensor_data import export


class HistoricalReconstructionTest(unittest.TestCase):
    def test_offsets_are_reversed_without_changing_original_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            db_path = root / "data.db"
            output_path = root / "reconstructed.csv"
            with sqlite3.connect(db_path) as connection:
                connection.execute(
                    """
                    CREATE TABLE sensor_logs (
                        id INTEGER PRIMARY KEY,
                        temperature REAL,
                        humidity REAL,
                        created_at TEXT
                    )
                    """
                )
                connection.executemany(
                    "INSERT INTO sensor_logs VALUES (?, ?, ?, ?)",
                    [
                        (1, 39.0, 30.0, "2026-05-12 03:00:00"),
                        (2, 32.0, 25.0, "2026-05-18 00:30:00"),
                        (3, 25.0, 50.0, "2026-05-18 00:35:00"),
                        (4, 22.0, 52.0, "2026-05-22 00:00:00"),
                        (5, 26.0, 60.0, "2026-06-02 00:00:00"),
                    ],
                )

            metadata = export(db_path, output_path)

            with output_path.open(encoding="utf-8", newline="") as source:
                rows = list(csv.DictReader(source))

            self.assertEqual(metadata["row_count"], 5)
            self.assertEqual(rows[0]["temperature"], "39.0")
            self.assertEqual(
                rows[0]["reconstructed_sensor_temperature"], "39.0"
            )
            self.assertEqual(
                rows[1]["reconstructed_sensor_temperature"], "40.0"
            )
            self.assertEqual(
                rows[2]["reconstructed_sensor_temperature"], "33.0"
            )
            self.assertEqual(
                rows[2]["reconstructed_sensor_humidity"], "35.0"
            )
            self.assertEqual(
                rows[3]["reconstructed_sensor_temperature"], "37.0"
            )
            self.assertEqual(
                rows[3]["reconstructed_sensor_humidity"], "37.0"
            )
            self.assertEqual(rows[4]["measurement_system"], "dht11")
            self.assertEqual(
                rows[4]["reconstructed_sensor_temperature"], "26.0"
            )
            self.assertTrue(
                output_path.with_suffix(".csv.metadata.json").is_file()
            )


if __name__ == "__main__":
    unittest.main()
