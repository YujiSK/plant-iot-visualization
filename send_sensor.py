from sense_hat import SenseHat
import requests
import time
import os
from dotenv import load_dotenv

sense = SenseHat()
URL = "http://localhost:8000/sensor"

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
SUPABASE_ENDPOINT = f"{SUPABASE_URL}/rest/v1/sensor_logs" if SUPABASE_URL else ""
LED_HOLD_SECONDS = float(os.getenv("LED_HOLD_SECONDS", "2"))
# Sense HAT temperature tends to be affected by Raspberry Pi board heat.
# Apply a configurable offset to approximate ambient temperature.
TEMP_OFFSET = float(os.getenv("TEMP_OFFSET", "-8.0"))

def get_interval_seconds():
    """Read sensor interval from env and fall back to 300 seconds."""
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

def score_temp(temperature):
    """Temperature score: optimal 24-28, acceptable 20-30, poor otherwise"""
    if 24 <= temperature <= 28:
        return 100
    elif 20 <= temperature <= 30:
        return 70
    else:
        return 40

def score_humidity(humidity):
    """Humidity score: optimal 40-60, acceptable 35-70, poor otherwise"""
    if 40 <= humidity <= 60:
        return 100
    elif 35 <= humidity <= 70:
        return 70
    else:
        return 40

def calculate_vitality(temperature, humidity):
    """Calculate vitality score: temp*0.6 + humidity*0.4"""
    return int(score_temp(temperature) * 0.6 + score_humidity(humidity) * 0.4)

def generate_message(temperature, humidity):
    """Generate status message based on temperature and humidity."""
    if humidity < 35:
        return "乾燥しています"
    elif temperature > 30:
        return "温度が高めです"
    return "安定しています"

def send_to_supabase(payload):
    """Send sensor payload to Supabase REST API without interrupting main loop."""
    if not SUPABASE_ENDPOINT or not SUPABASE_KEY:
        print("SUPABASE ERROR: SUPABASE_URL or SUPABASE_KEY is not set", flush=True)
        return

    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    try:
        response = requests.post(SUPABASE_ENDPOINT, json=payload, headers=headers, timeout=10)
        print(f"SUPABASE URL: {SUPABASE_ENDPOINT}", flush=True)
        print(f"SUPABASE STATUS: {response.status_code}", flush=True)
        print(f"SUPABASE RESPONSE: {response.text}", flush=True)
    except Exception as exc:
        print("SUPABASE ERROR:", exc, flush=True)

def show_led_status(sense, vitality_score):
    """Show status color briefly, then clear LED to avoid constant lighting."""
    if vitality_score >= 80:
        bg = [0, 255, 0]      # Green for good
    elif vitality_score >= 60:
        bg = [255, 255, 0]    # Yellow for caution
    else:
        bg = [255, 0, 0]      # Red for poor

    sense.clear(bg)
    time.sleep(max(0.0, LED_HOLD_SECONDS))
    sense.clear()

while True:
    raw_temperature = round(sense.get_temperature(), 2)
    temperature = round(raw_temperature + TEMP_OFFSET, 2)
    humidity = round(sense.get_humidity(), 2)
    pressure = round(sense.get_pressure(), 2)
    
    # Calculate vitality score
    vitality_score = calculate_vitality(temperature, humidity)
    message = generate_message(temperature, humidity)
    
    # Prepare data with source marker
    data = {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
        "source": "sensor"
    }

    supabase_payload = {
        "temperature": data["temperature"],
        "humidity": data["humidity"],
        "pressure": data["pressure"],
        "vitality_score": vitality_score,
        "message": message,
        "source": "sensor",
    }

    try:
        r = requests.post(URL, json=data, timeout=5)
        print(
            f"sent: raw_temp={raw_temperature}, corrected_temp={temperature}, humidity={humidity}, vitality={vitality_score}, status={r.status_code}",
            flush=True,
        )

        send_to_supabase(supabase_payload)
        
        # Display LED status after successful POST
        show_led_status(sense, vitality_score)
        
    except Exception as e:
        print("error:", e)
        sense.clear([255, 0, 0])  # Red on error
        time.sleep(max(0.0, LED_HOLD_SECONDS))
        sense.clear()

    time.sleep(SENSOR_INTERVAL_SECONDS)
