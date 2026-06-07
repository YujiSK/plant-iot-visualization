#!/usr/bin/env python3
"""Read the current wired sensors and send readings to local API and Supabase.

Current hardware:
- DHT11 DATA on BCM GPIO4 for temperature/humidity
- MCP3204/MCP3208 on SPI0 CE0
- ADC CH0: water level sensor SIG
- ADC CH1: light sensor AO
"""

import os
import statistics
import time

import adafruit_dht
import board
import requests
import spidev
from dotenv import load_dotenv

from vitality import calculate_vitality, generate_message

URL = "http://localhost:8000/sensor"
VREF = 3.3
ADC_MAX = 4095

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_SENSOR_KEY = os.getenv("SUPABASE_SENSOR_KEY", "")
SUPABASE_ENDPOINT = f"{SUPABASE_URL}/rest/v1/sensor_logs" if SUPABASE_URL else ""

DHT_RETRIES = int(os.getenv("DHT_RETRIES", "8"))
DHT_RETRY_INTERVAL_SECONDS = float(os.getenv("DHT_RETRY_INTERVAL_SECONDS", "2.0"))

ADC_BUS = int(os.getenv("ADC_BUS", "0"))
ADC_DEVICE = int(os.getenv("ADC_DEVICE", "0"))
ADC_MAX_SPEED_HZ = int(os.getenv("ADC_MAX_SPEED_HZ", "1000000"))
ADC_SAMPLES = int(os.getenv("ADC_SAMPLES", "5"))
ADC_SAMPLE_DELAY_SECONDS = float(os.getenv("ADC_SAMPLE_DELAY_SECONDS", "0.05"))


def get_interval_seconds():
    value = os.getenv("SENSOR_INTERVAL_SECONDS", "300")
    try:
        interval = int(value)
        if interval <= 0:
            raise ValueError("interval must be positive")
        return interval
    except Exception:
        print(f"invalid SENSOR_INTERVAL_SECONDS='{value}', using 300", flush=True)
        return 300


SENSOR_INTERVAL_SECONDS = get_interval_seconds()


def read_mcp320x(spi, channel):
    """Read one single-ended MCP3204/MCP3208 channel as a 12-bit raw value."""
    if not 0 <= channel <= 7:
        raise ValueError("channel must be between 0 and 7")

    response = spi.xfer2(
        [
            0x06 | ((channel & 0x04) >> 2),
            (channel & 0x03) << 6,
            0x00,
        ]
    )
    return ((response[1] & 0x0F) << 8) | response[2]


def voltage_from_raw(raw):
    return round(raw * VREF / ADC_MAX, 3)


def read_adc_median(spi, channel):
    samples = []
    for _ in range(max(1, ADC_SAMPLES)):
        samples.append(read_mcp320x(spi, channel))
        time.sleep(max(0.0, ADC_SAMPLE_DELAY_SECONDS))
    return int(statistics.median(samples))


def water_status(raw):
    if raw < 200:
        return "dry"
    if raw >= 1800:
        return "enough_water"
    if raw >= 800:
        return "wet"
    return "transition"


def light_status(raw):
    if raw < 700:
        return "dark"
    if raw >= 1200:
        return "bright"
    return "dim"


def read_dht11(dht):
    last_error = None
    for attempt in range(1, max(1, DHT_RETRIES) + 1):
        try:
            raw_temperature = dht.temperature
            raw_humidity = dht.humidity
            if raw_temperature is None or raw_humidity is None:
                raise RuntimeError("DHT11 returned no data")

            temperature = round(float(raw_temperature), 2)
            humidity = round(float(raw_humidity), 2)
            return raw_temperature, raw_humidity, temperature, humidity
        except RuntimeError as exc:
            last_error = exc
            print(f"DHT11 retry {attempt}/{DHT_RETRIES}: {exc}", flush=True)
            time.sleep(max(1.0, DHT_RETRY_INTERVAL_SECONDS))

    raise RuntimeError(f"DHT11 read failed after {DHT_RETRIES} attempts: {last_error}")


def send_to_supabase(payload):
    """Send sensor payload to Supabase REST API without interrupting main loop."""
    if not SUPABASE_ENDPOINT or not SUPABASE_SENSOR_KEY:
        print("SUPABASE ERROR: SUPABASE_URL or SUPABASE_SENSOR_KEY is not set", flush=True)
        return

    headers = {
        "apikey": SUPABASE_SENSOR_KEY,
        "Authorization": f"Bearer {SUPABASE_SENSOR_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        response = requests.post(SUPABASE_ENDPOINT, json=payload, headers=headers, timeout=10)
        print(f"SUPABASE URL: {SUPABASE_ENDPOINT}", flush=True)
        print(f"SUPABASE STATUS: {response.status_code}", flush=True)
        print(f"SUPABASE RESPONSE: {response.text}", flush=True)

        if response.status_code >= 400 and has_adc_fields(payload):
            legacy_payload = legacy_supabase_payload(payload)
            retry = requests.post(
                SUPABASE_ENDPOINT, json=legacy_payload, headers=headers, timeout=10
            )
            print("SUPABASE RETRY WITHOUT ADC FIELDS", flush=True)
            print(f"SUPABASE RETRY STATUS: {retry.status_code}", flush=True)
            print(f"SUPABASE RETRY RESPONSE: {retry.text}", flush=True)
    except Exception as exc:
        print("SUPABASE ERROR:", exc, flush=True)


def has_adc_fields(payload):
    return any(key.startswith(("water_", "light_")) for key in payload)


def legacy_supabase_payload(payload):
    keys = [
        "temperature",
        "humidity",
        "pressure",
        "vitality_score",
        "message",
        "source",
    ]
    return {key: payload[key] for key in keys if key in payload}


def read_sensor_payload(dht, spi):
    raw_temperature, raw_humidity, temperature, humidity = read_dht11(dht)

    water_raw = read_adc_median(spi, 0)
    light_raw = read_adc_median(spi, 1)

    vitality_score = calculate_vitality(temperature, humidity)
    message = generate_message(temperature, humidity)

    data = {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": None,
        "source": "dht11-mcp3204",
        "water_raw": water_raw,
        "water_voltage": voltage_from_raw(water_raw),
        "water_status": water_status(water_raw),
        "light_raw": light_raw,
        "light_voltage": voltage_from_raw(light_raw),
        "light_status": light_status(light_raw),
    }

    supabase_payload = {
        **data,
        "vitality_score": vitality_score,
        "message": message,
    }

    return raw_temperature, raw_humidity, data, supabase_payload


def run_once(dht, spi):
    raw_temperature, raw_humidity, data, supabase_payload = read_sensor_payload(dht, spi)
    response = requests.post(URL, json=data, timeout=5)
    print(
        "sent: "
        f"raw_temp={raw_temperature}, "
        f"temperature={data['temperature']}, "
        f"raw_humidity={raw_humidity}, "
        f"humidity={data['humidity']}, "
        f"water={data['water_raw']}({data['water_status']}), "
        f"light={data['light_raw']}({data['light_status']}), "
        f"vitality={supabase_payload['vitality_score']}, "
        f"status={response.status_code}",
        flush=True,
    )
    send_to_supabase(supabase_payload)


def main():
    dht = adafruit_dht.DHT11(board.D4)
    spi = spidev.SpiDev()
    spi.open(ADC_BUS, ADC_DEVICE)
    spi.max_speed_hz = ADC_MAX_SPEED_HZ
    spi.mode = 0

    try:
        while True:
            try:
                run_once(dht, spi)
            except Exception as exc:
                print("error:", exc, flush=True)

            time.sleep(SENSOR_INTERVAL_SECONDS)
    finally:
        try:
            dht.exit()
        finally:
            spi.close()


if __name__ == "__main__":
    main()
