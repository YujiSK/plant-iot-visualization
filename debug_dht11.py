#!/usr/bin/env python3
"""Debug DHT11 temperature/humidity readings on Raspberry Pi GPIO17.

Wiring:
- DHT11 VCC -> 3.3V
- DHT11 GND -> GND
- DHT11 DATA -> GPIO17
- DHT11 DATA -> 10kohm -> 3.3V
"""

import argparse
import time

import adafruit_dht
import board

PIN_BY_BCM = {
    17: board.D17,
}


def parse_args():
    parser = argparse.ArgumentParser(description="Read DHT11 from Raspberry Pi GPIO.")
    parser.add_argument("--pin", type=int, default=17, help="BCM GPIO pin. Default: 17")
    parser.add_argument("--retries", type=int, default=10, help="read attempts. Default: 10")
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="seconds between attempts. DHT11 needs about 1s+. Default: 2.0",
    )
    return parser.parse_args()


def board_pin_from_bcm(pin):
    try:
        return PIN_BY_BCM[pin]
    except KeyError as exc:
        raise SystemExit(
            f"Unsupported BCM pin {pin}. Add it to PIN_BY_BCM in debug_dht11.py."
        ) from exc


def main():
    args = parse_args()
    dht = adafruit_dht.DHT11(board_pin_from_bcm(args.pin))

    print("DHT11 debug")
    print(f"DATA GPIO: BCM {args.pin}")
    print("Expected wiring: VCC=3.3V, GND=GND, DATA=GPIO17, DATA pull-up=10kohm to 3.3V")
    print()

    try:
        for attempt in range(1, args.retries + 1):
            try:
                temperature = dht.temperature
                humidity = dht.humidity
                print(
                    f"attempt={attempt} temperature={temperature:.1f}C "
                    f"humidity={humidity:.1f}%",
                    flush=True,
                )
            except RuntimeError as exc:
                print(f"attempt={attempt} RETRY: {exc}", flush=True)
            except Exception as exc:
                print(f"attempt={attempt} ERROR: {type(exc).__name__}: {exc}", flush=True)
                break
            time.sleep(args.interval)
    finally:
        dht.exit()


if __name__ == "__main__":
    main()
