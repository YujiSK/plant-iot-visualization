# Plant IoT

Raspberry Pi plant monitor.

The project started with a Sense HAT-based prototype. The current hardware
configuration uses DHT11 and MCP3204/MCP3208 ADC wiring instead.

## Runtime

- `main.py`: FastAPI API. Stores sensor readings in local SQLite.
- `send_sensor.py`: Reads DHT11 temperature/humidity, DS18B20 solution temperature, and MCP3204/MCP3208 ADC values, then posts each reading to the local API and Supabase.
- `docs/index.html`: Static GitHub Pages UI. Reads the latest row from Supabase.

## Current wiring

- DHT11 `DATA` -> Raspberry Pi GPIO17 / physical pin 11, with 10kohm pull-up to 3.3V.
- DS18B20 `DATA` -> Raspberry Pi GPIO4 / physical pin 7, with 4.7kohm pull-up to 3.3V.
- MCP3204/MCP3208 `CH0` -> water level sensor `SIG`.
- MCP3204/MCP3208 `CH1` -> light sensor `AO`.
- MCP3204/MCP3208 uses SPI0 CE0:
  - `CLK` -> GPIO11 SCLK / physical pin 23
  - `DOUT` -> GPIO9 MISO / physical pin 21
  - `DIN` -> GPIO10 MOSI / physical pin 19
  - `CS/SHDN` -> GPIO8 CE0 / physical pin 24
- ADC `VDD` and `VREF` are 3.3V. Do not feed 5V into ADC inputs.

The complete wiring reference is available in
[`docs/WIRING.md`](docs/WIRING.md). The diagram is generated from
[`docs/wiring.dot`](docs/wiring.dot) and published as
[`docs/wiring.svg`](docs/wiring.svg).

Generate it after installing Graphviz:

```bash
sudo apt install graphviz
python scripts/generate_wiring_diagram.py
```

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
DS18B20_SENSOR_ID=28-your-sensor-id
MANUAL_SEND_MIN_INTERVAL_SECONDS=60
```

`TEMP_OFFSET` and `HUMIDITY_OFFSET` were for the old Sense HAT prototype. The
current DHT11 runtime intentionally does not apply offset correction.

Enable 1-Wire for the DS18B20 by adding
`dtoverlay=w1-gpio,gpiopin=4` to `/boot/firmware/config.txt`, then reboot.
`DS18B20_SENSOR_ID` is optional when only one DS18B20 is connected.

Generate the static Pages config:

```bash
python scripts/generate_pages_config.py
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
python send_sensor.py
```

Trigger one manual reading without restarting the service:

```bash
sudo systemctl reload plant-sensor.service
journalctl -u plant-sensor.service -n 30 --no-pager -l
```

Manual reload requests are skipped when the previous successful send was less
than `MANUAL_SEND_MIN_INTERVAL_SECONDS` seconds ago, to avoid accidental
duplicate rows.

Regular sends are aligned to wall-clock interval boundaries. With the default
`SENSOR_INTERVAL_SECONDS=300`, readings run at 00, 05, 10, 15, ... minutes.

## Sensor fields

Local SQLite is migrated automatically on API startup. Supabase needs the
matching migrations before the additional sensor fields can be stored there:

```bash
supabase_sensor_logs_adc_migration.sql
supabase_solution_temperature_migration.sql
```

Until that migration is applied, `send_sensor.py` retries Supabase writes
without the ADC fields so temperature/humidity logging can continue.

## Supabase security

`docs/config.js` is served publicly by GitHub Pages. Only use a Supabase publishable key there.

Enable Row Level Security on `sensor_logs` and apply `supabase_policies.sql`.

The static UI only needs anonymous read access. Browser writes should stay disabled. Sensor writes should use `SUPABASE_SENSOR_KEY` on the Raspberry Pi service, not a secret embedded in browser code.

Do not reuse `SUPABASE_KEY` for sensor writes. `SUPABASE_KEY` is published in `docs/config.js` for the browser and should only be able to read rows. `SUPABASE_SENSOR_KEY` must stay only in `.env` on the Raspberry Pi.
