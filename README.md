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
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/your/webhook/path
LINE_CHANNEL_ACCESS_TOKEN=your-line-messaging-api-channel-access-token
LINE_TO_ID=your-line-user-or-group-id
NOTIFICATION_STATE_PATH=/home/pi/plant-iot/notification_state.json
```

Slack photo observation logging uses the Slack Bot Token flow, not the existing
incoming webhook used for water-level alerts. Add these values only on the
machine running `slack_observation_bot.py`:

```dotenv
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_SIGNING_SECRET=your-slack-signing-secret
SLACK_OBSERVATION_CHANNEL_ID=C0123456789
AI_VISION_PROVIDER=openai
OPENAI_API_KEY=sk-your-openai-api-key
OPENAI_VISION_MODEL=gpt-4.1
GEMINI_API_KEY=your-gemini-api-key
GEMINI_VISION_MODEL=gemini-3.5-flash
```

The observation bot also reads `SUPABASE_URL`, `SUPABASE_KEY`, `DEVICE_ID`, and
`LOCATION_ID`. For the current deployment, run it with `DEVICE_ID=raspberrypi2`
and `LOCATION_ID=location-b`. `AI_VISION_PROVIDER` selects the backend:
`openai` uses the OpenAI Responses API and `gemini` uses the Gemini API.
`OPENAI_VISION_MODEL` defaults to `gpt-4.1`, and `GEMINI_VISION_MODEL` defaults
to `gemini-3.5-flash`. Keep all Slack tokens, AI provider keys, and Supabase
keys in `.env`; do not commit them.

Slack App settings for photo observation:

- OAuth scopes: `channels:history`, `files:read`, `chat:write`
- Event subscription: subscribe to message events for the observation channel
- Request URL: `https://<public-host>/slack/events`
- Observation target: set `SLACK_OBSERVATION_CHANNEL_ID` to `#plant-observation`

The bot ignores text-only posts, non-image files, bot messages, and channels
other than `SLACK_OBSERVATION_CHANNEL_ID`. It records only Slack file metadata
and the nearest `sensor_logs` summary when available. It does not save image
binaries to Supabase Storage.

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

# Slack photo observation Events API receiver
uvicorn slack_observation_bot:app --host 0.0.0.0 --port 8010
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

## Water-level notifications

Only `raspberrypi2` sends water-level notifications. Set `SLACK_WEBHOOK_URL` in
the secondary device's `.env` to send Slack alerts. To also send LINE alerts,
set `LINE_CHANNEL_ACCESS_TOKEN` and `LINE_TO_ID` for the LINE Messaging API push
message flow. Never add real URLs, tokens, or recipient IDs to Git. The existing
systemd unit already reads `/home/pi/plant-iot/.env`.

The first `low_water` reading sends an alert. Continued low-water readings are
suppressed. A recovery notification is sent after two consecutive `water_ok`
readings. Notification state is stored in `NOTIFICATION_STATE_PATH`, which
defaults to `notification_state.json` beside `slack_notifier.py`.

Slack and LINE errors are logged with `[slack]` and `[line]` prefixes and do not
stop sensor reads or Supabase writes.

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

GitHub Pages uses a responsive sidebar with three views: current status, an
interactive trend graph, and a plain-language research overview. Navigation is
stored in the URL hash (`#home`, `#trends`, or `#about`).

## Supabase security

`docs/config.js` is served publicly by GitHub Pages. Only use a Supabase publishable key there.

Enable Row Level Security on `sensor_logs` and apply `supabase_policies.sql`.

The static UI only needs anonymous read access. Browser writes should stay disabled. Sensor writes should use `SUPABASE_SENSOR_KEY` on the Raspberry Pi service, not a secret embedded in browser code.

Do not reuse `SUPABASE_KEY` for sensor writes. `SUPABASE_KEY` is published in `docs/config.js` for the browser and should only be able to read rows. `SUPABASE_SENSOR_KEY` must stay only in `.env` on the Raspberry Pi.

## 信頼性・運用監視 (Reliability & Operational Monitoring)

本システムは、Silent Failure（送信失敗に誰も気づかない状態）を完全に防ぐため、以下の堅牢なアーキテクチャを備えています。

### 1. 障害時データフロー (SQLite Outbox パターン)

センサーデータの送信処理は **Outbox パターン** に基づいて動作します。

1. **ローカル永続化**: センサーデータ取得後、Supabase への送信前に必ずローカル SQLite (`data.db` 内の `outbox_queue` テーブル) へ `pending` 状態として保存します。
2. **自動再送 (Backfill)**: サービス起動時および毎回の送信サイクル時に、未送信 (`pending` / `failed`) のレコードを自動的に再送します。
3. **重複登録防止**: 送信が成功したレコードのみ `synced` へ更新します。レコードには元の取得時刻 (`created_at`) が保持されるため、再送時もデータ時刻が正確に保たれます。
4. **journalctl への安全なペイロード出力**: 通信障害や 401 API Key 破損等で送信失敗した場合、API Key や Secret 情報を除外した安全な JSON ペイロード全体を `journalctl` に出力します。

```mermaid
flowchart TD
    Sensor["Sensor Read Cycle\n(5-min interval)"] --> Outbox["Save to Local SQLite\noutbox_queue (pending)"]
    Outbox --> Flush["Flush Outbox Queue"]
    Flush --> Post{{"POST /rest/v1/sensor_logs"}}

    Post -- "Success (201)" --> MarkSynced["Update outbox status to synced"]
    MarkSynced --> CheckAlert{"Active Alert?"}
    CheckAlert -- "Yes" --> RecAlert["Send Recovery Notification\n(Slack & LINE)"]
    RecAlert --> ResetState["Reset Failure Counter"]
    CheckAlert -- "No" --> Done["Done"]

    Post -- "Failure\n(401/403/5xx/Timeout/Network)" --> LogPayload["Log Full Payload to journalctl\n(No secrets)"]
    LogPayload --> MarkFailed["Update outbox status to failed\n(Preserved for retry)"]
    MarkFailed --> IncFail["Increment Consecutive Failure Count"]
    IncFail --> Threshold{"Failures >= 3?"}
    Threshold -- "Yes & Cooldown Met" --> SendAlert["Send Dual Alert\n(Slack & LINE)"]
    Threshold -- "No" --> Done
```

### 2. 運用監視 (Heartbeat & システム自己監視)

10 分ごとに `plant-supabase-health.timer` 経由で `supabase_health_check.py` が実行され、以下の項目を多層監視します。

* **Heartbeat 監視**:
  * Supabase 上の `sensor_logs` テーブルの最新 `created_at` を確認
  * 15 分以内: **OK**
  * 30 分以上更新なし: **Warning** (Slack & LINE 通知)
  * 60 分以上更新なし: **Critical** (Slack & LINE 通知)
* **Raspberry Pi 自己監視**:
  * systemd サービス状態 (`plant-sensor-raspberrypi2.service`)
  * ディスク容量使用率 (90% 以上で Warning/Critical)
  * CPU 温度 (80°C 以上で Warning)
  * メモリ使用率 (90% 以上で Warning)

```mermaid
flowchart TD
    Timer["Systemd Timer\n(Every 10 mins)"] --> HealthCheck["supabase_health_check.py"]
    HealthCheck --> CheckAPI["Check Supabase REST API"]
    HealthCheck --> CheckHB["Check Heartbeat\nMAX(created_at)"]
    HealthCheck --> CheckSys["Check Raspberry Pi Hardware\n(Service, Disk, CPU Temp, Mem)"]

    CheckHB --> HBVal{"Age > 30 mins?"}
    HBVal -- "Yes (Warning/Critical)" --> HBAlert["Send Heartbeat Alert\n(Slack & LINE)"]
    HBVal -- "No" --> SystemVal{"Disk >= 90% or Temp >= 80C\nor Service Stopped?"}

    SystemVal -- "Yes" --> SysAlert["Send System Alert\n(Slack & LINE)"]
    SystemVal -- "No" --> OK["Status Normal"]
```

### 3. 通知仕様 (Slack + LINE 二重通知)

* **通知先**: Slack Webhook (`SLACK_WEBHOOK_URL`) および LINE Messaging API (`LINE_CHANNEL_ACCESS_TOKEN`, `LINE_TO_ID`) の両方へ同一のアラートを送信
* **発動条件**: HTTP 401/403/5xx, Timeout, Connection Error, DNS Error, SSL Error が **3 回連続** で発生した場合
* **アラートスパム防止**: アラート送信後は 1 時間のクールダウン期間を設け、エラー継続中のスパム通知を防止
* **復旧通知**: 障害発生後に正常送信へ復帰した際、**復旧通知 (`✅ Plant IoT Recovered`)** を Slack と LINE へ 1 回送信（障害継続時間および再送件数を明記）

### 4. 障害復旧手順

1. **障害通知を受信した場合**:
   * 通知メッセージ内の `Action recommended` を確認します。
   * 例: `HTTP 401 Invalid API key` の場合は `.env` の `SUPABASE_SENSOR_KEY` を確認・更新します。
2. **サービスの再起動**:
   ```bash
   sudo systemctl restart plant-sensor-raspberrypi2.service
   ```
3. **ローカル未送信キューの自動復旧確認**:
   * サービス起動時および送信サイクル時に SQLite outbox (`data.db`) から自動再送されます。
   * 手動確認コマンド:
     ```bash
     python3 -c "import outbox; print('Pending outbox count:', outbox.count_pending())"
     ```
4. **復旧通知の確認**:
   * 正常に Supabase への INSERT が再開されると、自動的に Slack および LINE へ復旧通知が送信されます。

## Slack observation logs

`slack_observation_bot.py` records image posts in `#plant-observation` as
`care_logs` rows with `action_type=checked`. The current `care_logs` schema does
not have `metadata`, `source`, or `observed_at` columns, so Slack channel ID,
user ID, message timestamp, file ID, file name, MIME type, file URL, and the
Slack posting time in JST are written into `note`.

This feature is an observation-recording feature, not AI diagnosis. Its purpose
is to keep plant photos in the project timeline and make later comparison with
sensor values, `daily_sensor_analysis`, and `care_logs` easier.

`ai_observation.py` adds provider-based vision observation support. The OpenAI
provider uses the Responses API, while the Gemini provider uses the Gemini API
with inline image data and JSON Schema response format. The structured
`ai_observation_json` includes
`growth_stage`, `true_leaf_detected`, `true_leaf_pair_count`,
`cotyledon_visible`, `plant_count_estimate`, `crowding`, `leaf_color`,
`leaf_size`, `wilting`, `yellowing`, `root_visibility`,
`root_length_estimate`, `confidence`, `summary`, and `next_action`. The Slack
reply includes this observation support block, `care_logs.note` stores the same
data as `ai_observation_json=...`, and `plant_observations` stores normalized
columns plus `raw_ai_json`.

Phase 3 adds a minimal growth-change comparison. The bot reads the latest
previous `care_logs.note` containing `ai_observation_json=...`, compares growth
stage, estimated plant count, and crowding with the current observation, then
adds a `前回との比較` block to the Slack reply. The comparison JSON is stored in
`care_logs.note` as `observation_comparison_json=...`. New notes also include
`device_id=...` and `location_id=...` so future comparisons can prefer the same
device and location.

The observation module is intentionally not a disease diagnosis system. If the
selected provider key is not set, it returns conservative fallback values so
Slack photo logging still works, but normalized AI quality is lower.

Apply the normalized observation table before relying on `plant_observations`:

```bash
psql "$SUPABASE_DB_URL" -f supabase_plant_observations.sql
```

## Slack写真観察Botの常駐化

`slack_observation_bot.py` は、2号機上で systemd サービスとして常駐化している。

サービス名:

```bash
plant-slack-observation.service
```

状態確認:

```bash
systemctl status plant-slack-observation.service --no-pager
```

ログ確認:

```bash
journalctl -u plant-slack-observation.service -n 80 --no-pager
```

ローカル疎通確認:

```bash
curl -i http://127.0.0.1:8010/slack/events
```

`405 Method Not Allowed` が返れば、FastAPI アプリは起動している。

外部公開は現時点では Cloudflare Quick Tunnel を systemd で常駐化している。

```bash
systemctl status cloudflared-quick-tunnel.service --no-pager
```

ログから `https://xxxxx.trycloudflare.com` を取り出し、`/slack/events`
を付けて Slack App の Request URL に設定する。

Quick Tunnel は起動ごとに URL が変わるため、恒久運用時は Cloudflare
named tunnel への移行を検討する。

URL 確認:

```bash
journalctl -u cloudflared-quick-tunnel.service -b --no-pager -o cat \
  | rg -o 'https://[[:alnum:]-]+\.trycloudflare\.com' \
  | tail -n1
```
