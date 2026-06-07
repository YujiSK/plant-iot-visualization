# Plant IoT

Raspberry Pi plant monitor.

The project started with a Sense HAT-based prototype. The current hardware
configuration uses DHT11 and MCP3204/MCP3208 ADC wiring instead.

## Runtime

- `main.py`: FastAPI API. Stores sensor readings in local SQLite.
- `send_sensor.py`: Reads DHT11 temperature/humidity and MCP3204/MCP3208 ADC values, then posts each reading to the local API and Supabase.
- `docs/index.html`: Static GitHub Pages UI. Reads the latest row from Supabase.

## Current wiring

- DHT11 `DATA` -> Raspberry Pi GPIO4 / physical pin 7, with 10kohm pull-up to 3.3V.
- MCP3204/MCP3208 `CH0` -> water level sensor `SIG`.
- MCP3204/MCP3208 `CH1` -> light sensor `AO`.
- MCP3204/MCP3208 uses SPI0 CE0:
  - `CLK` -> GPIO11 SCLK / physical pin 23
  - `DOUT` -> GPIO9 MISO / physical pin 21
  - `DIN` -> GPIO10 MOSI / physical pin 19
  - `CS/SHDN` -> GPIO8 CE0 / physical pin 24
- ADC `VDD` and `VREF` are 3.3V. Do not feed 5V into ADC inputs.

## Setup

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Create `.env`:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-publishable-key
SUPABASE_SENSOR_KEY=your-private-service-role-or-sensor-write-key
SENSOR_INTERVAL_SECONDS=300
DHT_RETRIES=8
LED_HOLD_SECONDS=2
```

`TEMP_OFFSET` and `HUMIDITY_OFFSET` were for the old Sense HAT prototype. The
current DHT11 runtime intentionally does not apply offset correction.

Generate the static Pages config:

```bash
python scripts/generate_pages_config.py
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
python send_sensor.py
```

## Sensor fields

Local SQLite is migrated automatically on API startup. Supabase needs the
matching migration before ADC fields can be stored there:

```bash
supabase_sensor_logs_adc_migration.sql
```

Until that migration is applied, `send_sensor.py` retries Supabase writes
without the ADC fields so temperature/humidity logging can continue.

## Supabase security

`docs/config.js` is served publicly by GitHub Pages. Only use a Supabase publishable key there.

Enable Row Level Security on `sensor_logs` and apply `supabase_policies.sql`.

The static UI only needs anonymous read access. Browser writes should stay disabled. Sensor writes should use `SUPABASE_SENSOR_KEY` on the Raspberry Pi service, not a secret embedded in browser code.

Do not reuse `SUPABASE_KEY` for sensor writes. `SUPABASE_KEY` is published in `docs/config.js` for the browser and should only be able to read rows. `SUPABASE_SENSOR_KEY` must stay only in `.env` on the Raspberry Pi.
