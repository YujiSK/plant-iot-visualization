# Plant IoT 現状まとめ

更新日: 2026-06-13
リポジトリ: `plant-iot-visualization`
最新確認コミット: `99ad311`

## 1. システム概要

2台のRaspberry Piを別の設置場所で使用し、それぞれのセンサーデータを同じSupabaseへ送信する構成です。

```text
未設置・動作確認環境
└─ raspi
   ├─ DHT11
   ├─ DS18B20
   ├─ 水位センサー
   ├─ CdSセル
   └─ LED

設置場所B
└─ raspberrypi2
   ├─ BH1750
   ├─ DS18B20
   └─ フロートスイッチ

両機
└─ Supabase
   └─ GitHub Pagesで表示
```

データは`device_id`と`location_id`で機体・設置場所を識別します。

| 機体 | `device_id` | `location_id` |
|---|---|---|
| raspi | `raspi` | `location-a` |
| raspberrypi2 | `raspberrypi2` | `location-b` |

## 2. raspiの構成

ホスト名: `raspberrypi`
SSH名: `raspi`

現在、`raspi`は実際のバジル栽培キットへ設置されていません。以下のセンサー値は動作確認値であり、栽培中植物の状態を表すものではありません。

### 配線

| 機器 | 接続 |
|---|---|
| DHT11 DATA | GPIO17 / 物理ピン11 |
| DS18B20 DATA | GPIO4 / 物理ピン7 |
| 水位センサー SIG | MCP3204/MCP3208 CH0 |
| CdSセル AO | MCP3204/MCP3208 CH1 |
| ADC DIN | GPIO10 / MOSI / 物理ピン19 |
| ADC DOUT | GPIO9 / MISO / 物理ピン21 |
| ADC CLK | GPIO11 / SCLK / 物理ピン23 |
| ADC CS/SHDN | GPIO8 / CE0 / 物理ピン24 |
| LEDアノード | GPIO23から220Ω抵抗経由 |
| LEDカソード | GND |

### 必要な抵抗

- DHT11 DATAと3.3Vの間: 10kΩ
- DS18B20 DATAと3.3Vの間: 4.7kΩ
- LEDとGPIO23の間: 220Ω程度

### 実行プログラム

- センサー処理: `send_sensor_raspi.py`
- 互換エントリーポイント: `send_sensor.py`
- ローカルAPI: `main.py`

### systemd

| service | 状態 |
|---|---|
| `plant-api.service` | active |
| `plant-sensor.service` | active |

旧service名を使用していますが、内部では`send_sensor.py`から`send_sensor_raspi.py`を実行するため動作上の問題はありません。

### 最新確認値

確認時刻: 2026-06-13 11:45 JST頃

| 項目 | 値 |
|---|---:|
| 温度 | 28.6℃ |
| 湿度 | 44% |
| 養液温度 | 29.0℃ |
| 水位ADC | 2 / dry |
| CdS ADC | 3401 / bright |
| vitality | 25 |

Supabase POST `201`を確認済みです。

水位センサーを栽培キットへ設置していない状態では、`water_status=dry`やvitality 25を植物の給水状態として解釈しません。

## 3. raspberrypi2の構成

ホスト名: `raspberrypi2`
SSH接続:

```bash
ssh pi@raspberrypi2
```

Tailscale IP: `100.99.153.127`

### 配線

| 機器 | 接続 |
|---|---|
| BH1750 VCC | 3.3V |
| BH1750 GND | GND |
| BH1750 SDA | GPIO2 / 物理ピン3 |
| BH1750 SCL | GPIO3 / 物理ピン5 |
| BH1750 ADDR | GND / アドレス`0x23` |
| DS18B20 DATA | GPIO4 / 物理ピン7 |
| フロートスイッチ片側 | GPIO17 / 物理ピン11 |
| フロートスイッチもう片側 | GND |

### 抵抗

- BH1750モジュール: 通常は追加抵抗不要
- DS18B20 DATAと3.3Vの間: 4.7kΩ必須
- フロートスイッチ: GPIO17の内部プルアップを使用するため追加抵抗不要

フロートスイッチへ3.3Vや5Vは直接接続しません。

### OS設定

`/boot/firmware/config.txt`:

```ini
dtparam=i2c_arm=on
dtoverlay=w1-gpio,gpiopin=4
```

ホスト名はcloud-initを含めて`raspberrypi2`へ固定済みです。

### 実行プログラム

- センサー処理: `send_sensor_raspberrypi2.py`
- BH1750: `bh1750.py`
- DS18B20: `ds18b20.py`
- フロート: `float_switch.py`
- 専用依存関係: `requirements-raspberrypi2.txt`

### systemd

| service | 状態 |
|---|---|
| `plant-sensor-raspberrypi2.service` | enabled / active |

再起動後の自動起動とSupabase送信を確認済みです。

### 最新確認値

確認時刻: 2026-06-13 11:45 JST頃

| 項目 | 値 |
|---|---:|
| 養液温度 | 28.0℃ |
| BH1750照度 | 2049.2 lx / bright |
| フロート | water_ok |

BH1750は雨を避けるため青色蓋のタッパー内部に設置しています。値は葉面照度ではなく、容器内部の参考値として扱います。

Supabase POST `201`を確認済みです。

## 4. フロートスイッチ

GPIO17を内部プルアップ入力として使用します。

```text
スイッチ開放 → HIGH
スイッチ接触 → LOW
```

現在のコード:

```text
LOW  → low_water
HIGH → water_ok
```

実機を1秒間隔で動かし、`hi`と`lo`が切り替わることを確認済みです。

ただし、フロートの上下方向によって水あり・水不足の意味が反転します。最終的な設置方向で`LOW = 水不足`になることを確認する必要があります。

## 5. Supabase

`sensor_logs`へ次の列を追加済みです。

| 列 | 用途 |
|---|---|
| `solution_temperature` | DS18B20養液温度 |
| `light_lux` | BH1750照度 |
| `device_id` | 機体識別 |
| `location_id` | 設置場所識別 |
| `float_switch_triggered` | フロート接点状態 |
| `float_switch_state` | `low_water` / `water_ok` |

2号機にはDHTがないため、`temperature`と`humidity`はNULL許可へ変更済みです。既存データの値は変更していません。

## 6. 表示

### GitHub Pages

1号機・2号機の最新値、推移グラフ、プロジェクト概要を3ペインで表示します。

## 7. テスト状況

- Python構文チェック: 成功
- Python unit test: 22件成功
- SQLite INSERT構造確認: 成功
- GitHub Pages JavaScript構文チェック: 成功
- Supabase migration: 適用済み
- Supabase security advisor: 指摘なし
- 両PiのGit作業ツリー: クリーン
- 両Piのservice: active

## 8. 残作業

1. フロートスイッチの最終設置方向を確定する
2. `LOW = 水不足`になることを現物で確認する
3. GitHub Pagesの2機体表示をブラウザで確認する
4. `raspi`の旧service名を`plant-sensor-raspi.service`へ整理する
5. 植え替え、給水、フェルト交換などを`care_logs`へ記録する方法を整備する

## 9. 関連ファイル

- [配線資料](WIRING.md)
- [配線図](wiring.svg)
- [次の作業](NEXT_ACTIONS.md)
- [作業履歴](PROJECT_LOG.md)
- [過去の枯死・ストレス分析](HISTORICAL_STRESS_ANALYSIS_2026-06-12.md)
