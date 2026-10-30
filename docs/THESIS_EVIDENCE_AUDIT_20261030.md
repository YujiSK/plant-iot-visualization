# PLANT-IOT-THESIS-EVIDENCE-AUDIT-20261030

このチャットの初回監査報告を保存したもの。監査日2026-10-30、時刻は原則JST（UTC+09:00）。原本DB・サービスは読み取り専用。公開用コミットはその後のユーザー指示による。日別集計は[別紙](THESIS_EVIDENCE_DAILY_COUNTS_20261030.md)、後続の実機Bot監査は[別報告](THESIS_BOT_FUNCTION_AUDIT_20261030.md)。

## 1. EXECUTIVE_SUMMARY

Supabase主要系列35,407件、記録範囲2026-06-13 01:22:21.972648〜2026-10-13 10:35:00.669265 JSTを独立再計算して確認した。指定事故前半開区間 `[2026-07-22 00:00, 2026-08-02 19:15)` は3,794件。終了境界直後の19:15:00.617939の行は含まない。

重要な相違：既存事故解析文書は7月22日13:05開始、ユーザー指定は00:00開始。5分枠取得率はそれぞれ99.91%と95.44%。99.91%を00:00開始の成績として記載できない。最長隣接記録間隔は10日20時間59分7.184033秒。

初回監査時点ではSSH制約によりSQLite・現在の実機サービス・systemdログは未検証。後続Bot監査で接続できたが、SQLite実験の監査完了を意味しない。

## 2. SYSTEM_INVENTORY

GitHub確認HEAD `32b09a4db0dd3cb28e08f692fc7141726cfbca91`（2026-09-18 09:40:04 JST）。以下はコード上の構成で、当時の実機環境変数・配備版と同一とは未確認。

| 対象 | 実装 |
|---|---|
| raspi | DHT11、DS18B20、水位ADC、CdS、LED |
| raspberrypi2 | DS18B20、BH1750、フロートスイッチ |
| 定期測定・送信 | 両機既定300秒、環境変数で変更可 |
| フロート監視 | 待機既定1秒、低水位3回・復旧10回確認。通信時間を含む厳密な1秒周期ではない |
| Web | docs/index.htmlとGitHub Pages構成。公開画面実動作未検証 |
| Flutter | 確認したツリーにアプリ実装なし。実稼働未確認 |
| 通知 | Slack/LINE実装と運用記録。初回監査では配信原本未確認 |

出典：`AGENTS.md`、`send_sensor_raspi.py`、`send_sensor_raspberrypi2.py`、`outbox.py`。

送信前にSQLite Outboxへ保存。既定`data.db`、`OUTBOX_DB_PATH`で変更可。pending/failedをID順に最大50件、HTTPタイムアウト10秒で送信。失敗時retry_count増加、次回サイクルで再試行。確認コードには指数バックオフ・最大試行回数なし。同期済みは30日後削除の実装。DS18B20読取最大3回、再試行間隔0.25秒。時刻保持だけでは重複防止は保証されない。

## 3. DATASET_INVENTORY

データ源：Supabaseプロジェクト `oawkrkgnjkldfyvjcrgx` のpublicスキーマ。実COUNTでsensor_logs=43,280、care_logs=29、plant_observations=7。テーブル一覧の概算値は使わない。

| device_id | source | 件数 | 開始〜終了（2026年JST、秒省略） |
|---|---|---:|---|
| raspberrypi2 | raspberrypi2-ds18b20-bh1750-float | 35,407 | 6/13 01:22〜10/13 10:35 |
| raspberrypi2 | sensor | 1 | 7/22 12:51 |
| raspi | raspi-dht11-ds18b20-mcp3208 | 2,139 | 6/13 01:15〜6/20 11:25 |
| NULL | dht11-ds18b20-mcp3208 | 283 | 6/12 01:42〜6/13 01:10 |
| NULL | dht11-mcp3204 | 2,683 | 6/2 04:10〜6/11 12:05 |
| NULL | sensor | 2,767 | 4/26 02:57〜5/25 21:42 |

NULLデバイスの機体をこのSQLだけで確定しない。

```sql
SELECT 'sensor_logs' AS t, COUNT(*) FROM sensor_logs
UNION ALL SELECT 'care_logs', COUNT(*) FROM care_logs
UNION ALL SELECT 'plant_observations', COUNT(*) FROM plant_observations;
SELECT device_id,source,COUNT(*),MIN(created_at),MAX(created_at)
FROM sensor_logs GROUP BY device_id,source ORDER BY device_id,source;
```

SQLite：コードにoutbox_queue定義（id,device_id,payload,status,retry_count,created_at,synced_at,last_error）がある。実ファイル・実スキーマ・件数・10月19日までの実験区間、ADC変化・介入対応は未検証。

初回接続結果：raspi名前解決失敗、旧資料IPへのSSHタイムアウト、raspberrypi2はTailscale追加認証要求。補足された現在のraspi1はこの監査実行環境で、hostname/IP一致。調査した/home、/opt、/srv、/var/libには植物コード・data.dbを発見できず、対象ユニット・journalも確認できなかった。過去実験機と同じ環境か不明。認証後のraspi2で確認した現在状態はBot報告を参照。

## 4. QUANTITATIVE_RESULTS

主要系列の定義：`source='raspberrypi2-ds18b20-bh1750-float'`。

| JST月 | 件数 |
|---|---:|
| 2026-06 | 5,502 |
| 2026-07 | 6,569 |
| 2026-08 | 8,991 |
| 2026-09 | 10,171 |
| 2026-10 | 4,174 |

```sql
SELECT to_char(created_at AT TIME ZONE 'Asia/Tokyo','YYYY-MM') AS mon,COUNT(*)
FROM sensor_logs WHERE source='raspberrypi2-ds18b20-bh1750-float'
GROUP BY 1 ORDER BY 1;
```

日別全系列143行、計43,280件は別紙。ゼロ件日は行を生成していない。

指定半開区間の行数とdistinct created_atはともに3,794：

```sql
SELECT COUNT(*),COUNT(DISTINCT created_at)
FROM sensor_logs WHERE source='raspberrypi2-ds18b20-bh1750-float'
AND created_at >= '2026-07-22 00:00+09'
AND created_at < '2026-08-02 19:15+09';
```

### 5分枠取得率

実装既定300秒・正時境界整列に基づく。期待枠数=(終了−開始)/300秒+1。各期待時刻の[-150秒,+150秒)に1件以上あれば取得とし、追加行を重複カウントしない。取得率=取得枠/期待枠、欠測率=欠測枠/期待枠。

| 期待時刻の範囲（JST、両端含む） | 期待 | 取得 | 欠測 | 取得率 | 欠測率 |
|---|---:|---:|---:|---:|---:|
| 7/22 00:00〜8/2 19:15 | 3,400 | 3,245 | 155 | 95.44% | 4.56% |
| 7/22 13:05〜8/2 19:15 | 3,243 | 3,240 | 3 | 99.91% | 0.09% |

```sql
WITH slots AS (
 SELECT generate_series('2026-07-22 00:00+09'::timestamptz,
 '2026-08-02 19:15+09'::timestamptz,'5 minutes') AS t
), v AS (
 SELECT t,EXISTS(SELECT 1 FROM sensor_logs
 WHERE source='raspberrypi2-ds18b20-bh1750-float'
 AND created_at>=t-interval '150 seconds'
 AND created_at<t+interval '150 seconds') AS ok FROM slots
)
SELECT COUNT(*) AS expected,COUNT(*) FILTER(WHERE ok) AS covered,
COUNT(*) FILTER(WHERE NOT ok) AS missing FROM v;
```

2行目は開始を13:05に変更して実行。これはクラウド時刻列の被覆率で、リアルタイム送信成功率・全センサー正常率ではない。当時の環境変数照合は未完了。

### 隣接間隔と欠測

全主要系列のcreated_atをcreated_at,id順に並べた差の第1四分位298.810189秒、中央値299.519754秒、p95=300.650751秒、最小0秒、最大939,547.184033秒。同時刻複数行があり、行数を独立測定数と扱えない。

| 直前記録→次記録（JST） | 間隔 |
|---|---|
| 7/11 15:40:00.370500→7/22 12:39:07.554533 | 10日20:59:07.184033 |
| 8/4 10:49:59.450812→8/7 17:02:43.522931 | 3日06:12:44.072119 |
| 8/2 19:16:39.296990→8/4 10:35:15.481819 | 1日15:18:36.184829 |
| 6/15 19:45:00.505269→6/16 07:26:00.777475 | 11:41:00.272206 |
| 6/13 04:35:01.915103→6/13 06:30:47.343534 | 01:55:45.428431 |

```sql
WITH s AS (SELECT created_at,LAG(created_at) OVER(ORDER BY created_at,id) AS prev
FROM sensor_logs WHERE source='raspberrypi2-ds18b20-bh1750-float')
SELECT prev AT TIME ZONE 'Asia/Tokyo',created_at AT TIME ZONE 'Asia/Tokyo',
created_at-prev AS gap FROM s ORDER BY gap DESC NULLS LAST LIMIT 5;
```

分位点は同じ隣接差のextract(epoch)にpercentile_contを適用。上表は障害継続時間そのものではなく、記録終了後の空白を含まない。

### 指定半開区間3,794件の分布

養液温度：最小25.25、平均33.063748、中央値32.812、最大40.75℃。NULLと85℃は各0件。照度：最小0、平均2,629.877833、最大54,612.5 lx。low_water=0件。

算出：前記半開区間WHEREにMIN/AVG/MAX、percentile_cont(0.5)、COUNT FILTERを適用。追加記録込みの行単位分布で時間加重ではない。全期間・全センサー分布、ADC変化点・校正比較は未完了。温度の高さから植物への因果的影響を確定しない。

## 5. INCIDENT_EVIDENCE

7月：DBから長い記録空白を確認。PROJECT_LOG.mdの2026-07-22節は無効・破損キーによるHTTP 401、キー更新、Outbox導入、通知・復旧試験成功と記載。当時のjournal・応答・通知原本は今回未取得で、原因・試験成功は運用記録による証言として区別。

8月：主要系列で次の行を直接確認。

| JST | 養液温度℃ | lx | 水位 | Score |
|---|---:|---:|---|---:|
| 8/2 19:15:00.617939 | 29.5 | 0.8 | water_ok | 79 |
| 8/2 19:16:39.296990 | 85.0 | 2800.8 | low_water | 5 |
| 8/4 10:35:15.481819 | 29.812 | 3229.2 | low_water | 25 |

検証SQLは主要系列をcreated_at BETWEEN '2026-08-02 19:10+09' AND '2026-08-04 10:40+09'で選択して時刻順。急変後の空白39時間18分36.184829秒を再現。85℃は異常候補で、実養液温度と断定しない。

docs/INCIDENT_ANALYSIS_PROGRESS_2026-09-05.mdには8/4の転倒・萎凋・電源コード脱落の現地確認がある。写真・証言原本は未照合。検出できたものは水位変化、温度・照度急変、記録途絶。転倒そのもの、給水経路断絶、正確な電源断・死亡時刻の直接検出ではない。強風・転倒・電源断・通知遅延の因果関係は未確定。

## 6. VERIFIED_CLAIMS

主要系列35,407件と範囲、指定半開区間3,794件、5分枠取得率2種類、7月・8月の記録空白、8/2急変、既定300秒とOutbox実装。出典・SQLは上記。コード上の実装と実運用成果を分離する。

## 7. UNVERIFIED_CLAIMS

SQLiteの10/19までの実験・ADC値・介入対応、全期間連続正常運転、Web/Flutter実利用、通知到達率・遅延、7月原因の原本確認、全行がリアルタイムで復元・再送・試験行を含まないこと、生育改善・枯死防止・転倒事前予測。現在サービスについては後続Bot報告で一部更新したが、これらの未検証事項を解消したわけではない。

## 8. TITLE_RECOMMENDATION

「室内植物管理を対象としたIoTセンシング・可視化システムの開発と運用評価」を推奨。「長期運用評価」は約4か月の記録期間から期間面では支持できるが、長期連続正常運転を意味する表現は不適切。全期間欠測・構成変更・復元行・事故後対象の整理が必要。事故記録にはベランダ環境があるため「室内」と実験環境の整合にも注意する。

## 9. ABSTRACT_READY_FACTS

> Raspberry Piと複数センサー、クラウドデータベースを用いた植物管理支援システムを構築した。主要系列では2026年6月13日から10月13日までに35,407件の記録を確認した。実装の既定測定周期である5分に基づいて観測枠を定義したところ、7月22日13時05分から8月2日19時15分までの取得率は99.91%であった。一方、同日0時開始の区間では95.44%となり、評価区間によって結果が異なった。また、複数センサー値の急変後に約39時間の記録途絶が確認され、平常時の記録取得性能と異常発生時の監視継続性を分けて評価する必要性が示された。

SQLite実験、生育効果、通知有効性は追加検証後に記載する。
