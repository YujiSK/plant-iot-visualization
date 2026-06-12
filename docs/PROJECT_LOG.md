# PROJECT_LOG

## 2026-05-13

### 完了したこと

- Codex CLI のセッション引き継ぎ運用を導入
- `AGENTS.md` / `docs/PROJECT_LOG.md` / `docs/NEXT_ACTIONS.md` の運用方針を整理

### 変更したファイル

- `AGENTS.md`
- `docs/PROJECT_LOG.md`
- `docs/NEXT_ACTIONS.md`

### 判断した設計方針

- Codex の会話履歴だけに依存せず、リポジトリ内の Markdown に作業履歴と次アクションを残す
- 新しいセッション開始時は読み取り専用で状態確認し、勝手にファイル変更しない
- セッション終了前に作業ログと次アクションを更新する
- 未コミットの既存差分や秘密情報を不用意に触らない

### 動作確認

- `git status --short` を確認
- 対象3ファイルが存在しないことを確認
- 引き継ぎ運用ファイルを新規作成

### 注意点

- まだコミットはしていない
- 作成前から既存の未コミット変更があるため、今後の作業では差分の所有範囲に注意する

## 2026-05-18

### センサー補正まわり

#### 確認したこと

- 記録前に温度補正がかかっているか確認した
- `send_sensor.py` では Sense HAT の生温度に `TEMP_OFFSET` を足した値を、ローカルAPIとSupabaseへ送信している
- `.env` に `TEMP_OFFSET` が未設定の場合、デフォルトで `-8.0` が使われる
- 湿度は当初、補正なしで記録されていた
- バジルの目安として、適正温度はおおむね 20-30℃、育ちやすい温度は 25-28℃前後と整理した
- バジルの適正湿度はおおむね 40-70%、安定域は 50-60%前後と整理した

#### 湿度ログ確認

- ローカルDB `data.db` の `sensor_logs` から湿度ログを確認した
- 最新ログは `2026-05-18 00:27:33`、湿度 `25.1%`
- 全体件数は `1941` 件
- 記録期間は `2026-04-25 16:29:22` から `2026-05-18 00:27:33`
- 全体の湿度は最小 `19.2%`、平均 `29.9%`、最大 `65.0%`
- 直近は 24-35% 程度が多く、バジルの目安より乾燥気味だった

#### 変更したこと

- 湿度も温度と同様に記録前補正をかけるようにした
- `send_sensor.py` に `HUMIDITY_OFFSET` を追加した
- `HUMIDITY_OFFSET` は `.env` で管理し、未設定時のデフォルトは `15.0`
- `raw_humidity + HUMIDITY_OFFSET` を補正後湿度として、ローカルAPIとSupabaseへ送信するようにした
- 送信ログに `raw_humidity` と `corrected_humidity` を出すようにした
- `.env` に `HUMIDITY_OFFSET=15.0` を追加した
- `README.md` の `.env` 例にも `HUMIDITY_OFFSET=15.0` を追加した

#### 動作確認

- `python3 -m py_compile send_sensor.py` を実行し、構文チェックOK
- `python3 -m unittest test_vitality.py` を実行し、既存テストOK

#### 注意点

- `plant-sensor.service` の再起動は `sudo` のパスワード要求により未実施
- 実際の常駐センサー送信に反映するには `sudo systemctl restart plant-sensor.service` が必要
- `git status --short` 上、作業前から複数の未コミット変更や未追跡ファイルがあるため、差分の所有範囲に注意する

### 完了したこと

- Flutter管理支援アプリの最小実装を追加
- sensor_logs 最新1件を表示するFlutter画面を追加
- care_logs に watered / moved / checked / memo を記録する実装を追加
- care_logs 作成用SQLを supabase_care_logs.sql として追加

### 変更したファイル

- supabase_care_logs.sql
- lutter_app/pubspec.yaml
- lutter_app/lib/main.dart
- lutter_app/README.md

### 注意点

- Raspberry Pi環境にはFlutter/Dart CLIがないため、Flutterのビルド検証は未実施
- supabase_care_logs.sql はまだSupabaseへ適用していない
- 公開クライアントにはanon keyのみを使い、service_role keyは置かない

## 2026-06-02

### Sense HAT から現配線への移行方針

#### 判断したこと

- 最初は Sense HAT を使って始めた経緯は、Git 履歴と README / PROJECT_LOG に残す。
- 現在の実行構成は Sense HAT ではなく、DHT11 + MCP3204/MCP3208 ADC を前提にする。
- DHT11 には Sense HAT 用の `TEMP_OFFSET` / `HUMIDITY_OFFSET` を流用しない。
- いったん `_OFFSET` 補正は使わず、DHT11 の生値をそのまま記録する。

#### 変更したこと

- `send_sensor.py` から Sense HAT 依存を外し、DHT11 と ADC CH0/CH1 を読む構成へ変更した。
- `main.py` に水位・照度の任意カラムを追加し、SQLite は起動時に既存DBへ安全に `ALTER TABLE ADD COLUMN` するようにした。
- Supabase 用に `supabase_sensor_logs_adc_migration.sql` を追加した。
- Supabase 側に新カラムが未適用でも、温湿度ログだけは継続できるよう、ADCフィールドなしでリトライする処理を追加した。
- `requirements.txt` から `sense-hat` を外し、現在使う `spidev` / GPIO 関連パッケージを明示した。
- README と AGENTS の構成説明を現配線前提に更新した。

#### 注意点

- Supabase に水位・照度を保存するには `supabase_sensor_logs_adc_migration.sql` の適用が必要。
- `plant-api.service` と `plant-sensor.service` は pi ユーザー所有プロセスを終了し、systemd の自動再起動で新コードを読み込ませた。
- `plant-sensor.service` の `/etc/systemd/system` 側定義更新と `daemon-reload` は sudo パスワード要求により未実施。リポジトリ内の `plant-sensor.service` は更新済み。
- `docs/index.html` の水位・照度表示追加は未実施。

#### 動作確認

- `python -m py_compile main.py send_sensor.py vitality.py debug_adc_channels.py debug_dht11.py` OK。
- `python -m unittest test_vitality.py` OK。
- `plant-sensor.service` は DHT11 + ADC 構成で起動し、ローカルAPIへのPOSTが `200` になった。
- `/latest` に `source=dht11-mcp3204`、`water_raw`、`water_status`、`light_raw`、`light_status` が入ることを確認した。
- Supabase は水位・照度カラム未追加のためADC付きPOSTは `400`。温湿度のみのリトライは `201` で成功した。

### Supabase 側の反映

#### 適用したこと

- Supabase project `plant-iot-visualization` に migration `add_adc_fields_to_sensor_logs` を適用した。
- `public.sensor_logs` に `water_raw`、`water_voltage`、`water_status`、`light_raw`、`light_voltage`、`light_status` を追加した。
- `sensor_logs` の重複していた anon SELECT / INSERT RLS policy を整理した。
- `care_logs` の anon INSERT policy を `action_type` 制約付きに整理した。
- `care_logs.sensor_log_id` 用 index `care_logs_sensor_log_id_idx` を追加した。
- `public.rls_auto_enable()` の anon / authenticated / public 実行権限を revoke した。

#### 動作確認

- Raspberry Pi の `send_sensor.py` から Supabase へのADCフィールド付きPOSTが `201` で成功した。
- 最新Supabase行に `source=dht11-mcp3204`、`water_raw`、`light_raw` が保存されていることを確認した。
- Supabase security advisor は警告なし。
- Supabase performance advisor は追加直後の `care_logs_sensor_log_id_idx` が未使用 index として INFO を出すのみ。

## 2026-06-08

### 表示の現構成対応

#### 変更したこと

- `docs/index.html` のGitHub Pages表示から気圧タイルを外し、水位と照度を表示するようにした。
- GitHub Pages のSupabase取得対象を `pressure` から `water_raw` / `water_status` / `light_raw` / `light_status` へ切り替えた。
- デモ表示も DHT11 + MCP3204/MCP3208 の現構成に合わせた。
- Flutter管理画面の最新状態カードも気圧ではなく水位・照度を表示するようにした。
- `docs/NEXT_ACTIONS.md` から完了済みのGitHub Pages水位・照度表示追加を外した。

#### 注意点

- Flutter SDK はRaspberry Pi環境にないため、Flutter側のビルド検証は未実施。
- `care_logs` は既存スキーマ維持のため、記録時スナップショットは従来通り温度・湿度・気圧互換カラム中心のまま。
- `/etc/systemd/system/plant-sensor.service` にリポジトリ内のservice定義を反映し、`daemon-reload` 済み。
- `systemctl status plant-sensor.service --no-pager -l` で表示名が `Plant IoT DHT11 and ADC Sensor Sender` になったことを確認した。
- `journalctl -u plant-sensor.service -n 20 --no-pager -l` でローカルAPI `status=200`、Supabase `201` の送信継続を確認した。

### 再起動なしの手動送信

#### 変更したこと

- `send_sensor.py` が `SIGUSR1` を受けたら待機を中断し、手動送信を試行するようにした。
- `plant-sensor.service` に `ExecReload=/bin/kill -USR1 $MAINPID` を追加し、`sudo systemctl reload plant-sensor.service` で手動送信できるようにした。
- 直近送信から `MANUAL_SEND_MIN_INTERVAL_SECONDS` 秒以内の手動送信はスキップし、誤操作による重複行を避けるようにした。
- 通常送信は前回送信からの相対間隔ではなく、`SENSOR_INTERVAL_SECONDS=300` の場合に 00/05/10/15/... 分へ揃うようにした。
- 手動送信直後など、通常送信境界で直近送信から `MANUAL_SEND_MIN_INTERVAL_SECONDS` 秒以内の場合は通常送信もスキップするようにした。

#### 注意点

- `plant-sensor.service` の `ExecReload` 追加は `/etc/systemd/system/plant-sensor.service` へ反映し、`daemon-reload` 済み。
- 時刻境界揃えの変更を常駐プロセスへ読み込ませるため、ユーザーが `sudo systemctl restart plant-sensor.service` を実行済み。
- `journalctl -u plant-sensor.service -n 30 --no-pager -l` で `next regular send in 251.9s` を確認し、08:05:00 付近の次回送信待ちになっていることを確認した。

### GitHub Pages アドバイス表示

#### 変更したこと

- `docs/index.html` に総合アドバイスとセンサー別アドバイスを追加した。
- 温度、湿度、水位ADC、水位状態、照度ADC、照度状態、`vitality_score` に基づくコメントを生成するようにした。
- 表示は情報過多を避けるため、総合メッセージ1件と詳細アドバイス最大3件に制限した。
- Supabase取得対象に `water_voltage` / `light_voltage` も含め、今後の表示拡張に備えた。
- PC幅では既存メインカード右側に、スマホ幅では下部に `Plant Doctor` パネルを表示するようにした。
- `generateAdvice(data)` を総合判定、センサー別分析、推定原因、推奨アクションを返す構造に拡張した。
- 給水経路異常、高温・強光ストレス、乾燥ストレス、光量不足、安定状態の複合条件を追加した。
- メインカードと重複するセンサー別分析はPlant Doctorパネル上では非表示にし、推定原因と推奨アクション中心の表示へ整理した。
- 安定時の「定期的にろ過ウールと根の接触状態を確認してください。」は冗長なため削除した。

## 2026-06-11

### 配線図のコード管理

#### 変更したこと

- Graphviz DOT形式の配線図ソース `docs/wiring.dot` を追加した。
- `scripts/generate_wiring_diagram.py` から `docs/wiring.svg` を再生成できるようにした。
- 水位センサー、照度センサー、DHT11、MCP3204/MCP3208、Raspberry Pi 40ピンヘッダーの接続を図示した。
- Raspberry Piの物理ピン番号、BCM番号、SPIの送受信方向、未使用UART、3.3V/GND、DHT11の10kΩプルアップ、5V禁止を明記した。
- READMEにGraphvizの導入方法と配線図生成コマンドを追加した。

#### 動作確認

- Graphviz互換レンダラーで `docs/wiring.dot` の構文を検証し、`docs/wiring.svg` を生成した。
- ChromiumでSVGを画像化し、各信号線が意図したピン行へ接続されていることを目視確認した。
- `python -m py_compile scripts/generate_wiring_diagram.py` を実行し、構文チェックOK。
- Graphviz 2.42.4 導入後、`python scripts/generate_wiring_diagram.py` で正式に `docs/wiring.svg` を再生成した。

#### 注意点

- MCP3204とMCP3208ではパッケージの物理ピン番号が異なるため、図では共通の信号ピン名を使用している。

### 配線図の可読性改善

#### 変更したこと

- センサー、ADC、Raspberry Piの対象行から配線が伸びるよう、Graphvizの表ポート位置を調整した。
- MCP3204/MCP3208のSPI行をRaspberry Piの物理ピン順に合わせて並べ替えた。
- 配線を折れ線から直線へ変更し、交差と表への重なりを減らした。
- Markdown版の配線資料 `docs/WIRING.md` を追加した。
- READMEの配線図案内からMarkdown版を参照できるようにした。

#### 動作確認

- Graphviz 15.0.0で `docs/wiring.svg` を再生成した。
- PNGへレンダリングし、接続行、配線方向、表との重なりを目視確認した。

## 2026-06-12

### DS18B20養液温度センサーの追加

#### 実配線

- DHT11のDATAをGPIO4からGPIO17（物理ピン11）へ移動した。
- DS18B20のDATA（黄）をGPIO4（物理ピン7）へ接続した。
- DS18B20のVCC（赤）を3.3V、GND（黒）を共通GNDへ接続した。
- DS18B20のDATAと3.3Vの間に4.7kΩプルアップ抵抗を接続する構成とした。
- 水位センサーCH0、照度センサーCH1、MCP3208のSPI配線は従来構成を維持した。

#### 実装したこと

- Linux 1-Wire sysfsからDS18B20を読み取る `ds18b20.py` を追加した。
- `send_sensor.py` のDHT11をGPIO17へ変更し、DS18B20の養液温度取得を追加した。
- ローカルSQLiteとSupabaseの `sensor_logs` にNULL許可の `solution_temperature` を追加した。
- GitHub PagesとFlutterへ養液温度表示を追加した。
- 配線図と `docs/WIRING.md` をDHT11 GPIO17 / DS18B20 GPIO4構成へ更新した。
- Supabase migration `add_solution_temperature` を適用し、`solution_temperature numeric NULL` を確認した。

#### 確認結果

- Raspberry Piの実配線はDHT11 GPIO17、DS18B20 GPIO4へ変更済み。
- Raspberry Piの `/boot/firmware/config.txt` には1-Wire設定がまだ追加されていない。
- `/sys/bus/w1/devices` にDS18B20デバイスはまだ検出されていない。
- Raspberry Pi上のリポジトリは旧コードのままで、`send_sensor.py` はDHT11 GPIO4指定になっている。
- `plant-sensor.service` は `ModuleNotFoundError: No module named 'adafruit_dht'` により再起動を繰り返している。

#### 注意点

- 配線変更は完了しているが、Pi側への新コード反映、1-Wire有効化、再起動、依存パッケージ復旧が必要。
- 1-Wire有効化後は `/sys/bus/w1/devices/28-*/w1_slave` の出現を確認する。

### 再起動後の確認

#### 完了したこと

- `/boot/firmware/config.txt` の `dtoverlay=w1-gpio,gpiopin=4` が有効になった。
- `w1_gpio` / `wire` カーネルモジュールのロードを確認した。
- Piの仮想環境へ欠落していた `click`、`adafruit-circuitpython-dht`、`gpiod`、`requests`、`spidev` などを再導入した。
- DHT11 GPIO17 / DS18B20 GPIO4対応コードを `/home/pi/plant-iot` へ反映した。
- `plant-api.service` と `plant-sensor.service` が `active (running)` へ復旧した。
- `/latest` が `solution_temperature` を返すことを確認した。

#### センサー確認結果

- DHT11はGPIO17（物理ピン11）で8回読み取りを試行したが、`DHT sensor not found, check wiring` となった。
- DS18B20用1-Wireマスターは有効だが、スレーブ数は0で `28-*` デバイスは未検出。
- 1-Wire探索は43回実行されているため、OS設定ではなく配線・電源・プルアップ抵抗を優先して確認する。
- GPIO4は物理ピン7、GPIO17は物理ピン11であることをPiの `pinout` で再確認した。

#### 次の配線確認

- DS18B20: 赤を3.3V（物理1または17）、黒をGND、黄をGPIO4（物理7）へ接続する。
- DS18B20: 黄と3.3Vの間に4.7kΩ抵抗が入っていることを確認する。
- DHT11: DATAをGPIO17（物理11）へ接続し、DATAと3.3Vの間の10kΩプルアップを確認する。
- 3.3Vと5Vを取り違えていないこと、全機器のGNDが共通であることを確認する。

### センサー再接続後の統合確認

#### 確認結果

- DS18B20デバイス `28-000000cc2639` を1-Wireで検出した。
- DS18B20単体確認で養液温度 `26.562℃` を3回連続取得した。
- 常駐サービス経由でDHT11 GPIO17から温度 `26.6℃`、湿度 `60%` を取得した。
- 同一送信で養液温度 `26.5℃`、水位ADC `0`、照度ADC `2858` を取得した。
- ローカルAPIへのPOSTは `200`、SupabaseへのPOSTは `201` で成功した。
- `/latest` に `source=dht11-ds18b20-mcp3208` と `solution_temperature=26.5` が保存された。
- Supabase最新行にも `solution_temperature=26.5` が保存されていることを確認した。
- `plant-api.service` と `plant-sensor.service` はともに `active (running)`。

#### 補足

- 配線が外れていた期間はDHT11とDS18B20の両方が未検出だったが、再接続後は正常化した。
- DS18B20の1-Wire設定、GPIO割り当て、保存経路は動作確認済み。

### バジル枯死候補時期のログ分析

#### 分析結果

- Supabaseの温湿度ログから、強い高温・乾燥ストレスの候補期間を3回抽出した。
- 候補Aは2026-04-26 02:57-09:10 JST、平均36.4℃、平均湿度30.4%だった。
- 候補Bは2026-05-12 11:01-05-14 00:32 JST、平均39.7℃、平均湿度30.6%で、3候補中最も深刻だった。
- 候補Cは2026-05-18 02:35-09:58 JST、平均32.7℃、平均湿度26.9%だった。
- 2026-05-18 09:10 JSTの`care_logs`確認記録後、温湿度が改善している。
- 2026-05-19以降とDHT11へ移行した2026-06-02以降には、同程度の高温・低湿度は記録されていない。

#### 注意点

- 候補期間は旧Sense HATと補正値を使用しており、絶対温度には本体発熱や補正誤差が含まれる可能性がある。
- 水位ADCの記録開始は2026-06-02のため、それ以前の枯死時の水不足はログから確認できない。
- 現在の水位センサーでは貯水部の水と、フェルト・根まで水が届いたかを区別できない。
- 詳細は`docs/HISTORICAL_STRESS_ANALYSIS_2026-06-12.md`へ記録した。

#### 養液・フェルト変更後の枯死

- ユーザーの記憶から、養液とフェルトへ変更後の水不足による枯死は2026-06-02の週の初め頃と暫定特定した。
- 2026-06-02から6月5日の平均温度は24.8-26.6℃、平均湿度は59.3-64.0%で、高温・空気乾燥は確認されなかった。
- 同期間の水位ADCは全記録が0だった。
- この回は高温よりも、養液不足、フェルトの吸水不足、根との接触不良による給水ストレスの可能性が高い。
- 正確な変更日時、枯死確認日時、ADC値0が実水位を正しく表していたかは未確認。

### 照度センサーのBH1750移行準備

#### 変更したこと

- 旧フォトセルとMCP3208 CH1による照度取得を、BH1750のI2C照度取得へ変更した。
- BH1750高分解能モードを読み取る`bh1750.py`と、実機確認用`debug_bh1750.py`を追加した。
- `send_sensor.py`はBH1750のlux値を`light_lux`として送信し、旧`light_raw`と`light_voltage`はNULLで保存する構成にした。
- BH1750が未接続または読み取り失敗の場合も、他センサーの送信は継続する。
- SQLiteへNULL許可の`light_lux`自動追加を実装した。
- Supabaseへ`add_bh1750_light_lux` migrationを適用し、`light_lux numeric NULL`を確認した。
- GitHub PagesとFlutterをlux表示へ変更し、過去ログは旧raw値を表示する互換処理を残した。
- 配線資料をBH1750のGPIO2/SDA、GPIO3/SCL、標準アドレス`0x23`構成へ更新した。
- MCP3208 CH1は未使用とした。

#### 確認結果

- `test_vitality.py`、`test_ds18b20.py`、`test_bh1750.py`の計10テストが成功した。
- Python対象ファイルの構文チェックが成功した。
- Graphvizで`docs/wiring.svg`を再生成し、I2C配線と既存配線の重なりを目視確認した。
- Supabase security advisorは指摘なし。
- performance advisorは既存の未使用インデックス`care_logs_sensor_log_id_idx`のみで、今回変更による新規指摘はない。

#### 未実施

- BH1750の実配線、Raspberry PiのI2C有効化、`i2cdetect`、実lux値の取得は未実施。
- 実配線前のため、Piへのコード反映とsystemdサービス再起動は行っていない。

### 2台のRaspberry Piによる分散計測

#### 構成

- `raspi`はDHT11、DS18B20、水位センサーCH0、CdSセルCH1、LEDを担当する。
- `raspberrypi2`はBH1750、DS18B20、GPIO17フロートスイッチを担当する。
- 同じリポジトリ内に`send_sensor_raspi.py`と`send_sensor_raspberrypi2.py`を用意した。
- systemd serviceも`plant-sensor-raspi.service`と`plant-sensor-raspberrypi2.service`へ分離した。
- Supabaseへ`device_id`、`location_id`、`float_switch_triggered`、`float_switch_state`を追加した。
- 既存ログ互換のため新規DB列はすべてNULL許可とした。

#### raspberrypi2の実機確認

- I2C1とGPIO4の1-Wireを有効化した。
- GPIO17は内部プルアップ状態で、フロート操作に応じた`hi`と`lo`の切り替わりを15秒間の実測で確認した。
- BH1750はI2Cバス上で未検出。`0x23`、`0x5c`を含め応答なし。
- DS18B20は1-Wireマスターが生成されたが、`28-*`デバイスは未検出。
- GPIO2/SDAとGPIO3/SCLはI2C機能かつHigh、GPIO4もHighであるため、OS側機能は有効。
- BH1750とDS18B20は電源、GND、信号線、プルアップ抵抗、端子順を再確認する必要がある。
- cloud-initがホスト名を`raspi2`へ戻していたため、`preserve_hostname: true`と`hostname: raspberrypi2`へ修正した。

#### 検証

- Python構文チェック成功。
- SQLiteの18列INSERTをインメモリDBで確認した。
- Pythonテスト15件成功。
- GitHub PagesのJavaScript構文チェック成功。
- Supabase migration適用後、追加列の型とNULL許可を確認した。
- `raspberrypi2`ではDHT11/SPIを使用しないため、`lgpio`を除外した`requirements-raspberrypi2.txt`を追加した。
- `raspberrypi2`のDS18B20 `28-000000cc1ad1`を検出し、`26.750℃`を取得した。
- GPIO17フロートはPythonコードでも`triggered=True / low_water`を取得した。
- BH1750だけ未検出でもDS18B20とフロートの送信を継続できるよう、各センサーを独立して読み取る構成へ変更した。
- DHTを持たない2号機のログを保存するため、Supabaseの`temperature`と`humidity`をNULL許可へ変更した。既存値は変更していない。
- DS18B20の一時的なCRC失敗に対して3回まで再試行するようにした。

#### 配備結果

- コミット`999be1e`以降をGitHubへpushし、両Piへ反映した。
- `raspi`は既存serviceから互換ラッパー経由で`send_sensor_raspi.py`を実行している。
- `raspi`の最新ログに`device_id=raspi`、`location_id=location-a`が保存され、Supabase POST `201`を確認した。
- `raspberrypi2`へリポジトリ、仮想環境、専用requirements、`.env`、systemd serviceを配備した。
- 秘密情報のコピーに使用したPC上の一時`.env`ファイルは処理直後に削除した。
- `plant-sensor-raspberrypi2.service`を有効化し、再起動後も`active (running)`で自動起動することを確認した。
- `raspberrypi2`は`solution_temperature=26.75`、`float_switch_state=low_water`をSupabaseへPOST `201`で保存した。
- 2号機のBH1750は引き続きI2C未検出のため、`light_lux`はNULLで保存している。
- 2号機のホスト名はcloud-init設定も含めて`raspberrypi2`へ変更し、再起動後も維持されることを確認した。
- `raspi`のunitファイル名変更はsudoパスワードが必要なため未実施。ただし既存unitで新しい専用コードが正常稼働している。
