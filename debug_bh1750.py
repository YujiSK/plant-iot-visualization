#!/usr/bin/env python3
"""Debug BH1750 illuminance readings through Raspberry Pi I2C."""

import argparse
import time

from bh1750 import read_lux


def parse_args():
    parser = argparse.ArgumentParser(description="Read a BH1750 light sensor.")
    parser.add_argument("--bus", type=int, default=1, help="I2C bus number. Default: 1")
    parser.add_argument(
        "--address",
        type=lambda value: int(value, 0),
        default=0x23,
        help="I2C address. Default: 0x23",
    )
    parser.add_argument("--count", type=int, default=5, help="Number of readings.")
    parser.add_argument("--interval", type=float, default=1.0, help="Seconds between readings.")
    return parser.parse_args()


def main():
    args = parse_args()
    print(f"BH1750 I2C bus={args.bus} address=0x{args.address:02x}", flush=True)

    for attempt in range(1, max(1, args.count) + 1):
        try:
            lux = read_lux(bus_number=args.bus, address=args.address)
            print(f"attempt={attempt} light={lux:.1f} lx", flush=True)
        except OSError as exc:
            print(f"attempt={attempt} ERROR: {exc}", flush=True)
        if attempt < args.count:
            time.sleep(max(0.0, args.interval))


if __name__ == "__main__":
    main()

