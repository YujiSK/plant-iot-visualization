"""Read a DS18B20 temperature sensor through the Linux 1-Wire sysfs."""

from pathlib import Path
from typing import Optional


DEFAULT_DEVICES_ROOT = Path("/sys/bus/w1/devices")


def parse_w1_slave_text(text: str) -> float:
    lines = text.strip().splitlines()
    if len(lines) < 2 or not lines[0].strip().endswith("YES"):
        raise ValueError("DS18B20 CRC check failed")

    marker = "t="
    marker_index = lines[1].find(marker)
    if marker_index < 0:
        raise ValueError("DS18B20 temperature value was not found")

    milli_celsius = int(lines[1][marker_index + len(marker) :])
    return round(milli_celsius / 1000.0, 3)


def find_sensor_file(
    devices_root: Path = DEFAULT_DEVICES_ROOT,
    sensor_id: Optional[str] = None,
) -> Path:
    if sensor_id:
        candidates = [devices_root / sensor_id / "w1_slave"]
    else:
        candidates = sorted(devices_root.glob("28-*/w1_slave"))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    target = sensor_id or "28-*"
    raise FileNotFoundError(f"DS18B20 sensor {target} was not found under {devices_root}")


def read_temperature(
    devices_root: Path = DEFAULT_DEVICES_ROOT,
    sensor_id: Optional[str] = None,
) -> float:
    sensor_file = find_sensor_file(devices_root, sensor_id)
    return parse_w1_slave_text(sensor_file.read_text(encoding="ascii"))
