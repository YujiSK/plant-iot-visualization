#!/usr/bin/env python3
"""Debug a DS18B20 solution temperature sensor through Linux 1-Wire."""

import argparse
import time

from ds18b20 import find_sensor_file, read_temperature


def parse_args():
    parser = argparse.ArgumentParser(description="Read a DS18B20 sensor.")
    parser.add_argument(
        "--sensor-id",
        help="1-Wire sensor ID such as 28-000000000001. Defaults to the first sensor.",
    )
    parser.add_argument("--count", type=int, default=5, help="Number of readings.")
    parser.add_argument("--interval", type=float, default=2.0, help="Seconds between readings.")
    return parser.parse_args()


def main():
    args = parse_args()
    sensor_file = find_sensor_file(sensor_id=args.sensor_id)
    print(f"DS18B20 file: {sensor_file}", flush=True)

    for attempt in range(1, max(1, args.count) + 1):
        try:
            temperature = read_temperature(sensor_id=args.sensor_id)
            print(
                f"attempt={attempt} solution_temperature={temperature:.3f}C",
                flush=True,
            )
        except (OSError, ValueError) as exc:
            print(f"attempt={attempt} ERROR: {exc}", flush=True)
        if attempt < args.count:
            time.sleep(max(0.0, args.interval))


if __name__ == "__main__":
    main()
