# ADC Debug Session - 2026-06-01

> **履歴資料:** この文書は2026年6月1日のデバッグ記録です。DHT11がGPIO4に接続され、1-Wire未使用だった前提は当時のものです。現行構成は [CURRENT_STATUS_2026-06-13.md](CURRENT_STATUS_2026-06-13.md)、現行配線は [WIRING.md](WIRING.md) を参照してください。

## 目的

水位センサの出力が `0.133V` から `0.144V` 程度しか変化しない原因を、安全に切り分ける。

研究目的は高精度な水位測定ではなく、補水判断と植物状態の可視化。

## 安全方針

- Raspberry Pi GPIOは3.3V系。
- Raspberry Pi GPIOへ5Vを入れない。
- まずは全体を3.3Vで統一して確認する。
- MCP3204/MCP3208の `VDD` と `VREF` は3.3V。
- MCP3204/MCP3208は12bit ADCなので raw は `0` から `4095`。
- 電圧換算は `voltage = raw * 3.3 / 4095`。
- 5V駆動を試す場合は、センサSIG電圧をテスターで測り、3.3V以下であることを確認してからADCへ接続する。
- 電源OFF時の導通確認は人間がテスターで実施する。

## 想定配線

### Raspberry Pi

- Raspberry Pi 3.3V -> ブレッドボード + レール
- Raspberry Pi GND -> ブレッドボード - レール
- GPIO11 / SCLK -> MCP3204/MCP3208 CLK
- GPIO9 / MISO -> MCP3204/MCP3208 DOUT
- GPIO10 / MOSI -> MCP3204/MCP3208 DIN
- GPIO8 / CE0 -> MCP3204/MCP3208 CS/SHDN
- GPIO4 -> DHT11 DATA
- GPIO23 -> 220ohm -> LEDアノード
- LEDカソード -> GND

### ADC

- MCP3204/MCP3208 VDD -> 3.3V
- MCP3204/MCP3208 VREF -> 3.3V
- MCP3204/MCP3208 AGND -> GND
- MCP3204/MCP3208 DGND -> GND
- MCP3204/MCP3208 CH0 -> 水位センサ SIG
- MCP3204/MCP3208 CH1 -> 照度センサ AO

### 水位センサ

- 水位センサ VCC -> 3.3V
- 水位センサ GND -> GND
- 水位センサ SIG -> MCP3204/MCP3208 CH0

### 照度センサ

- 照度センサ VCC -> 3.3V
- 照度センサ GND -> GND
- 照度センサ AO -> MCP3204/MCP3208 CH1

### DHT11

- DHT11 VCC -> 3.3V
- DHT11 GND -> GND
- DHT11 DATA -> GPIO4
- DHT11 DATA -> 10kohm -> 3.3V

## Raspberry Pi設定

今回の構成では以下が必要。

- SPI: 必要
- I2C: 基本不要
- 1-Wire: 基本不要

DHT11はGPIO4を使うが、raspi-configの1-Wire機能とは別物。
1-Wireは主にDS18B20などで使う。

SPI有効化手順:

```bash
sudo raspi-config
```

```text
Interface Options -> SPI -> Enable
```

有効化後は再起動する。

```bash
sudo reboot
```

再起動後の確認:

```bash
ls -l /dev/spidev*
cd /home/pi/plant-iot
python3 debug_adc_channels.py
```

## 実施済み調査

- 作業ディレクトリ: `/home/pi`
- プロジェクト: `/home/pi/plant-iot`
- 関連ファイル:
  - `send_sensor.py`
  - `main.py`
  - `requirements.txt`
  - `AGENTS.md`
- 調査開始時点の `send_sensor.py` はSense HAT中心だった。
- 調査開始時点ではMCP3204/MCP3208、水位センサ、フォトレジスタADCの本番読み取りコードは未実装だった。
- MCP3008向けの `1023` 割り流用コードは見当たらなかった。
- `spidev` Python import は成功。
- `/dev/spidev*` は未検出だったため、SPI未有効の可能性が高い。
- 再起動後、実機側では `/dev/spidev0.0` と `/dev/spidev0.1` を確認。
- Codexサンドボックス内では `/dev/spidev*` が見えない場合があるため、実機デバイス確認とADC実行はサンドボックス外で行う。

## 追加済みデバッグスクリプト

新規ファイル:

```text
debug_adc_channels.py
```

内容:

- MCP3204/MCP3208向け12bit ADC読み取り。
- CH0を `water` と表示。
- CH1を `light` と表示。
- デフォルトでCH0からCH3を1秒間隔表示。
- MCP3208の場合は `--channels 8` でCH0からCH7表示。
- raw値、電圧、前回値との差分を表示。
- Ctrl+Cで安全終了。
- SPI未有効時の案内メッセージを表示。

構文チェック済み:

```bash
python3 -m py_compile debug_adc_channels.py
```

## 実行結果

### SPI有効化前

以下を実行した。

```bash
cd /home/pi/plant-iot
python3 debug_adc_channels.py
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: not found
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

ERROR: SPI device was not found. SPI may be disabled.
Enable SPI: sudo raspi-config -> Interface Options -> SPI -> Enable
```

### 再起動後

実機側で以下を確認した。

```bash
ls -l /dev/spidev*
```

結果:

```text
crw-rw---- 1 root spi 153, 0 Jun  1 09:32 /dev/spidev0.0
crw-rw---- 1 root spi 153, 1 Jun  1 09:32 /dev/spidev0.1
```

サンドボックス外で以下を実行した。

```bash
cd /home/pi/plant-iot
python3 debug_adc_channels.py
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
```

判断:

- SPI有効化は成功。
- ADC読み取りは全CH `raw=0` のため、ADC電源、VREF、GND、ADCの向き、SPI配線、CS/SHDN、読み取りコードを次に切り分ける。

### 再テスト 2026-06-01 11:43 JST

以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=   0 voltage=0.000V diff=   +0 | CH2 ch2 raw=   0 voltage=0.000V diff=   +0 | CH3 ch3 raw=   0 voltage=0.000V diff=   +0
```

補足:

- `timeout` により終了コードは `124`。これは6秒で停止したためで、ADCスクリプト自体の異常終了ではない。
- 通常のCodexサンドボックス内で `ls -l /dev/spidev0.0 /dev/spidev0.1` を実行すると、デバイスは見えなかった。
- 承認済みコマンドで実行したADCスクリプトからは `/dev/spidev0.0` と `/dev/spidev0.1` が見えている。

判断:

- 前回と同じくSPIデバイスは認識できている。
- CH0からCH3まで、複数回の読み取りで全て `raw=0` のまま。
- センサ条件による小さい変化ではなく、ADC入力またはSPI/ADC配線・電源系の根本切り分けが必要。
- 次はセンサを外した状態で、CH0またはCH1にGNDと3.3Vを直接入れて `raw=0` と `raw=4095` 付近に振れるかを確認する。

### 追加観察 2026-06-01

- センサーを入れると動かなくなる。

判断:

- センサー接続時だけ動作が崩れるなら、ADC単体やSPI有効化よりも、センサー配線や電源負荷によって3.3V、GND、VREF、SIGのどこかが崩れている可能性が高い。
- センサーのVCC/GND逆接、SIGとVCC/GNDの短絡、センサーが5V前提で3.3Vでは正しく動かない、またはセンサー接続によりADCのVREF/GNDが引きずられている可能性を優先して確認する。

次の確認:

1. センサーを外した状態で、ADCの `VDD`、`VREF`、`AGND`、`DGND` の電圧と導通を確認する。
2. センサーを外した状態で、CH0またはCH1にGNDを入れて `raw=0`、3.3Vを入れて `raw=4095` 付近になるか確認する。
3. センサー単体で、VCC-GND間が短絡していないか確認する。
4. センサー単体を3.3Vで動かし、SIG-GND間の電圧をテスターで測る。
5. 5V駆動を試す場合は、SIGが3.3Vを超えないことをテスターで確認してからADCへ接続する。

### 再テスト 2026-06-01 11:47 JST

ADCを再度テストした。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=4093 voltage=3.298V diff=   +0 | CH1 light raw=  33 voltage=0.027V diff=   +0 | CH2 ch2 raw=  43 voltage=0.035V diff=   +0 | CH3 ch3 raw=  47 voltage=0.038V diff=   +0
CH0 water raw=4095 voltage=3.300V diff=   +2 | CH1 light raw=  44 voltage=0.035V diff=  +11 | CH2 ch2 raw=  47 voltage=0.038V diff=   +4 | CH3 ch3 raw=  59 voltage=0.048V diff=  +12
CH0 water raw=4087 voltage=3.294V diff=   -8 | CH1 light raw=  69 voltage=0.056V diff=  +25 | CH2 ch2 raw=  94 voltage=0.076V diff=  +47 | CH3 ch3 raw= 119 voltage=0.096V diff=  +60
CH0 water raw=4086 voltage=3.293V diff=   -1 | CH1 light raw= 122 voltage=0.098V diff=  +53 | CH2 ch2 raw= 130 voltage=0.105V diff=  +36 | CH3 ch3 raw= 163 voltage=0.131V diff=  +44
CH0 water raw=4090 voltage=3.296V diff=   +4 | CH1 light raw= 138 voltage=0.111V diff=  +16 | CH2 ch2 raw= 156 voltage=0.126V diff=  +26 | CH3 ch3 raw= 199 voltage=0.160V diff=  +36
CH0 water raw=4093 voltage=3.298V diff=   +3 | CH1 light raw= 146 voltage=0.118V diff=   +8 | CH2 ch2 raw= 166 voltage=0.134V diff=  +10 | CH3 ch3 raw= 210 voltage=0.169V diff=  +11
```

判断:

- CH0は `raw=4086` から `4095`、`3.293V` から `3.300V` 付近で、ADCの上限付近まで読めている。
- 少なくともCH0のADC読み取り経路は反応している。
- CH1からCH3は低い値だが、0固定ではなく変化している。
- 前回の全CH `raw=0` とは状態が変わっている。配線、センサー接続状態、CH0に3.3V相当が入っているかを実物側で確認する。

### DHT11温湿度テスト 2026-06-01

サンドボックス内ではGPIOにアクセスできず、以下で失敗した。

```text
Unable to open chip: gpiochip0
RuntimeError: Timed out waiting for PulseIn message. Make sure libgpiod is installed.
```

権限付きで以下を実行した。

```bash
cd /home/pi/plant-iot
python3 debug_dht11.py --retries 5 --interval 2
```

結果:

```text
DHT11 debug
DATA GPIO: BCM 4
Expected wiring: VCC=3.3V, GND=GND, DATA=GPIO4, DATA pull-up=10kohm to 3.3V

attempt=1 RETRY: Checksum did not validate. Try again.
attempt=2 RETRY: A full buffer was not returned. Try again.
attempt=3 RETRY: Checksum did not validate. Try again.
attempt=4 RETRY: A full buffer was not returned. Try again.
attempt=5 temperature=29.9C humidity=52.0%
```

判断:

- DHT11はリトライが多いが、5回目で温度 `29.9C`、湿度 `52.0%` を取得できた。
- DHT11の通信は不安定だが、配線またはライブラリが完全に動いていない状態ではない。
- 安定化するにはDATAの10kohmプルアップ、配線の接触、GPIO4、DHT11の読み取り間隔を確認する。

### ADC再テスト 2026-06-01 11:48 JST

以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw= 164 voltage=0.132V diff=   +0 | CH1 light raw=1830 voltage=1.475V diff=   +0 | CH2 ch2 raw=4086 voltage=3.293V diff=   +0 | CH3 ch3 raw= 120 voltage=0.097V diff=   +0
CH0 water raw= 163 voltage=0.131V diff=   -1 | CH1 light raw=1844 voltage=1.486V diff=  +14 | CH2 ch2 raw=4086 voltage=3.293V diff=   +0 | CH3 ch3 raw= 122 voltage=0.098V diff=   +2
CH0 water raw= 163 voltage=0.131V diff=   +0 | CH1 light raw=1942 voltage=1.565V diff=  +98 | CH2 ch2 raw=4086 voltage=3.293V diff=   +0 | CH3 ch3 raw= 114 voltage=0.092V diff=   -8
CH0 water raw= 163 voltage=0.131V diff=   +0 | CH1 light raw=1995 voltage=1.608V diff=  +53 | CH2 ch2 raw=4095 voltage=3.300V diff=   +9 | CH3 ch3 raw= 121 voltage=0.098V diff=   +7
CH0 water raw= 163 voltage=0.131V diff=   +0 | CH1 light raw=2027 voltage=1.633V diff=  +32 | CH2 ch2 raw=4086 voltage=3.293V diff=   -9 | CH3 ch3 raw= 124 voltage=0.100V diff=   +3
CH0 water raw= 162 voltage=0.131V diff=   -1 | CH1 light raw=2057 voltage=1.658V diff=  +30 | CH2 ch2 raw=4094 voltage=3.299V diff=   +8 | CH3 ch3 raw= 115 voltage=0.093V diff=   -9
```

判断:

- CH0は `raw=162` から `164`、約 `0.131V` で安定している。
- CH1は `raw=1830` から `2057`、約 `1.475V` から `1.658V` へ上昇している。
- CH2は `raw=4086` から `4095`、ほぼ `3.3V` に張り付いている。
- CH3は `raw=114` から `124`、約 `0.09V` から `0.10V`。
- ADCは複数チャンネルで値を読めているため、SPI/ADC全体が完全に死んでいる状態ではない。
- CH0の水位センサ相当は以前の `0.133V` 付近と整合する。水位変化を見たい場合は、CH0のセンサー状態を変えながらこの値が動くかを見る。
- CH2は3.3V相当なので、CH2が意図せず3.3Vへ接続されていないか、または浮いて上限に寄っていないか確認する。

### 照度センサ暗状態テスト 2026-06-01 11:49 JST

照度センサに指を置いて暗くした状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw= 164 voltage=0.132V diff=   +0 | CH1 light raw= 369 voltage=0.297V diff=   +0 | CH2 ch2 raw=4095 voltage=3.300V diff=   +0 | CH3 ch3 raw=  39 voltage=0.031V diff=   +0
CH0 water raw= 162 voltage=0.131V diff=   -2 | CH1 light raw= 358 voltage=0.288V diff=  -11 | CH2 ch2 raw=4094 voltage=3.299V diff=   -1 | CH3 ch3 raw=  34 voltage=0.027V diff=   -5
CH0 water raw= 163 voltage=0.131V diff=   +1 | CH1 light raw= 352 voltage=0.284V diff=   -6 | CH2 ch2 raw=4094 voltage=3.299V diff=   +0 | CH3 ch3 raw=  18 voltage=0.015V diff=  -16
CH0 water raw= 163 voltage=0.131V diff=   +0 | CH1 light raw= 291 voltage=0.235V diff=  -61 | CH2 ch2 raw=4095 voltage=3.300V diff=   +1 | CH3 ch3 raw=   4 voltage=0.003V diff=  -14
CH0 water raw= 164 voltage=0.132V diff=   +1 | CH1 light raw= 354 voltage=0.285V diff=  +63 | CH2 ch2 raw=4086 voltage=3.293V diff=   -9 | CH3 ch3 raw=   4 voltage=0.003V diff=   +0
CH0 water raw= 164 voltage=0.132V diff=   +0 | CH1 light raw= 307 voltage=0.247V diff=  -47 | CH2 ch2 raw=4091 voltage=3.297V diff=   +5 | CH3 ch3 raw=   0 voltage=0.000V diff=   -4
```

判断:

- 直前の通常状態ではCH1が `raw=1830` から `2057`、約 `1.475V` から `1.658V` だった。
- 暗状態ではCH1が `raw=291` から `369`、約 `0.235V` から `0.297V` まで下がった。
- CH1の照度センサ入力は明暗に反応している。
- 照度センサは本番統合候補として使える可能性が高い。

### CH2 3.3V直結解除後テスト 2026-06-01 11:50 JST

CH2に3.3Vから直接刺していた線を抜いた状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw= 164 voltage=0.132V diff=   +0 | CH1 light raw=1773 voltage=1.429V diff=   +0 | CH2 ch2 raw= 167 voltage=0.135V diff=   +0 | CH3 ch3 raw= 202 voltage=0.163V diff=   +0
CH0 water raw= 163 voltage=0.131V diff=   -1 | CH1 light raw=1814 voltage=1.462V diff=  +41 | CH2 ch2 raw= 135 voltage=0.109V diff=  -32 | CH3 ch3 raw= 179 voltage=0.144V diff=  -23
CH0 water raw= 164 voltage=0.132V diff=   +1 | CH1 light raw=2033 voltage=1.638V diff= +219 | CH2 ch2 raw= 130 voltage=0.105V diff=   -5 | CH3 ch3 raw= 156 voltage=0.126V diff=  -23
CH0 water raw= 165 voltage=0.133V diff=   +1 | CH1 light raw=2060 voltage=1.660V diff=  +27 | CH2 ch2 raw= 124 voltage=0.100V diff=   -6 | CH3 ch3 raw= 149 voltage=0.120V diff=   -7
CH0 water raw= 163 voltage=0.131V diff=   -2 | CH1 light raw=2041 voltage=1.645V diff=  -19 | CH2 ch2 raw=  97 voltage=0.078V diff=  -27 | CH3 ch3 raw= 135 voltage=0.109V diff=  -14
CH0 water raw= 162 voltage=0.131V diff=   -1 | CH1 light raw=2085 voltage=1.680V diff=  +44 | CH2 ch2 raw= 104 voltage=0.084V diff=   +7 | CH3 ch3 raw= 122 voltage=0.098V diff=  -13
```

判断:

- 直前までCH2は `raw=4086` から `4095`、約 `3.3V` に張り付いていた。
- CH2の3.3V直結を外すと、CH2は `raw=97` から `167`、約 `0.078V` から `0.135V` まで下がった。
- CH2の上限張り付きは3.3V直結が原因と見てよい。
- CH0は引き続き約 `0.131V` から `0.133V`。
- CH1は通常明るさで約 `1.43V` から `1.68V` に戻っており、暗状態テストとの差が出ている。

### 水位センサ水没テスト 2026-06-01 11:52 JST

水位センサを水に入れた状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw= 170 voltage=0.137V diff=   +0 | CH1 light raw=1869 voltage=1.506V diff=   +0 | CH2 ch2 raw= 189 voltage=0.152V diff=   +0 | CH3 ch3 raw= 237 voltage=0.191V diff=   +0
CH0 water raw= 169 voltage=0.136V diff=   -1 | CH1 light raw=1874 voltage=1.510V diff=   +5 | CH2 ch2 raw= 187 voltage=0.151V diff=   -2 | CH3 ch3 raw= 244 voltage=0.197V diff=   +7
CH0 water raw= 169 voltage=0.136V diff=   +0 | CH1 light raw=1873 voltage=1.509V diff=   -1 | CH2 ch2 raw= 191 voltage=0.154V diff=   +4 | CH3 ch3 raw= 246 voltage=0.198V diff=   +2
CH0 water raw= 170 voltage=0.137V diff=   +1 | CH1 light raw=1867 voltage=1.505V diff=   -6 | CH2 ch2 raw= 193 voltage=0.156V diff=   +2 | CH3 ch3 raw= 254 voltage=0.205V diff=   +8
CH0 water raw= 171 voltage=0.138V diff=   +1 | CH1 light raw=1882 voltage=1.517V diff=  +15 | CH2 ch2 raw= 195 voltage=0.157V diff=   +2 | CH3 ch3 raw= 245 voltage=0.197V diff=   -9
CH0 water raw= 170 voltage=0.137V diff=   -1 | CH1 light raw=1874 voltage=1.510V diff=   -8 | CH2 ch2 raw= 196 voltage=0.158V diff=   +1 | CH3 ch3 raw= 252 voltage=0.203V diff=   +7
```

判断:

- 水没前のCH0は `raw=162` から `165`、約 `0.131V` から `0.133V`。
- 水没時のCH0は `raw=169` から `171`、約 `0.136V` から `0.138V`。
- 水に入れるとCH0は少し上がるが、変化幅は `raw` で約 `+5` から `+9`、電圧で約 `+0.004V` から `+0.007V` 程度。
- 3.3V駆動では水位センサ出力の変化がかなり小さい。
- 補水判断に使うなら、しきい値判定はかなり慎重にする必要がある。センサ面の浸かり方、接触、5V前提センサかどうかを追加確認する。

### 水位センサ拭き取り後テスト 2026-06-01 12:06 JST

水位センサを水から出して拭き取った状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1783 voltage=1.437V diff=   +0 | CH2 ch2 raw=   6 voltage=0.005V diff=   +0 | CH3 ch3 raw=  12 voltage=0.010V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1725 voltage=1.390V diff=  -58 | CH2 ch2 raw=   0 voltage=0.000V diff=   -6 | CH3 ch3 raw=   0 voltage=0.000V diff=  -12
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1819 voltage=1.466V diff=  +94 | CH2 ch2 raw=   4 voltage=0.003V diff=   +4 | CH3 ch3 raw=   7 voltage=0.006V diff=   +7
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1841 voltage=1.484V diff=  +22 | CH2 ch2 raw=   2 voltage=0.002V diff=   -2 | CH3 ch3 raw=   6 voltage=0.005V diff=   -1
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1947 voltage=1.569V diff= +106 | CH2 ch2 raw=  12 voltage=0.010V diff=  +10 | CH3 ch3 raw=  13 voltage=0.010V diff=   +7
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2014 voltage=1.623V diff=  +67 | CH2 ch2 raw=  27 voltage=0.022V diff=  +15 | CH3 ch3 raw=  30 voltage=0.024V diff=  +17
```

判断:

- 水没時のCH0は `raw=169` から `171`、約 `0.136V` から `0.138V`。
- 拭き取り後のCH0は全て `raw=0`、`0.000V`。
- 単なる乾燥戻りというより、CH0のSignalがGND側に落ちた、または拭き取り・取り外し時にCH0配線やセンサ接続状態が変わった可能性がある。
- CH1は通常明るさで `raw=1725` から `2014`、約 `1.39V` から `1.62V` で、照度センサは引き続き反応している。

次の確認:

1. 水位センサの `VCC`、`GND`、`Signal` が抜けかけていないか確認する。
2. テスターで水位センサの `Signal-GND` を測り、ADCのCH0値と一致するか確認する。
3. CH0に一時的に3.3Vを入れて、ADCが `raw=4095` 付近まで振れるか再確認する。

### 水位センサ再水没テスト 2026-06-01 12:07 JST

水位センサを再度水に入れた状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=2201 voltage=1.774V diff=   +0 | CH1 light raw=1973 voltage=1.590V diff=   +0 | CH2 ch2 raw=  16 voltage=0.013V diff=   +0 | CH3 ch3 raw=  21 voltage=0.017V diff=   +0
CH0 water raw=2201 voltage=1.774V diff=   +0 | CH1 light raw=1980 voltage=1.596V diff=   +7 | CH2 ch2 raw=   6 voltage=0.005V diff=  -10 | CH3 ch3 raw=   8 voltage=0.006V diff=  -13
CH0 water raw=2180 voltage=1.757V diff=  -21 | CH1 light raw=1975 voltage=1.592V diff=   -5 | CH2 ch2 raw=   1 voltage=0.001V diff=   -5 | CH3 ch3 raw=   7 voltage=0.006V diff=   -1
CH0 water raw=2182 voltage=1.758V diff=   +2 | CH1 light raw=1982 voltage=1.597V diff=   +7 | CH2 ch2 raw=   5 voltage=0.004V diff=   +4 | CH3 ch3 raw=   0 voltage=0.000V diff=   -7
CH0 water raw=2177 voltage=1.754V diff=   -5 | CH1 light raw=1979 voltage=1.595V diff=   -3 | CH2 ch2 raw=   0 voltage=0.000V diff=   -5 | CH3 ch3 raw=   5 voltage=0.004V diff=   +5
CH0 water raw=2177 voltage=1.754V diff=   +0 | CH1 light raw=1980 voltage=1.596V diff=   +1 | CH2 ch2 raw=   5 voltage=0.004V diff=   +5 | CH3 ch3 raw=   5 voltage=0.004V diff=   +0
```

判断:

- 拭き取り後のCH0は全て `raw=0`、`0.000V` だった。
- 再水没時のCH0は `raw=2177` から `2201`、約 `1.754V` から `1.774V` まで上がった。
- 水位センサは水に対して明確に反応している。
- 以前の水没時に約 `0.136V` しか出なかった状態とは大きく異なるため、センサ面の濡れ方、接触、配線状態、または水への浸け方で出力が大きく変わる。
- 実運用では、乾燥/拭き取り時を `0V` 付近、水没時を `1.7V` 付近として扱える可能性がある。ただし浅い水位や中間状態の追加測定が必要。

### 水位センサ再拭き取り後テスト 2026-06-01 12:09 JST

水位センサを水から出して拭き取った状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1989 voltage=1.603V diff=   +0 | CH2 ch2 raw=  93 voltage=0.075V diff=   +0 | CH3 ch3 raw= 118 voltage=0.095V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1982 voltage=1.597V diff=   -7 | CH2 ch2 raw=  98 voltage=0.079V diff=   +5 | CH3 ch3 raw= 118 voltage=0.095V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1989 voltage=1.603V diff=   +7 | CH2 ch2 raw= 108 voltage=0.087V diff=  +10 | CH3 ch3 raw= 124 voltage=0.100V diff=   +6
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1888 voltage=1.521V diff= -101 | CH2 ch2 raw=  94 voltage=0.076V diff=  -14 | CH3 ch3 raw= 119 voltage=0.096V diff=   -5
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1945 voltage=1.567V diff=  +57 | CH2 ch2 raw=  95 voltage=0.077V diff=   +1 | CH3 ch3 raw= 131 voltage=0.106V diff=  +12
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=1926 voltage=1.552V diff=  -19 | CH2 ch2 raw= 105 voltage=0.085V diff=  +10 | CH3 ch3 raw= 119 voltage=0.096V diff=  -12
```

判断:

- 直前の再水没時CH0は `raw=2177` から `2201`、約 `1.754V` から `1.774V`。
- 再拭き取り後CH0は全て `raw=0`、`0.000V`。
- 水没と拭き取りでCH0は明確にON/OFF的に切り替わっている。
- この状態なら、水あり/なしの二値判定はしやすい。中間水位の測定を追加すれば、しきい値をより安全に決められる。

### 水位センサ浅水テスト 2026-06-01 12:10 JST

水位センサを水にちょびっとだけつけた状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=1451 voltage=1.169V diff=   +0 | CH1 light raw=1999 voltage=1.611V diff=   +0 | CH2 ch2 raw=   9 voltage=0.007V diff=   +0 | CH3 ch3 raw=  19 voltage=0.015V diff=   +0
CH0 water raw=1427 voltage=1.150V diff=  -24 | CH1 light raw=1994 voltage=1.607V diff=   -5 | CH2 ch2 raw=   9 voltage=0.007V diff=   +0 | CH3 ch3 raw=  14 voltage=0.011V diff=   -5
CH0 water raw=1435 voltage=1.156V diff=   +8 | CH1 light raw=2000 voltage=1.612V diff=   +6 | CH2 ch2 raw=  14 voltage=0.011V diff=   +5 | CH3 ch3 raw=  24 voltage=0.019V diff=  +10
CH0 water raw=1441 voltage=1.161V diff=   +6 | CH1 light raw=1995 voltage=1.608V diff=   -5 | CH2 ch2 raw=  22 voltage=0.018V diff=   +8 | CH3 ch3 raw=  45 voltage=0.036V diff=  +21
CH0 water raw=1494 voltage=1.204V diff=  +53 | CH1 light raw=1998 voltage=1.610V diff=   +3 | CH2 ch2 raw=  37 voltage=0.030V diff=  +15 | CH3 ch3 raw=  59 voltage=0.048V diff=  +14
CH0 water raw=1872 voltage=1.509V diff= +378 | CH1 light raw=1999 voltage=1.611V diff=   +1 | CH2 ch2 raw=  59 voltage=0.048V diff=  +22 | CH3 ch3 raw=  78 voltage=0.063V diff=  +19
```

判断:

- 拭き取り後のCH0は `raw=0`、`0.000V`。
- 深めの再水没時CH0は `raw=2177` から `2201`、約 `1.754V` から `1.774V`。
- 浅く少しだけ水につけた状態ではCH0が `raw=1427` から `1872`、約 `1.150V` から `1.509V`。
- 浅水は乾燥と深水の中間値として取れている。
- 最後に `raw=1872` まで上がっているため、浸かる面積、水の広がり、保持時間によって値が増える。
- 仮のしきい値としては、乾燥 `raw=0`、浅水 `raw=1400+`、深水 `raw=2200` 前後という分離が見えている。追加で数回再現確認してから本番しきい値を決める。

### 水位センサ水膜テスト 2026-06-01 12:11 JST

水から出したあと、センサ面にまんべんなく水を塗った状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=2380 voltage=1.918V diff=   +0 | CH1 light raw=1944 voltage=1.567V diff=   +0 | CH2 ch2 raw=  10 voltage=0.008V diff=   +0 | CH3 ch3 raw=  15 voltage=0.012V diff=   +0
CH0 water raw=2390 voltage=1.926V diff=  +10 | CH1 light raw=1942 voltage=1.565V diff=   -2 | CH2 ch2 raw=  14 voltage=0.011V diff=   +4 | CH3 ch3 raw=  17 voltage=0.014V diff=   +2
CH0 water raw=2391 voltage=1.927V diff=   +1 | CH1 light raw=2002 voltage=1.613V diff=  +60 | CH2 ch2 raw=  24 voltage=0.019V diff=  +10 | CH3 ch3 raw=  40 voltage=0.032V diff=  +23
CH0 water raw=2390 voltage=1.926V diff=   -1 | CH1 light raw=2020 voltage=1.628V diff=  +18 | CH2 ch2 raw=  43 voltage=0.035V diff=  +19 | CH3 ch3 raw=  54 voltage=0.044V diff=  +14
CH0 water raw=2390 voltage=1.926V diff=   +0 | CH1 light raw=2010 voltage=1.620V diff=  -10 | CH2 ch2 raw=  92 voltage=0.074V diff=  +49 | CH3 ch3 raw= 108 voltage=0.087V diff=  +54
CH0 water raw=2371 voltage=1.911V diff=  -19 | CH1 light raw=2009 voltage=1.619V diff=   -1 | CH2 ch2 raw= 113 voltage=0.091V diff=  +21 | CH3 ch3 raw= 149 voltage=0.120V diff=  +41
```

判断:

- 水膜状態のCH0は `raw=2371` から `2391`、約 `1.911V` から `1.927V`。
- 深め水没時の `raw=2177` から `2201`、約 `1.754V` から `1.774V` より高い。
- センサ面に水膜がまんべんなくあると、平行銅線間の導通が強くなり、出力が大きくなる。
- このセンサは「水位の深さ」だけでなく「センサ面の濡れ面積」と「水膜のつながり」に強く反応する。
- 補水判断では、瞬間値だけでなく数回平均やヒステリシスを入れた方がよい。

### 水膜拭き取り後テスト 2026-06-01 12:12 JST

水膜状態のあと、センサ面を拭き取った状態で、以下を実行した。

```bash
cd /home/pi/plant-iot
timeout 6s python3 debug_adc_channels.py --channels 4
```

結果:

```text
MCP3204/MCP3208 ADC debug
SPI device files: /dev/spidev0.0, /dev/spidev0.1
Opening SPI bus=0, device=0
If opening fails, enable SPI with: sudo raspi-config -> Interface Options -> SPI
CH0 water_level: dry / slightly wet / deeply dipped should change raw/voltage
CH1 light: cover by hand / shine phone light should change raw/voltage

CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2033 voltage=1.638V diff=   +0 | CH2 ch2 raw= 106 voltage=0.085V diff=   +0 | CH3 ch3 raw= 136 voltage=0.110V diff=   +0
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2000 voltage=1.612V diff=  -33 | CH2 ch2 raw= 104 voltage=0.084V diff=   -2 | CH3 ch3 raw= 140 voltage=0.113V diff=   +4
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2040 voltage=1.644V diff=  +40 | CH2 ch2 raw= 103 voltage=0.083V diff=   -1 | CH3 ch3 raw= 130 voltage=0.105V diff=  -10
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2038 voltage=1.642V diff=   -2 | CH2 ch2 raw= 102 voltage=0.082V diff=   -1 | CH3 ch3 raw= 134 voltage=0.108V diff=   +4
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2035 voltage=1.640V diff=   -3 | CH2 ch2 raw= 103 voltage=0.083V diff=   +1 | CH3 ch3 raw= 132 voltage=0.106V diff=   -2
CH0 water raw=   0 voltage=0.000V diff=   +0 | CH1 light raw=2027 voltage=1.633V diff=   -8 | CH2 ch2 raw= 107 voltage=0.086V diff=   +4 | CH3 ch3 raw= 127 voltage=0.102V diff=   -5
```

判断:

- 水膜状態のCH0は `raw=2371` から `2391`、約 `1.911V` から `1.927V`。
- 水膜を拭き取るとCH0は全て `raw=0`、`0.000V` に戻った。
- 水膜あり/拭き取りのON/OFFは再現性がある。
- 乾燥判定と濡れ判定は十分分離できそう。

## 再起動後の判断基準

- CH0 rawがほぼ変わらない:
  - 配線、VCC、GND、SIG、センサ感度、3.3V駆動不足を疑う。
- CH1は変わるがCH0だけ変わらない:
  - 水位センサまたはCH0配線を疑う。
- 全CHが0または4095付近:
  - SPI配線、VREF、VDD、GND、読み取りコードを疑う。
- CH0とCH1が両方変化する:
  - ADCとSPIは概ね正常。
- 電圧が0.133Vから0.144V程度しか変わらない:
  - 水位センサの出力が弱い。
  - 濡れている面積が小さい。
  - 5V前提センサの可能性。

## 当時の次アクション（完了済み）

1. ADCの向きとピン番号を実物の型番、切り欠き、ドット位置で確認する。
2. ADCの `VDD`、`VREF`、`AGND`、`DGND` が3.3V/GNDに正しくつながっているか確認する。
3. `CS/SHDN`、`CLK`、`DOUT`、`DIN` の配線がMCP3204/MCP3208の実ピンに合っているか確認する。
4. CH0またはCH1に一時的に3.3V、GNDを入れて、rawが `4095` 付近または `0` 付近になるか確認する。
5. CH0水位センサを乾燥、少し濡らす、深く浸す状態で比較する。
6. CH1照度センサを手で覆う、スマホライトを当てる状態で比較する。
7. 値が確認できてから `send_sensor.py` やFastAPI/Supabase送信処理への統合を検討する。
