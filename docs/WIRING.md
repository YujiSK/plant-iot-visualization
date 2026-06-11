# Plant IoT 配線図

![Plant IoT 配線図](wiring.svg)

## 信号配線

| 接続元 | 接続先 | Raspberry Pi |
|---|---|---|
| DHT11 `DATA` | GPIO17 | BCM 17 / 物理ピン 11 |
| DS18B20 `DATA`（黄） | GPIO4 / 1-Wire | BCM 4 / 物理ピン 7 |
| 水位センサー `SIG` | ADC `CH0` | MCP3204/MCP3208経由 |
| 照度センサー `AO` | ADC `CH1` | MCP3204/MCP3208経由 |
| ADC `DIN` | SPI0 MOSI | BCM 10 / 物理ピン 19 |
| ADC `DOUT` | SPI0 MISO | BCM 9 / 物理ピン 21 |
| ADC `CLK` | SPI0 SCLK | BCM 11 / 物理ピン 23 |
| ADC `CS/SHDN` | SPI0 CE0 | BCM 8 / 物理ピン 24 |

## 電源配線

| Raspberry Pi | 接続先 |
|---|---|
| 3.3V / 物理ピン 1 | DHT11 `VCC`、DS18B20赤線、水位センサー `VCC`、照度センサー `VCC`、ADC `VDD` / `VREF` |
| GND / 物理ピン 6 | DHT11 `GND`、DS18B20黒線、各センサー `GND`、ADC `AGND` / `DGND` |

DHT11の`DATA`と3.3Vの間には10kΩのプルアップ抵抗を接続します。
DS18B20の`DATA`（黄）と3.3Vの間には4.7kΩのプルアップ抵抗を接続します。

## DS18B20の有効化

`/boot/firmware/config.txt`へ次を追加し、Raspberry Piを再起動します。

```ini
dtoverlay=w1-gpio,gpiopin=4
```

再起動後、次のようなデバイスが見えることを確認します。

```bash
ls /sys/bus/w1/devices/28-*/w1_slave
```

## 注意事項

- GPIOとADC入力へ5Vを入力しない。
- ADC入力範囲は0Vから`VREF`まで。現在の`VREF`は3.3V。
- 全機器のGNDを共通化する。
- MCP3204とMCP3208では物理ピン番号が異なるため、使用する型番とパッケージのデータシートを確認する。
- 照度センサーのデジタル出力`DO`は使用しない。

## 図の再生成

配線図のソースは[`wiring.dot`](wiring.dot)です。Graphviz導入後に次のコマンドを実行すると[`wiring.svg`](wiring.svg)を再生成できます。

```bash
python scripts/generate_wiring_diagram.py
```
