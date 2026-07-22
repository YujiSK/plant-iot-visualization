#!/usr/bin/env python3
"""Read the sensors connected to the secondary Raspberry Pi."""

import json
import os
import signal
import threading
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

from alert_manager import record_transmission_failure, record_transmission_success
from bh1750 import read_lux
from care_log import send_recovery_care_log
from ds18b20 import read_temperature
from float_switch import FloatSwitchStateMonitor, read_triggered
from outbox import enqueue, flush_outbox
from slack_notifier import load_notification_state, process_notifications
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
FLOAT_MONITOR_INTERVAL_SECONDS = float(
    os.getenv("FLOAT_MONITOR_INTERVAL_SECONDS", "1")
)
FLOAT_LOW_WATER_CONFIRMATIONS = int(
    os.getenv("FLOAT_LOW_WATER_CONFIRMATIONS", "3")
)
FLOAT_WATER_OK_CONFIRMATIONS = int(
    os.getenv("FLOAT_WATER_OK_CONFIRMATIONS", "10")
)
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


def build_payload(float_triggered=None):
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
    if float_triggered is None:
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
        "created_at": observed_at.isoformat(),
    }


def send_single_payload_raw(payload):
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
        err_msg = f"HTTP {response.status_code} {response.text[:200]}"
        raise RuntimeError(err_msg)
    return True


def send_to_supabase_with_outbox(payload):
    # Enqueue payload locally to outbox queue first
    enqueue(payload)

    last_error = None
    try:
        synced_count, failed_count = flush_outbox(send_single_payload_raw)
    except Exception as exc:
        synced_count = 0
        failed_count = 1
        last_error = str(exc)

    if synced_count > 0:
        resent = max(0, synced_count - 1)
        print(
            "sent: "
            f"device={payload['device_id']}, "
            f"solution_temperature={payload['solution_temperature']}, "
            f"light={payload['light_lux']}lx({payload['light_status']}), "
            f"float={payload['float_switch_state']}, "
            f"status=201 (synced={synced_count})",
            flush=True,
        )
        record_transmission_success(DEVICE_ID, resent_count=resent)
    else:
        # Failure: output full payload to journalctl safely
        payload_str = json.dumps(payload, ensure_ascii=False, indent=2)
        err_desc = last_error or "Transmission failed"
        print(
            f"POST failed ({err_desc})\n"
            f"payload={payload_str}",
            flush=True,
        )
        record_transmission_failure(DEVICE_ID, f"POST failed: {err_desc}")


send_to_supabase = send_to_supabase_with_outbox


def seconds_until_next_send():
    remainder = time.time() % SENSOR_INTERVAL_SECONDS
    return 0 if remainder < 0.001 else SENSOR_INTERVAL_SECONDS - remainder


def process_sensor_cycle(float_triggered=None):
    payload = build_payload(float_triggered=float_triggered)

    try:
        send_to_supabase(payload)
    except Exception as exc:
        print(f"sensor send error: {type(exc).__name__}: {exc}", flush=True)

    try:
        process_notifications(payload, recovery_confirmations=1)
    except Exception as exc:
        print(f"[notification] failed: {type(exc).__name__}: {exc}", flush=True)

    return payload


def notification_payload(float_state, latest_payload=None):
    latest_payload = latest_payload or {}
    return {
        "device_id": DEVICE_ID,
        "location_id": LOCATION_ID,
        "float_switch_state": float_state,
        "float_switch_triggered": float_state == "low_water",
        "vitality_score": latest_payload.get("vitality_score"),
        "solution_temperature": latest_payload.get("solution_temperature"),
        "light_lux": latest_payload.get("light_lux"),
    }


def process_float_transition(float_state, latest_payload=None):
    payload = notification_payload(float_state, latest_payload)
    try:
        process_notifications(payload, recovery_confirmations=1)
    except Exception as exc:
        print(f"[notification] failed: {type(exc).__name__}: {exc}", flush=True)

    if float_state == "water_ok":
        send_recovery_care_log(payload, datetime.now().astimezone().isoformat())


def initial_float_state():
    try:
        state = load_notification_state()
    except Exception as exc:
        print(
            f"[slack] failed: state load during monitor startup: "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None
    return "low_water" if state["low_water"].get("active") else None


def main():
    signal.signal(signal.SIGUSR1, request_manual_send)
    float_monitor = FloatSwitchStateMonitor(
        low_water_confirmations=FLOAT_LOW_WATER_CONFIRMATIONS,
        water_ok_confirmations=FLOAT_WATER_OK_CONFIRMATIONS,
        initial_state=initial_float_state(),
    )
    latest_payload = None
    next_sensor_send_at = 0.0

    while True:
        try:
            float_triggered = read_optional(
                "float switch",
                lambda: read_triggered(
                    gpio=FLOAT_SWITCH_GPIO,
                    samples=1,
                    interval_seconds=0,
                ),
            )
            transition = float_monitor.observe(float_triggered)
            if transition:
                process_float_transition(transition, latest_payload)

            now = time.time()
            if manual_send_requested.is_set() or now >= next_sensor_send_at:
                manual_send_requested.clear()
                confirmed_triggered = (
                    float_monitor.confirmed_state == "low_water"
                    if float_monitor.confirmed_state is not None
                    else float_triggered
                )
                latest_payload = process_sensor_cycle(
                    float_triggered=confirmed_triggered
                )
                next_sensor_send_at = now + seconds_until_next_send()
        except Exception as exc:
            print(f"sensor error: {type(exc).__name__}: {exc}", flush=True)

        manual_send_requested.wait(max(0.1, FLOAT_MONITOR_INTERVAL_SECONDS))


if __name__ == "__main__":
    main()
