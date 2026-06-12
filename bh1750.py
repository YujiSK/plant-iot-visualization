"""Read a BH1750 ambient light sensor through Linux I2C."""

import time

DEFAULT_I2C_BUS = 1
DEFAULT_ADDRESS = 0x23
ONE_TIME_HIGH_RES_MODE = 0x20
DEFAULT_MEASUREMENT_SECONDS = 0.18


def raw_bytes_to_lux(data) -> float:
    values = list(data)
    if len(values) != 2:
        raise ValueError("BH1750 reading must contain exactly 2 bytes")

    raw = (values[0] << 8) | values[1]
    return round(raw / 1.2, 1)


def read_lux(
    bus_number: int = DEFAULT_I2C_BUS,
    address: int = DEFAULT_ADDRESS,
    measurement_seconds: float = DEFAULT_MEASUREMENT_SECONDS,
) -> float:
    from smbus2 import SMBus, i2c_msg

    with SMBus(bus_number) as bus:
        bus.write_byte(address, ONE_TIME_HIGH_RES_MODE)
        time.sleep(max(0.0, measurement_seconds))
        message = i2c_msg.read(address, 2)
        bus.i2c_rdwr(message)
        return raw_bytes_to_lux(message)
