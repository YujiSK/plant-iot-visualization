# NEXT_ACTIONS

## 次にやること

1. フロートスイッチの設置方向を決め、GPIO17の`lo`が水不足になることを確認する
2. `raspi`でsudoを使い、旧`plant-sensor.service`を`plant-sensor-raspi.service`へ名称整理する
3. GitHub Pagesのサイドバー、3画面、グラフ操作を実機ブラウザで継続確認する
4. 2026-06-02の週初め頃に行った植え替え、養液変更、フェルト変更、枯死確認の正確な日時を整理する
5. 今後の給水・植え替え作業を`care_logs`に記録できる入力方法を追加する
6. BH1750を青色蓋のタッパー内部から透明な防水ケースへ移し、葉と同程度の高さ・空向きで設置する
7. BH1750移設後、同一時間帯・天候で移設前後の値を比較し、透明ケースの透過損失と補正係数を確認する
8. BH1750の5分値から日中積算luxを算出し、透明ケース移設後の傾向評価へ利用する

## 保留

- 通知機能
- 認証ユーザー単位のRLS
- 端末識別
- 入力回数制限
- care_logsとsensor_logsを使った回復傾向分析
- フェルト側の乾燥を検出する方法の検討
- 手動送信reload機能の運用後、`MANUAL_SEND_MIN_INTERVAL_SECONDS` の適正値を調整する
- pH、EC、溶存酸素センサーの追加とvitalityへの統合
- Slack写真観察ログの次段階として、OpenAI Visionによる発芽、子葉、本葉、水位確認などの実画像解析へ拡張する
- 成長変化比較を実機写真投稿で確認し、比較メモが妥当か記録する
- AI観察支援後の段階として、情報不足時の再撮影支援と観察品質スコアを検討する

## Slack通知

1. 実際の低水位発生時に`[slack] alert sent: low_water`とSlack受信を確認する
2. 低水位から2回連続正常へ戻した際の回復通知を確認する
3. Webhook送信失敗時もSupabase送信が継続することを実機journalで確認する
4. Slack回復通知を`care_logs`の自動記録へ接続する

## 注意点

- GitHub Pagesにservice_role keyを置かない
- SUPABASE_SENSOR_KEY はRaspberry Pi側だけで使う
- Slack Bot Token、Signing Secret、チャンネルIDは`.env`だけに置き、Gitへコミットしない
- Slack写真観察ログは現段階ではAI診断ではなく、観察記録として扱う
- 現在のDHT11実行系では `TEMP_OFFSET` / `HUMIDITY_OFFSET` を使わない
- 配線図を再生成する環境にはGraphvizが必要（`sudo apt install graphviz`）
- `raspberrypi2`は`requirements-raspberrypi2.txt`を使用し、不要な`lgpio`を導入しない
- `raspi`の旧unit名でも処理内容は`send_sensor_raspi.py`になっており、動作上の問題はない
- 透明防水ケースへ移設するまで、`raspberrypi2`のBH1750値は青色蓋内部の参考値として扱い、葉面照度とはみなさない
