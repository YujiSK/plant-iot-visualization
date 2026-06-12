# NEXT_ACTIONS

## 次にやること

1. `raspberrypi2`のBH1750配線を再確認し、`i2cdetect -y 1`で`23`を検出する
2. `raspberrypi2`のDS18B20配線と4.7kΩ抵抗を再確認し、`28-*`を検出する
3. フロートスイッチの設置方向を決め、GPIO17の`lo`が水不足になることを確認する
4. `raspi`でsudoを使い、旧`plant-sensor.service`を`plant-sensor-raspi.service`へ名称整理する
5. GitHub Pagesを`?device=raspi`と`?device=raspberrypi2`で確認する
6. Flutter SDKがある環境で`DEVICE_ID`を切り替えて実機表示を確認する
7. 2026-06-02の週初め頃に行った植え替え、養液変更、フェルト変更、枯死確認の正確な日時を整理する
8. 今後の給水・植え替え作業を`care_logs`に記録できる入力方法を追加する

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
- `raspberrypi2`ではBH1750とDS18B20が検出されるまでセンサーサービスを有効化しない
- `raspberrypi2`は`requirements-raspberrypi2.txt`を使用し、不要な`lgpio`を導入しない
- `raspi`の旧unit名でも処理内容は`send_sensor_raspi.py`になっており、動作上の問題はない
