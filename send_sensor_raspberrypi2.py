#!/usr/bin/env python3
"""Read the sensors connected to the secondary Raspberry Pi."""

import os
import signal
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from bh1750 import read_lux
from ds18b20 import read_temperature
from float_switch import read_triggered
from slack_notifier import process_notifications
from vitality import calculate_basil_vitality


load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SENSOR_KEY = os.getenv("SUPABASE_SENSOR_KEY", "")
SUPABASE_ENDPOINT = f"{SUPABASE_URL}/rest/v1/sensor_logs" if SUPABASE_URL else ""

DEVICE_ID = os.getenv("DEVICE_ID", "raspberrypi2")
LOCATION_ID = os.getenv("LOCATION_ID", "location-b")
SENSOR_INTERVAL_SECONDS = int(os.getenv("SENSOR_INTERVAL_SECONDS", "300"))
DS18B20_SENSOR_ID = os.getenv("DS18B20_SENSOR_ID") or None
BH1750_I2C_BUS = int(os.getenv("BH1750_I2C_BUS", "1"))
BH1750_ADDRESS = int(os.getenv("BH1750_ADDRESS", "0x23"), 0)
FLOAT_SWITCH_GPIO = int(os.getenv("FLOAT_SWITCH_GPIO", "17"))
LIGHT_DARK_LUX = float(os.getenv("LIGHT_DARK_LUX", "100"))
LIGHT_BRIGHT_LUX = float(os.getenv("LIGHT_BRIGHT_LUX", "1000"))
LIGHT_EVALUATION_START_HOUR = int(os.getenv("LIGHT_EVALUATION_START_HOUR", "9"))
LIGHT_EVALUATION_END_HOUR = int(os.getenv("LIGHT_EVALUATION_END_HOUR", "15"))

manual_send_requested = threading.Event()


def request_manual_send(signum, frame):
    manual_send_requested.set()


def light_status(lux):
    if lux is None:
        return None
    if lux < LIGHT_DARK_LUX:
        return "dark"
    if lux >= LIGHT_BRIGHT_LUX:
        return "bright"
    return "dim"


def calculate_remote_status(
    solution_temperature,
    light_state,
    float_triggered,
    light_lux=None,
    observed_at=None,
):
    if light_lux is None:
        representative_lux = {
            "dark": 100.0,
            "dim": 2500.0,
            "bright": 10000.0,
        }
        light_lux = representative_lux.get(light_state)

    return calculate_basil_vitality(
        solution_temperature=solution_temperature,
        light_lux=light_lux,
        float_switch_triggered=float_triggered,
        observed_at=observed_at,
        light_start_hour=LIGHT_EVALUATION_START_HOUR,
        light_end_hour=LIGHT_EVALUATION_END_HOUR,
    )


def read_optional(label, reader):
    try:
        return reader()
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"{label} unavailable: {exc}", flush=True)
        return None


def read_with_retries(label, reader, attempts=3, interval_seconds=0.25):
    for attempt in range(1, max(1, attempts) + 1):
        value = read_optional(label, reader)
        if value is not None:
            return value
        if attempt < attempts:
            time.sleep(max(0.0, interval_seconds))
    return None


def build_payload():
    solution_temperature = read_with_retries(
        "DS18B20",
        lambda: read_temperature(sensor_id=DS18B20_SENSOR_ID),
    )
    light_lux = read_optional(
        "BH1750",
        lambda: read_lux(
            bus_number=BH1750_I2C_BUS,
            address=BH1750_ADDRESS,
        ),
    )
    float_triggered = read_optional(
        "float switch",
        lambda: read_triggered(gpio=FLOAT_SWITCH_GPIO),
    )
    current_light_status = light_status(light_lux)
    observed_at = datetime.now().astimezone()
    vitality_score, message = calculate_remote_status(
        solution_temperature,
        current_light_status,
        float_triggered,
        light_lux=light_lux,
        observed_at=observed_at,
    )

    return {
        "source": "raspberrypi2-ds18b20-bh1750-float",
        "device_id": DEVICE_ID,
        "location_id": LOCATION_ID,
        "solution_temperature": solution_temperature,
        "light_lux": light_lux,
        "light_status": current_light_status,
        "float_switch_triggered": float_triggered,
        "float_switch_state": (
            None
            if float_triggered is None
            else "low_water"
            if float_triggered
            else "water_ok"
        ),
        "vitality_score": vitality_score,
        "message": message,
    }


def send_to_supabase(payload):
    if not SUPABASE_ENDPOINT or not SUPABASE_SENSOR_KEY:
        raise RuntimeError("SUPABASE_URL or SUPABASE_SENSOR_KEY is not set")

    response = requests.post(
        SUPABASE_ENDPOINT,
        json=payload,
        headers={
            "apikey": SUPABASE_SENSOR_KEY,
            "Authorization": f"Bearer {SUPABASE_SENSOR_KEY}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
        timeout=10,
    )
    if not response.ok:
        print(
            f"Supabase error status={response.status_code} body={response.text}",
            flush=True,
        )
    response.raise_for_status()
    print(
        "sent: "
        f"device={payload['device_id']}, "
        f"solution_temperature={payload['solution_temperature']}, "
        f"light={payload['light_lux']}lx({payload['light_status']}), "
        f"float={payload['float_switch_state']}, "
        f"status={response.status_code}",
        flush=True,
    )


def seconds_until_next_send():
    remainder = time.time() % SENSOR_INTERVAL_SECONDS
    return 0 if remainder < 0.001 else SENSOR_INTERVAL_SECONDS - remainder


def process_sensor_cycle():
    payload = build_payload()

    try:
        send_to_supabase(payload)
    except Exception as exc:
        print(f"sensor send error: {type(exc).__name__}: {exc}", flush=True)

    try:
        process_notifications(payload)
    except Exception as exc:
        print(f"[slack] failed: {type(exc).__name__}: {exc}", flush=True)


def main():
    signal.signal(signal.SIGUSR1, request_manual_send)

    while True:
        try:
            process_sensor_cycle()
        except Exception as exc:
            print(f"sensor error: {type(exc).__name__}: {exc}", flush=True)

        manual_send_requested.clear()
        manual_send_requested.wait(seconds_until_next_send())


if __name__ == "__main__":
    main()
