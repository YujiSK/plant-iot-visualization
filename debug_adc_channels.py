#!/usr/bin/env python3
"""Debug MCP3204/MCP3208 ADC readings on Raspberry Pi SPI.

Safety notes:
- Use 3.3V for MCP3204/MCP3208 VDD/VREF and sensor VCC while debugging.
- Do not feed 5V into Raspberry Pi GPIO or MCP ADC inputs used with 3.3V VREF.
- If trying a 5V-powered sensor, measure SIG with a tester first and connect it
  to the ADC only after confirming the signal is 3.3V or lower.
"""

import argparse
import glob
import time

import spidev

VREF = 3.3
ADC_MAX = 4095

CHANNEL_LABELS = {
    0: "water",
    1: "light",
}


def read_mcp320x(spi, channel):
    """Read one single-ended channel from MCP3204/MCP3208 as a 12-bit raw value."""
    if not 0 <= channel <= 7:
        raise ValueError("channel must be between 0 and 7")

    # MCP3208 command: start bit, single-ended bit, then channel bits D2 D1 D0.
    # For MCP3204, use channels 0-3; the same framing works for those channels.
    response = spi.xfer2(
        [
            0x06 | ((channel & 0x04) >> 2),
            (channel & 0x03) << 6,
            0x00,
        ]
    )
    return ((response[1] & 0x0F) << 8) | response[2]


def voltage_from_raw(raw, vref):
    return raw * vref / ADC_MAX


def format_channel(channel, raw, previous_raw, vref):
    label = CHANNEL_LABELS.get(channel, f"ch{channel}")
    voltage = voltage_from_raw(raw, vref)
    delta = 0 if previous_raw is None else raw - previous_raw
    return f"CH{channel} {label} raw={raw:4d} voltage={voltage:.3f}V diff={delta:+5d}"


def parse_args():
    parser = argparse.ArgumentParser(
        description="Continuously print MCP3204/MCP3208 ADC raw and voltage values."
    )
    parser.add_argument("--bus", type=int, default=0, help="SPI bus number, default: 0")
    parser.add_argument(
        "--device", type=int, default=0, help="SPI chip select device, default: 0"
    )
    parser.add_argument(
        "--channels",
        type=int,
        default=4,
        choices=range(1, 9),
        metavar="1-8",
        help="number of channels to read. Use 4 for MCP3204, 8 for MCP3208.",
    )
    parser.add_argument(
        "--vref",
        type=float,
        default=VREF,
        help="ADC reference voltage. Default: 3.3",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="seconds between readings. Default: 1.0",
    )
    parser.add_argument(
        "--max-speed-hz",
        type=int,
        default=1_000_000,
        help="SPI max speed in Hz. Default: 1000000",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    devices = sorted(glob.glob("/dev/spidev*"))

    print("MCP3204/MCP3208 ADC debug")
    print(f"SPI device files: {', '.join(devices) if devices else 'not found'}")
    print(f"Opening SPI bus={args.bus}, device={args.device}")
    print("If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI")
    print("CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage")
    print("CH1 light: cover by hand / shine phone light should change raw/voltage")
    print()

    spi = spidev.SpiDev()
    previous = {}

    try:
        spi.open(args.bus, args.device)
        spi.max_speed_hz = args.max_speed_hz
        spi.mode = 0

        while True:
            parts = []
            for channel in range(args.channels):
                raw = read_mcp320x(spi, channel)
                parts.append(format_channel(channel, raw, previous.get(channel), args.vref))
                previous[channel] = raw
            print(" | ".join(parts), flush=True)
            time.sleep(args.interval)
    except FileNotFoundError:
        print("ERROR: SPI device was not found. SPI may be disabled.")
        print("Enable SPI: sudo raspi-config -> Interface Options -> SPI -> Enable")
    except PermissionError:
        print("ERROR: Permission denied opening SPI device.")
        print("Try running with sudo or add the user to the spi group.")
    except KeyboardInterrupt:
        print("\nStopped by Ctrl+C")
    finally:
        try:
            spi.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
