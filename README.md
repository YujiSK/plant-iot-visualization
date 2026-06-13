# Plant IoT

Two-device Raspberry Pi plant monitor.

Both Raspberry Pis use this repository but run different sensor entry points.

## Runtime

- `main.py`: FastAPI API. Stores sensor readings in local SQLite.
- `send_sensor_raspi.py`: Primary device. Reads DHT11, DS18B20, water level CH0, and CdS CH1.
- `send_sensor_raspberrypi2.py`: Secondary device. Reads BH1750, DS18B20, and the GPIO17 float switch.
- `send_sensor.py`: Backward-compatible wrapper for `send_sensor_raspi.py`.
- `docs/index.html`: Static GitHub Pages UI. Reads the latest row from Supabase.

## Device layout

### raspi / location-a

- DHT11: GPIO17
- DS18B20: GPIO4
- Water level sensor: MCP3204/MCP3208 CH0
- CdS light sensor: MCP3204/MCP3208 CH1
- LED: GPIO23 through a current-limiting resistor

### raspberrypi2 / location-b

- BH1750: I2C1 GPIO2/GPIO3, address `0x23`
- DS18B20: GPIO4
- Active-low float switch: GPIO17 to GND

The complete wiring reference is available in
[`docs/WIRING.md`](docs/WIRING.md). The diagram is generated from
[`docs/wiring.dot`](docs/wiring.dot) and published as
[`docs/wiring.svg`](docs/wiring.svg).

The verified deployment status, services, and remaining work are summarized in
[`docs/CURRENT_STATUS_2026-06-13.md`](docs/CURRENT_STATUS_2026-06-13.md).

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

The secondary device does not need the DHT11/SPI dependencies:

```bash
# raspberrypi2
pip install -r requirements-raspberrypi2.txt
```

Create `.env` on `raspi`:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-publishable-key
SUPABASE_SENSOR_KEY=your-private-service-role-or-sensor-write-key
SENSOR_INTERVAL_SECONDS=300
DHT_RETRIES=8
DS18B20_SENSOR_ID=28-your-sensor-id
DEVICE_ID=raspi
LOCATION_ID=location-a
MANUAL_SEND_MIN_INTERVAL_SECONDS=60
```

Create a separate `.env` on `raspberrypi2`:

```dotenv
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-publishable-key
SUPABASE_SENSOR_KEY=your-private-service-role-or-sensor-write-key
SENSOR_INTERVAL_SECONDS=300
DS18B20_SENSOR_ID=28-your-sensor-id
DEVICE_ID=raspberrypi2
LOCATION_ID=location-b
BH1750_I2C_BUS=1
BH1750_ADDRESS=0x23
FLOAT_SWITCH_GPIO=17
LIGHT_DARK_LUX=100
LIGHT_BRIGHT_LUX=1000
LIGHT_EVALUATION_START_HOUR=9
LIGHT_EVALUATION_END_HOUR=15
MANUAL_SEND_MIN_INTERVAL_SECONDS=60
```

`TEMP_OFFSET` and `HUMIDITY_OFFSET` were for the old Sense HAT prototype. The
current DHT11 runtime intentionally does not apply offset correction.

Historical SQLite rows can be exported with both the stored values and the
reconstructed pre-offset Sense HAT outputs:

```bash
python scripts/reconstruct_historical_sensor_data.py \
  --db data.db \
  --output exports/sensor_logs_reconstructed.csv
```

The source database is opened read-only. The CSV preserves every original
column and adds the applied offsets, reconstructed outputs, evidence, and
confidence. A metadata JSON file records the source database hashes and the
reconstruction periods. Generated files under `exports/` are not committed.
The reconstructed Sense HAT temperature still includes Raspberry Pi board heat
and is not a calibrated ambient temperature.

`LIGHT_EVALUATION_START_HOUR` and `LIGHT_EVALUATION_END_HOUR` define the local
core daylight window used for vitality scoring. Lux readings outside this
window are recorded but do not reduce vitality.

Enable 1-Wire for the DS18B20 by adding
`dtoverlay=w1-gpio,gpiopin=4` to `/boot/firmware/config.txt`, then reboot.
`DS18B20_SENSOR_ID` is optional when only one DS18B20 is connected.

On `raspberrypi2`, enable both I2C and 1-Wire before starting the service.

Generate the static Pages config:

```bash
python scripts/generate_pages_config.py
```

## Run

```bash
uvicorn main:app --host 0.0.0.0 --port 8000

# raspi
python send_sensor_raspi.py

# raspberrypi2
python send_sensor_raspberrypi2.py
```

`send_sensor.py` remains as a compatibility wrapper for the existing
`plant-sensor.service` on `raspi`.

Trigger one manual reading without restarting each service:

```bash
# raspi
sudo systemctl reload plant-sensor.service
journalctl -u plant-sensor.service -n 30 --no-pager -l

# raspberrypi2
sudo systemctl reload plant-sensor-raspberrypi2.service
journalctl -u plant-sensor-raspberrypi2.service -n 30 --no-pager -l
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
supabase_light_lux_migration.sql
supabase_multi_device_migration.sql
supabase_multi_device_nullable_ambient_migration.sql
```

The deployed environment has these migrations applied. The primary sender
retains a fallback write path for older database deployments.

GitHub Pages selects a device with a query parameter:

```text
?device=raspi
?device=raspberrypi2
```

## Supabase security

`docs/config.js` is served publicly by GitHub Pages. Only use a Supabase publishable key there.

Enable Row Level Security on `sensor_logs` and apply `supabase_policies.sql`.

The static UI only needs anonymous read access. Browser writes should stay disabled. Sensor writes should use `SUPABASE_SENSOR_KEY` on the Raspberry Pi service, not a secret embedded in browser code.

Do not reuse `SUPABASE_KEY` for sensor writes. `SUPABASE_KEY` is published in `docs/config.js` for the browser and should only be able to read rows. `SUPABASE_SENSOR_KEY` must stay only in `.env` on the Raspberry Pi.
