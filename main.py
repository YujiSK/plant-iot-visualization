from fastapi import FastAPI
from pydantic import BaseModel
import sqlite3

app = FastAPI()

conn = sqlite3.connect("data.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS sensor_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    temperature REAL,
    humidity REAL,
    pressure REAL,
    vitality_score INTEGER,
    message TEXT,
    source TEXT DEFAULT 'sensor',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Helper functions for vitality calculation
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
    """Generate status message based on conditions"""
    if humidity < 35:
        return "乾燥しています"
    elif temperature > 30:
        return "温度が高めです"
    else:
        return "安定しています"

class SensorData(BaseModel):
    temperature: float
    humidity: float
    pressure: float
    source: str = "sensor"

@app.post("/sensor")
def receive_sensor(data: SensorData):
    vitality_score = calculate_vitality(data.temperature, data.humidity)
    message = generate_message(data.temperature, data.humidity)
    
    cursor.execute(
        """INSERT INTO sensor_logs 
           (temperature, humidity, pressure, vitality_score, message, source) 
           VALUES (?, ?, ?, ?, ?, ?)""",
        (data.temperature, data.humidity, data.pressure, vitality_score, message, data.source)
    )
    conn.commit()
    return {"status": "ok"}

@app.get("/latest")
def get_latest():
    cursor.execute("""
        SELECT id, temperature, humidity, pressure, created_at, vitality_score, message, source
        FROM sensor_logs
        ORDER BY id DESC
        LIMIT 1
    """)
    row = cursor.fetchone()

    if row is None:
        return {"message": "no data"}

    return {
        "id": row[0],
        "temperature": row[1],
        "humidity": row[2],
        "pressure": row[3],
        "created_at": row[4],
        "vitality_score": row[5],
        "message": row[6],
        "source": row[7]
    }
