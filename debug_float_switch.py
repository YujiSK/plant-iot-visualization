#!/usr/bin/env python3
"""Print the current active-low float switch state."""

import argparse

from float_switch import read_triggered


def main():
    parser = argparse.ArgumentParser(description="Read an active-low float switch.")
    parser.add_argument("--gpio", type=int, default=17, help="BCM GPIO. Default: 17")
    args = parser.parse_args()

    triggered = read_triggered(gpio=args.gpio)
    print(
        f"GPIO{args.gpio}: triggered={triggered} "
        f"state={'low_water' if triggered else 'water_ok'}"
    )


if __name__ == "__main__":
    main()

