# NEXT_ACTIONS

## 次にやること

1. `journalctl -u plant-sensor.service -n 80 --no-pager -l` で、通常送信が 00/05/10/15/... 分付近に揃うことを確認する
2. `sudo systemctl reload plant-sensor.service` を実行し、直近送信から短時間ならスキップ、十分時間が空いていれば1回送信されることを確認する
3. Flutter SDKがある環境で cd flutter_app && flutter create . && flutter pub get を実行する
4. flutter analyze を実行する
5. --dart-define=SUPABASE_URL=... と --dart-define=SUPABASE_ANON_KEY=... を渡して起動する
6. sensor_logs 最新1件が表示されることを確認する
7. watered / moved / checked / memo が care_logs に入ることを確認する

## 保留

- 通知機能
- 認証ユーザー単位のRLS
- 端末識別
- 入力回数制限
- care_logsとsensor_logsを使った回復傾向分析
- 手動送信reload機能の運用後、`MANUAL_SEND_MIN_INTERVAL_SECONDS` の適正値を調整する

## 注意点

- Flutter/GitHub Pagesにservice_role keyを置かない
- Flutterにはanon public keyのみを渡す
- SUPABASE_SENSOR_KEY はRaspberry Pi側だけで使う
- 現在のDHT11実行系では `TEMP_OFFSET` / `HUMIDITY_OFFSET` を使わない
- 配線図を再生成する環境にはGraphvizが必要（`sudo apt install graphviz`）
