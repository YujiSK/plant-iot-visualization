# NEXT_ACTIONS

## 次にやること

1. GitHub Pagesに養液温度が表示されることを確認する
2. `journalctl -u plant-sensor.service -n 80 --no-pager -l` で、通常送信が 00/05/10/15/... 分付近に揃うことを確認する
3. Flutter SDKがある環境で `flutter analyze` と実機表示を確認する
4. 2026-06-02の週初め頃に行った植え替え、養液変更、フェルト変更、枯死確認の正確な日時を整理する
5. 今後の給水・植え替え作業を `care_logs` に記録できる入力方法を追加する

## 保留

- 通知機能
- 認証ユーザー単位のRLS
- 端末識別
- 入力回数制限
- care_logsとsensor_logsを使った回復傾向分析
- フェルト側の乾燥を検出する方法の検討
- 手動送信reload機能の運用後、`MANUAL_SEND_MIN_INTERVAL_SECONDS` の適正値を調整する

## 注意点

- Flutter/GitHub Pagesにservice_role keyを置かない
- Flutterにはanon public keyのみを渡す
- SUPABASE_SENSOR_KEY はRaspberry Pi側だけで使う
- 現在のDHT11実行系では `TEMP_OFFSET` / `HUMIDITY_OFFSET` を使わない
- 配線図を再生成する環境にはGraphvizが必要（`sudo apt install graphviz`）
