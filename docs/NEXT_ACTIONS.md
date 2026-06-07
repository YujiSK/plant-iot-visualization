# NEXT_ACTIONS

## 次にやること

1. Flutter SDKがある環境で cd flutter_app && flutter create . && flutter pub get を実行する
2. flutter analyze を実行する
3. --dart-define=SUPABASE_URL=... と --dart-define=SUPABASE_ANON_KEY=... を渡して起動する
4. sensor_logs 最新1件が表示されることを確認する
5. watered / moved / checked / memo が care_logs に入ることを確認する

## 保留

- 通知機能
- 認証ユーザー単位のRLS
- 端末識別
- 入力回数制限
- care_logsとsensor_logsを使った回復傾向分析

## 注意点

- Flutter/GitHub Pagesにservice_role keyを置かない
- Flutterにはanon public keyのみを渡す
- SUPABASE_SENSOR_KEY はRaspberry Pi側だけで使う
- 現在のDHT11実行系では `TEMP_OFFSET` / `HUMIDITY_OFFSET` を使わない
