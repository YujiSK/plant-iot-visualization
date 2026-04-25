from sense_hat import SenseHat
import requests
import time

sense = SenseHat()
URL = "http://localhost:8000/sensor"

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

def show_led_status(sense, vitality_score):
    """Display vitality status on Sense HAT LED with background color"""
    if vitality_score >= 80:
        bg = [0, 255, 0]      # Green for good
    elif vitality_score >= 60:
        bg = [255, 255, 0]    # Yellow for caution
    else:
        bg = [255, 0, 0]      # Red for poor
    
    sense.clear(bg)

while True:
    temperature = round(sense.get_temperature(), 2)
    humidity = round(sense.get_humidity(), 2)
    pressure = round(sense.get_pressure(), 2)
    
    # Calculate vitality score
    vitality = calculate_vitality(temperature, humidity)
    
    # Prepare data with source marker
    data = {
        "temperature": temperature,
        "humidity": humidity,
        "pressure": pressure,
        "source": "sensor"
    }

    try:
        r = requests.post(URL, json=data, timeout=5)
        print(f"sent: temp={temperature}, humidity={humidity}, vitality={vitality}, status={r.status_code}")
        
        # Display LED status after successful POST
        show_led_status(sense, vitality)
        
    except Exception as e:
        print("error:", e)
        sense.clear([255, 0, 0])  # Red on error

    time.sleep(10)
