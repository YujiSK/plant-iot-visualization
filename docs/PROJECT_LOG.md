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
