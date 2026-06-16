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

- 管理支援UIの最小実装を追加
- sensor_logs 最新1件を表示する画面を追加
- care_logs に watered / moved / checked / memo を記録する実装を追加
- care_logs 作成用SQLを supabase_care_logs.sql として追加

### 変更したファイル

- supabase_care_logs.sql
- lutter_app/pubspec.yaml
- lutter_app/lib/main.dart
- lutter_app/README.md

### 注意点

- Raspberry Pi環境には対応するUI SDKがないため、画面側のビルド検証は未実施
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
- 管理画面の最新状態カードも気圧ではなく水位・照度を表示するようにした。
- `docs/NEXT_ACTIONS.md` から完了済みのGitHub Pages水位・照度表示追加を外した。

#### 注意点

- 対応するUI SDK はRaspberry Pi環境にないため、画面側のビルド検証は未実施。
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
- GitHub Pagesと管理画面へ養液温度表示を追加した。
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
- GitHub Pagesと管理画面をlux表示へ変更し、過去ログは旧raw値を表示する互換処理を残した。
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

#### BH1750配線修正後の確認

- `raspberrypi2`の配線修正後、BH1750から`244.2 lx`、`244.2 lx`、`194.2 lx`を連続取得した。
- systemd serviceへ手動送信を要求し、`light_lux=245.8`、`light_status=dim`でSupabase POST `201`を確認した。
- Supabase最新行に養液温度`27.375℃`、照度`245.8 lx`、フロート`low_water`が保存された。
- BH1750、DS18B20、フロートスイッチの3センサーすべてが常駐serviceから送信可能になった。

### 現状サマリー作成

- 2台構成、配線、抵抗、OS設定、systemd、最新値、Supabase列、表示方法、テスト状況、残作業を`docs/CURRENT_STATUS_2026-06-13.md`へ整理した。

### リポジトリ内ドキュメント更新

- `README.md`の環境変数例、実行方法、systemd手動送信手順を2台構成に合わせて更新した。
- `AGENTS.md`の確認コマンドを両デバイスと現行センサーモジュールに対応させた。
- 管理アプリの起動例へ`DEVICE_ID`を追加した。
- 2026年6月1日のADC資料を履歴資料として明示し、現行状態と配線資料へのリンクを追加した。

### バジル水耕栽培のvitality評価強化

#### 調査と設計

- バジルの光強度・DLI、根域の通気、養液温度、水位低下の因果関係を一次研究中心に整理した。
- 調査結果、採用閾値、重み、緊急上限、現センサーの限界を`docs/BASIL_VITALITY_RESEARCH_2026-06-13.md`へ記録した。
- BH1750のluxはPPFD/DLIではないため、09:00～15:00の補助評価に限定し、夜間や日の出直後を減点しない方針にした。

#### 実装

- `vitality.py`へ養液温度、照度、水位、気温、湿度を統合する`calculate_basil_vitality()`を追加した。
- 水位低下、養液高温・低温、水位と温度の複合ストレスは、良好な他センサー値で相殺されない上限制約を追加した。
- `send_sensor_raspi.py`、`send_sensor_raspberrypi2.py`、`main.py`を新しい評価ロジックへ切り替えた。
- GitHub Pagesの助言へ水位低下、養液温度、複合ストレスを追加し、低照度助言を日中コア時間帯だけに限定した。
- `LIGHT_EVALUATION_START_HOUR=9`と`LIGHT_EVALUATION_END_HOUR=15`を2号機の設定項目として追加した。

#### 検証

- Python対象ファイルの読み取り専用構文チェックに成功した。
- `test_vitality.py`、`test_ds18b20.py`、`test_bh1750.py`、`test_float_switch.py`の22件が成功した。
- `docs/index.html`内のJavaScript構文チェックに成功した。
- 7時台の実測相当値は夜明け補正で100、同じ照度が正午なら92、低水位と31℃の複合条件は15になることを確認した。
- DBスキーマ変更、Raspberry Piへの配備、systemd再起動は行っていない。

### raspberrypi2屋外設置後のBH1750運用メモ

- `raspberrypi2`をバジル栽培キットへ取り付けて屋外へ設置した。
- 1号機`raspi`は現在バジル栽培キットへ設置しておらず、送信値はセンサー・API・systemdの動作確認値として扱う。
- BH1750は雨を避けるため、現在は青色の蓋が付いたタッパー内部に設置している。
- 青色の蓋による遮光と波長選択の影響があるため、現在の`light_lux`は葉が受ける照度ではなく、容器内部の参考値として記録を継続する。
- 現在の設置状態では、BH1750の低照度を植物の光量不足と断定しない。
- 今後、BH1750を透明な防水ケースへ移し、葉と同程度の高さで受光面を空へ向けて設置する必要がある。
- 移設後はケースによる透過損失を確認し、移設前後の値を同一条件で比較して補正係数を検討する。

### 2026-06-13日次センサーデータ分析

- Supabase `sensor_logs`から2026-06-13 00:00-19:50 JSTの444件を取得し、1号機239件と2号機205件へ分類した。
- 1号機は未設置の動作確認データ、2号機は実栽培データとして分離して評価した。
- 2号機の06:30以降はフロート163件すべてが`water_ok`、養液温度は24.875-28.062℃、vitality平均は92.2だった。
- BH1750は09:45に8,147.5 lxで最大となり、夜間に0 lxへ低下した。欠測・日周変化・時間帯平均を確認し、相対推移センサーとして正常と判断した。
- 青色蓋内部の値であるため、積算約25,456 lux·hは葉面照度、PPFD、DLIではなく、現設置条件での日別比較用と明記した。
- 未明の`low_water`と04:35-06:30の記録空白を確認した。`care_logs`は権限エラーで参照できず、作業との関係は未確定とした。
- 分析結果を`docs/DAILY_SENSOR_ANALYSIS_2026-06-13.md`へ記録した。

#### 設置初日の前提更新

- 1号機`raspi`は室内テーブル上で仮稼働する動作確認用ノードであり、実栽培分析の対象外であることを明記した。
- 2号機`raspberrypi2`は2026-06-13の06:30頃までにバジル栽培キットへ設置し、06:30以降を安定稼働区間として扱う前提を明記した。
- 未明の`low_water`は、設置前の配線・開発・フロート確認中の入力変化を含む可能性が高く、植物の水不足として評価しない記述へ更新した。
- バジルは子葉が出始めた段階であるため、この日の分析を栽培成果の評価ではなく、設置初日の計測系検証とベースライン確認に位置づけた。
- 既存の件数、温度、照度、vitalityなどの数値集計は変更していない。

#### 写真による植物観察

- 観察時刻を2026-06-13 21:44 JST、対象を`raspberrypi2`実栽培環境のバジルとして記録した。
- 2026-06-13をバジルの「発芽確認」と「子葉展開確認」のマイルストーンとして記録した。
- 写真から、複数個体の発芽と子葉展開、本葉未形成、未発芽種子の残存を確認した。
- 顕著な徒長、明確なしおれ、黄化、枯死個体は見られず、ろ過ウール表面は十分な湿潤状態に見えることを記録した。
- 正確な播種数と発芽個体数を写真から確定していないため、発芽率は数値化せず、100%ではないという定性的記録に留めた。
- 日次分析へ植物観察セクションを追加し、今後は本葉形成、葉数、草丈、生存個体数を環境データと対応づける方針を追記した。
- Supabase `care_logs`へ観察時刻2026-06-13 21:44 JST、`action_type=checked`として植物観察を保存した。
- 観察記録を最寄りの2号機センサーログ（21:45 JST）へ紐づけた。同ログはvitality 25、フロート`low_water`であり、写真上のろ過ウール表面の湿潤状態とは観測対象が異なるため、両方を併記した。

### 旧Sense HAT補正履歴と生値復元の再調査

- 初期運用では、Sense HATの値をバジルの想定環境範囲へ近づけるため、基準計との比較や校正試験を行わずに固定オフセットを適用し、補正後の値だけをDBへ保存していた。この処理は研究データの扱いとして不適切だったと整理した。
- 問題認識後、補正の痕跡を削除せず、適用理由、補正量、適用期間、復元方法、確度を追跡可能な形で残す方針とした。
- 1号機`raspi`の`plant-iot/data.db`には生値専用列はないが、補正適用期間が特定できたため、DBに存在する旧Sense HAT行は補正前の出力値へ逆算可能と確認した。
- 補正なし、温度`-8℃`、温度`-8℃`と湿度`+15ポイント`、温度`-15℃`と湿度`+15ポイント`の4期間を分離した。
- 候補Aは94件で平均36.46℃/30.35%、候補Bは448件で平均39.74℃/30.54%、候補Cは86件で平均41.07℃/25.71%へ復元した。
- 候補DはDHT11生値1,099件で平均25.71℃/61.04%だった。
- Sense HATの復元後温度は基板発熱を含むセンサー出力であり、室温の絶対値として扱わない。
- データ欠測期間と固定オフセットの適用期間を`docs/HISTORICAL_STRESS_ANALYSIS_2026-06-12.md`へ追記した。
- 旧Sense HAT期間は削除せず、計測条件不統一の参考データとして保持し、現行センサー期間の定量系列とは分離する方針とした。
- 原本`data.db`を読み取り専用で開き、元の全カラムと復元列を併記する`scripts/reconstruct_historical_sensor_data.py`を追加した。
- 復元CSVには適用オフセット、計測システム、復元根拠、確度を記録し、メタデータJSONには原本DBのSHA-256と補正期間を保存する。
- 欠測補間、外気温推定、Sense HAT基板発熱の推測補正は行わず、当時の固定オフセットだけを取り除く方針とした。
- 合成SQLite DBを使い、補正なし、温度`-8℃`、温度`-8℃`と湿度`+15ポイント`、温度`-15℃`と湿度`+15ポイント`、DHT11無補正の各期間をテストした。
- 2026-06-14にTailscale経由のSSH鍵認証が成功し、1号機`raspberrypi`（`100.69.139.28`）の原本`data.db`から復元CSVを生成した。
- 7,330行すべてを補正期間へ分類でき、unknownは0件だった。原本DBのエクスポート前後SHA-256は一致し、DBが変更されていないことを確認した。
- 生成物は1号機とこの端末の`exports/sensor_logs_reconstructed.csv`および同名のメタデータJSONへ保存した。

## 2026-06-14

### 卒業研究の方向性整理

- 卒業研究の主軸を「植物を自動で育てる・枯らさないシステム」から「植物の異常発見・観察・記録を継続しやすくする管理支援システム」へ整理した。
- 約4回の栽培失敗について、センサー構成、目視観察、管理作業の記録不足により、後から原因を確定することが難しかった経験を研究背景として位置づけた。
- 2026-06-13 21:44 JSTの写真ではろ過ウール表面が湿潤だった一方、21:45 JSTのフロートは`low_water`だった事例から、人間の観察とセンサーは異なる対象を補完的に観測すると整理した。
- 研究対象を植物そのものの自動制御ではなく、異常発見、観察、記録、対応、振り返りからなる植物管理行動の支援とした。
- 研究目的を「IoTセンサーおよび生成AIを活用し、植物の異常発見・観察・記録を継続しやすくする管理支援システムを構築する」と暫定定義した。
- 研究仮説として、異常通知による対応時間短縮、AI観察支援による記録欠損削減、日次分析と`care_logs`による振り返り容易化を設定した。
- AIは病気診断ではなく、写真から確認可能な事実の抽出、確認不能項目の明示、再撮影指示、観察品質向上に使用する方針とした。
- 自動給水の高度化、AI病気診断、高度な画像分類は卒業研究の主軸から外し、将来拡張として扱う。
- 優先順位を、基盤運用、通知と対応記録、AI観察支援、将来拡張の順に整理した。
- 方針、研究仮説、システム構想、評価候補、優先順位を`docs/PROJECT_DIRECTION_2026-06.md`へ記録した。

### Slack中心の管理支援フロー

- LINE、Slack、専用アプリを比較し、研究期間中はSlackを実験基盤、専用アプリを最終発展形として扱う方針を決定した。
- 専用アプリは自由度が高い一方、現段階ではUIと通知基盤の開発工数が大きいため、まずSlackで研究仮説の検証と運用データ収集を優先する。
- SlackのBot・API・画像投稿・チャンネル分離・通知機能を利用し、短い実験サイクルで管理支援フローを検証する。
- Phase 1を異常通知、Phase 2を回復検知と`care_logs`生成、Phase 3を写真観察支援、Phase 4を再撮影支援、Phase 5を観察品質評価、Phase 6を専用アプリ化の再評価とした。
- Slackチャンネル案として、異常通知用`#plant-alert`、写真観察用`#plant-observation`、分析共有用`#plant-analysis`を設定した。
- `low_water`から利用者対応、`water_ok`回復、`care_logs`生成までを記録し、異常発見から回復までの管理行動を評価対象とする。
- Slackで有効性を確認できたPush通知、写真投稿、`care_logs`作成、日次分析閲覧、AI観察支援などを専用アプリへ移植する方針とした。
- 優先順位を、基盤運用、Slack通知と対応記録、AI観察支援、専用アプリ化を含む将来拡張の順に更新した。

### プロジェクト全体時系列の整理

- 2026-04-25のSense HAT試作開始から、Supabase・GitHub Pages、固定補正、DHT11・ADC移行、養液温度、2台構成、実栽培設置、発芽確認、旧データ復元、研究方針転換までを時系列で整理した。
- 技術変更だけでなく、約4回の栽培失敗、記録不足、補正処理の問題、写真とセンサーの観測差が研究方針へ与えた影響を対応づけた。
- 冒頭の全体図、フェーズ別一覧、日付別詳細、現在の到達点、現在の研究フローを`docs/PROJECT_TIMELINE_2026-06.md`へ記録した。

### Supabaseログの機体判定ルール

- `sensor_logs.device_id IS NULL`の既存5,733件は、すべて1号機`raspi`のログとして扱う。
- 内訳は、旧Sense HATの`source=sensor`が2,767件、DHT11とADCの`source=dht11-mcp3204`が2,683件、DS18B20追加後の`source=dht11-ds18b20-mcp3208`が283件だった。
- `device_id IS NULL`の行に、2号機固有の`light_lux`、`float_switch_state`、`float_switch_triggered`または2号機を示す`source`を持つ行は0件だった。
- 2号機のログは`device_id=raspberrypi2`かつ`location_id=location-b`の行だけである。
- 今後の分析では、`device_id IS NULL`を「機体不明」とせず、1号機の履歴として正規化する。既存DB行は監査性を保つため更新しない。

### 未使用管理支援UI試作の削除

- 管理支援UI試作ディレクトリは2026-05-18に作成した最小試作だったが、ビルド・配備・実運用されておらず、GitHub Pagesやセンサー送信にも使用していなかった。
- 現行システムの構成要素と誤解されることを避けるため、この試作コードをリポジトリから削除した。
- 試作した事実は、Git履歴、`PROJECT_LOG.md`、プロジェクト時系列へ残す。
- GitHub Pagesを現在の可視化手段、Slackを今後の実験基盤として明確化した。
- 専用アプリ化は確定した移植計画とせず、Slackで機能の有効性を確認した後に必要性と技術選定を再評価する方針へ変更した。

### GitHub Pages の 3 ペイン化

- GitHub Pages を 1号機・2号機の最新値、推移グラフ、プロジェクト概要の3ペイン構成へ更新した。
- 画面上で期間を切り替えられるようにし、各機体の状態変化を見やすくした。
- 右側の概要欄は、教授や第三者が目的、背景、進捗を短く把握できるように、専門用語を抑えた説明へ寄せた。
- デモモードと `?device=` 前提の表示は廃止した。

### GitHub Pages の研究向けUI再設計

- 3ペインを常時横並びにする方式を取りやめ、PCでは左サイドバー、スマートフォンでは上部タブから「ホーム」「データ推移」「概要」を切り替える構成へ変更した。
- URLハッシュ`#home`、`#trends`、`#about`で表示状態を保持し、再読み込み、ブラウザの戻る・進む、矢印キー操作に対応した。
- ホームは2号機の実栽培データを主役、1号機を動作確認値として表示する。1号機の低いvitalityや未設置水位を植物異常として警告しない。
- 2号機が`low_water`の場合だけ、ホームに赤い要確認パネルと確認行動を表示する。
- データ推移は機体、6時間・24時間・7日・30日、vitality・養液温度・照度・水位を選択し、大きなグラフ1つへ表示する。
- グラフはSVGで描画し、日時と値のツールチップ、欠測区間の分断、水位の段階表示、最小・平均・最大・最新の統計を追加した。
- 30日表示に備え、Supabaseデータを1000件ずつ最大1万件までページ分割して取得する。
- 概要画面は指導教員や第三者向けに、目的、背景、着想、現在、次の段階を専門用語を抑えて整理した。
- 画面全体の状態色変更を廃止し、2号機は緑、1号機は青、警告箇所だけ赤で表現する。
- Python標準HTMLパーサーによる構造確認と`git diff --check`に成功した。
- 新UIと同じ条件でSupabase REST APIを確認し、2号機の最新行をHTTP 200で取得できた。
- 初回push後のGitHub Pages公開反映を確認し、サイドバー、3画面、30日フィルタ、ハッシュ切替処理が配信されていることを確認した。
- GitHub ActionsのHTML検証で指摘されたボタンの`type`属性と研究メモ領域のアクセシブル名を追加した。
- Python CIは今回未変更のワークフローが`requests`をインストールせずテストを実行するため失敗した。ローカルでは23テストすべて成功しており、UI変更によるPython回帰ではない。

### GitHub Actions のPython依存修正

- GitHub Actionsの新しいPython環境には、2号機モジュールが読み込む`requests`と`python-dotenv`が入っていなかった。
- Raspberry Pi固有のGPIO依存をCIへ持ち込まず、単体テストのimportに必要な純Python依存だけをテスト前にインストールするよう変更した。

## 2026-06-15

### 2号機のSlack水位異常通知

- 植物管理支援サイクルの第一段階として、`raspberrypi2`の水位低下と回復をIncoming WebhookでSlackへ通知する機能を追加した。
- `float_switch_state=low_water`の初回だけ警告し、継続中の5分ごとの重複通知を抑止する。
- `water_ok`が2回連続した場合に回復通知を送る。
- 通知状態は`notification_state.json`へ保存し、`NOTIFICATION_STATE_PATH`で保存先を変更できる。
- Slack未設定・送信失敗・状態ファイル処理失敗はログへ残し、センサー読み取りとSupabase送信を停止しない構成にした。
- 1号機`raspi`は通知対象外とした。
- 本機能は自動給水ではなく、異常発見・観察・記録を継続しやすくする管理支援機能として位置付ける。

#### 2号機でのWebhook・サービス確認

- 2号機の`.env`に`SLACK_WEBHOOK_URL`が設定済みであることを、URL本体を表示せず確認した。
- Incoming Webhookへ単体POSTし、HTTP `200`と本文`ok`を確認した。
- systemd unitが`EnvironmentFile=/home/pi/plant-iot/.env`を使用していることを確認した。
- `slack_notifier.py`と更新済み`send_sensor_raspberrypi2.py`を2号機へ配備し、リモート構文チェックに成功した。
- sudoパスワードを非対話で渡せないため、稼働中のpi所有プロセスへ`TERM`を送り、`Restart=always`によるsystemd自動再起動を行った。
- 再起動後のserviceは`active (running)`で、Supabase POST `201`を確認した。
- serviceプロセスに`SLACK_WEBHOOK_URL`が渡り、`notification_state.json`が`last_state=water_ok`で生成されたことを確認した。
- 確認時の実測水位は`water_ok`だったため、実水位低下による`[slack] alert sent: low_water`は未確認である。

## 2026-06-16

### Slack写真観察ログ Phase 1

#### 実装したこと

- `slack_observation_bot.py`を追加し、Slack Events APIの`/slack/events`で写真投稿イベントを受け取る独立プロセスを用意した。
- `SLACK_OBSERVATION_CHANNEL_ID`で指定したチャンネルの`message`イベントだけを対象にした。
- `files`内の`mimetype`が`image/`で始まるSlackファイルだけを観察写真として扱うようにした。
- テキストのみ、別チャンネル、bot自身の投稿、画像以外のファイルは無視するようにした。
- Slack投稿時刻をJSTへ変換し、SlackチャンネルID、投稿者ID、message ts、file id、file名、MIME type、Slack file URLを`care_logs.note`へ保存するようにした。
- 現行`care_logs`には`metadata`、`source`、`observed_at`カラムがないため、スキーマ変更は行わず既存カラムへ合わせた。
- 観察時刻の前後10分から、`device_id=raspberrypi2`の最寄り`sensor_logs`を検索し、見つかった場合は`sensor_log_id`、`vitality_score`、水位、養液温度、照度を記録するようにした。
- 最寄り`sensor_logs`検索に失敗、または該当なしの場合でも、`care_logs`保存は継続するようにした。
- 保存成功時はSlackスレッドへ「観察写真を記録しました」と返信し、失敗時は警告メッセージを返すようにした。
- Slack返信に失敗しても`care_logs`登録結果は維持するようにした。
- AI画像解析、植物診断、再撮影指示、観察品質スコア、Supabase Storageへの画像保存、Flutter連携、LINE連携は実装対象外として維持した。

#### README更新

- Slack Bot Token方式の環境変数、OAuth scopes、Event subscription、実行コマンドを追記した。
- 今回の機能はAI診断ではなく、観察写真を継続的に残し、センサー値や日次分析、`care_logs`と後から比較するための観察記録機能であることを明記した。
- 将来フェーズとして、発芽、子葉、本葉、水位確認などのAI観察支援を追加する方針を記録した。

#### 検証

- `python -m py_compile main.py send_sensor.py send_sensor_raspi.py send_sensor_raspberrypi2.py bh1750.py ds18b20.py float_switch.py vitality.py care_log.py slack_notifier.py slack_observation_bot.py` 成功。
- `python -m unittest test_vitality.py test_ds18b20.py test_bh1750.py test_float_switch.py test_slack_observation_bot.py` 成功。30件成功。

#### 注意点

- Slack App側のRequest URL公開、Event subscription設定、実チャンネルID設定、実投稿による疎通確認は未実施。
- 現行`care_logs`スキーマに合わせたため、SlackメタデータはJSONではなく`note`へテキスト保存している。
- `SUPABASE_KEY`で`care_logs` insertと`sensor_logs` selectが許可されている必要がある。

#### 直近2日間の観察補足

- 2026-06-15から06-16にかけて、2号機`raspberrypi2`の`low_water`は21件から1件へ減少し、`water_ok`が大半を占める状態に戻った。
- 2号機のvitality平均も6/15の85.28から6/16の94.36へ上昇し、設置直後の揺れは収束方向にあると読める。
- 6/16の平均照度は6/15より高く、透明な容器へ移した影響で周囲光の入り方が変化した可能性があるため、今後は同一条件で比較する。
- 1号機`raspi`は引き続き動作確認用ノードで、`water_status=dry`とvitality 25の固定挙動を示した。

## 2026-06-17

### Slack写真観察Botの常駐化

#### 変更したこと

- `slack_observation_bot` を `systemd` サービス `plant-slack-observation.service` として常駐化する方針を整理した。
- 先に Bot 本体だけを常駐化し、Cloudflare Quick Tunnel は引き続き手動運用にする方針を明確にした。
- `plant-slack-observation.service` をリポジトリに追加した。

#### 注意点

- Quick Tunnel の URL は起動ごとに変わるため、`cloudflared` の常駐化は今回の対象外。
- 外部公開 URL の固定化は、必要に応じて Cloudflare named tunnel へ移行する段階で行う。
- `plant-sensor-raspberrypi2.service` など既存のセンサー送信サービスは変更していない。

#### 検証

- `sudo systemctl is-active plant-slack-observation.service` が `active` になった。
- `sudo systemctl status plant-slack-observation.service --no-pager -l` で `Uvicorn running on http://0.0.0.0:8010` を確認した。
- `sudo curl -i http://127.0.0.1:8010/slack/events` が `405 Method Not Allowed` を返した。
