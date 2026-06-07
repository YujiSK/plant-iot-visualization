import sqlite3
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from vitality import calculate_vitality, generate_message

app = FastAPI()
DB_PATH = "data.db"


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    with get_connection() as conn:
        conn.execute("""
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
        existing_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(sensor_logs)").fetchall()
        }
        migrations = {
            "water_raw": "ALTER TABLE sensor_logs ADD COLUMN water_raw INTEGER",
            "water_voltage": "ALTER TABLE sensor_logs ADD COLUMN water_voltage REAL",
            "water_status": "ALTER TABLE sensor_logs ADD COLUMN water_status TEXT",
            "light_raw": "ALTER TABLE sensor_logs ADD COLUMN light_raw INTEGER",
            "light_voltage": "ALTER TABLE sensor_logs ADD COLUMN light_voltage REAL",
            "light_status": "ALTER TABLE sensor_logs ADD COLUMN light_status TEXT",
        }
        for column, statement in migrations.items():
            if column not in existing_columns:
                conn.execute(statement)


init_db()


class SensorData(BaseModel):
    temperature: float
    humidity: float
    pressure: Optional[float] = None
    source: str = "sensor"
    water_raw: Optional[int] = None
    water_voltage: Optional[float] = None
    water_status: Optional[str] = None
    light_raw: Optional[int] = None
    light_voltage: Optional[float] = None
    light_status: Optional[str] = None


@app.post("/sensor")
def receive_sensor(data: SensorData):
    vitality_score = calculate_vitality(data.temperature, data.humidity)
    message = generate_message(data.temperature, data.humidity)

    with get_connection() as conn:
        conn.execute(
            """INSERT INTO sensor_logs
               (temperature, humidity, pressure, vitality_score, message, source,
                water_raw, water_voltage, water_status,
                light_raw, light_voltage, light_status)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                data.temperature,
                data.humidity,
                data.pressure,
                vitality_score,
                message,
                data.source,
                data.water_raw,
                data.water_voltage,
                data.water_status,
                data.light_raw,
                data.light_voltage,
                data.light_status,
            ),
        )
    return {"status": "ok"}


@app.get("/latest")
def get_latest():
    with get_connection() as conn:
        row = conn.execute("""
            SELECT id, temperature, humidity, pressure, created_at, vitality_score, message, source,
                   water_raw, water_voltage, water_status,
                   light_raw, light_voltage, light_status
            FROM sensor_logs
            ORDER BY id DESC
            LIMIT 1
        """).fetchone()

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
        "source": row[7],
        "water_raw": row[8],
        "water_voltage": row[9],
        "water_status": row[10],
        "light_raw": row[11],
        "light_voltage": row[12],
        "light_status": row[13],
    }
