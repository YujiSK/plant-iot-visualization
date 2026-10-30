# PLANT-IOT-THESIS-BOT-FUNCTION-AUDIT

監査日：2026-10-30（JST）。対象：raspi2 / 100.99.153.127 / `/home/pi/plant-iot`。本書の新規作成以外は読み取り専用。外部通知・AIリクエスト・テスト実行・サービス操作・既存ファイル変更・commit・pushは実施していない。

## 1. SYSTEM_ARCHITECTURE

センサー処理 → Supabase送信／SQLite Outboxと、LINE Push・Slack Webhook通知は別経路。Slack写真投稿 → Cloudflare Quick Tunnel → FastAPI `/slack/events` → 画像取得 → 近傍センサー照会 → 画像AI → `care_logs`／`plant_observations` → Slackスレッド返信。

証拠階層を区別する：コード＝実装、systemd＝プロセス状態、DB＝保存済み成果物、journal＝処理記録、PROJECT_LOG＝過去の実施報告。いずれも単独では利用者の理解・管理改善の証明にならない。

実機HEAD：`a288f6d4fc0703fce2cd1f4f7ac208acd11ebef1`（2026-07-22 13:02:38 JST）。監査前の `git status --short` と `git diff --stat` は空。GitHubの前回監査HEAD `32b09a4...`（9月18日）とは異なる。現行実機コードを優先し、過去の全運用期間に同じ実装が配備されていたとは仮定しない。

出典：`AGENTS.md`、`plant-slack-observation.service`、`slack_observation_bot.py:709–965`、`slack_notifier.py:120–226`、`alert_manager.py:108–251`。行番号は実機取得版。

## 2. LINE_IMPLEMENTATION

- LINE Messaging APIのPush送信を実装。宛先は環境設定、本文は最大5,000文字に切り詰め、HTTPタイムアウト10秒。HTTPエラーがなければ成功として返す（`slack_notifier.py:135–165`）。利用者の既読は取得しない。
- 低水位・復旧通知：`device_id=raspberrypi2` の `float_switch_state` を判定。低水位継続中は重複通知を抑止し、復旧は呼出側指定の確認回数を使用（関数既定2回）。呼出側の条件を無視して「必ず2回」とは記載できない（同:55–81,168–226）。
- 送信障害：連続失敗3回、継続障害の再通知は1時間間隔、成功後の復旧通知を実装（`alert_manager.py:44,126–251`）。
- ヘルスチェック実装はあるが、定期実行用timerは今回非稼働。定期通知が現在動いているとはいえない。
- 利用者メッセージの受信Webhook、LINE Reply API、対話的な最新センサー照会は、調査した関連コードでは確認できない。LINEは「通知連携」と表現するのが適切。
- `sent = slack_sent or line_sent` で共通状態を更新するため、共通の成功ログはLINE成功の証拠ではない。一方のみ成功すると、もう一方への低水位通知は次回重複抑止の対象となり得る。両経路を独立に再送保証する実装ではない。

過去のLINE成功はPROJECT_LOGの7月22日E2E実施報告に記載されるが、今回のjournalから独立確認できない。保守的分類はC（過去の実施報告あり）。

## 3. SLACK_IMPLEMENTATION

- Webhook通知はLINEと同じ低水位・復旧・送信障害経路。HTTP応答成功と利用者の受信・閲覧は別。
- Events API入口で署名HMAC-SHA256と時刻差5分以内を検証し、URL verificationに応答（`slack_observation_bot.py:909–965`）。
- 指定チャンネルのmessageイベントから最初の画像を抽出。Bot投稿を除外。自由文だけの一般対話やセンサー照会コマンドは確認できない（同:142–166）。
- 投稿時刻前後10分、同じdevice_idのセンサー行から最も近い行を選択する。近傍行がなくても観察処理は継続し得る（同:180–220）。近傍というだけで撮影時刻との一致は保証されない。
- 投稿時刻・SlackファイルID・画像SHA256による重複チェック、観察とAI結果のDB保存、前回との比較、スレッド返信を実装（同:576–633,709–905）。
- `chat.postMessage` はHTTP成功に加えてJSON `ok` を確認し、返信成功ログを出す（同:674–705）。DB保存成功と返信成功は別の戻り値。
- AI失敗時もcare_logs保存を試み、エラーを記録する。care_logs保存失敗時には警告返信を試みる。DB二段階保存とSlack返信は一つのトランザクションではなく、部分成功があり得る。
- `/slack/events` はAI・DB・返信を同期的に処理してから応答する。遅い処理時の再配信・重複競合の可能性があるが、今回その発生を実測したわけではない。

## 4. AI_SUPPORT_FUNCTIONS

実装：OpenAI Responses API、Gemini generateContent API。実機ファイルのモデル既定値は `gpt-4.1` と `gemini-3.5-flash`。`.env`の非秘密設定のみを許可リストで確認した結果はprovider=`gemini`、Gemini=`gemini-3.5-flash`、OpenAI=`gpt-4o-mini`。ファイル上の設定であり、起動済みプロセスのロード済み値は別途未確認。モデル名はコード・DBの記録文字列であり、API提供状況を検証したものではない。

入力：写真バイト列、投稿テキスト、観察時刻、device/location、近傍センサー値。出力：生育段階、本葉・子葉、推定株数、混雑度、葉色・大きさ、萎れ・黄化、根、confidence、要約、次の確認・助言。プロンプトは「病害診断ではなく観察支援」と制限し、不明瞭画像では保守的判定を求める（`ai_observation.py:175–281,532–561`）。

ルールベースとの差：画像解釈・自然言語助言がモデル処理。低水位通知、送信障害判定、前回との項目比較、値の正規化はプログラム処理。全機能をAIと呼ばない。

検証機構：JSON形式、列挙値正規化、confidenceの0〜1制限、型変換、画像同一性、前回比較。これらは形式・整合性の検査であり、植物学的正解の保証ではない。人手正解ラベル、専門家一致率、診断精度、助言効果の評価は確認できない。

重要な限界（`ai_observation.py:152–172,615–654`）：

- 画像またはAPIキーがない場合、固定の子葉段階・20株・緑色などを含むfallback辞書を返す。実際の画像推論結果と混ぜて集計してはいけない。
- normalizeで既定キーを生成した後にrequiredキーを検査するため、欠落検出は強くない。`bool(value)`による変換は文字列の真偽表現を厳密に検証しない。
- confidenceはモデル出力または固定値であり、校正済みの正答確率ではない。
- GeminiはTimeout/ConnectionErrorおよび429/500/502/503/504で候補モデルへフォールバック（既定 `gemini-3.1-flash-lite`）。全候補失敗時は例外。永続AIジョブキューの存在は確認できない。
- `AI observation success` はfallback返却でも通る呼出側構造のため、ログ名だけで外部モデル推論成功と断定しない。

## 5. OPERATIONAL_EVIDENCE

監査日の `systemctl show ... -p Id -p ActiveState -p SubState -p ActiveEnterTimestamp -p FragmentPath`：

| 対象 | 結果 |
|---|---|
| plant-slack-observation.service | active/running、ActiveEnterTimestamp=2026-10-13 10:39:00 JST |
| cloudflared-quick-tunnel.service | list-unitsでactive/running |
| plant-sensor-raspberrypi2.service | inactive/dead |
| plant-supabase-health.timer | inactive/dead、FragmentPath空 |

プロセス稼働は外部SlackのRequest URL設定・現在のE2E疎通成功を証明しない。監査でテスト送信はしていない。

`journalctl -u UNIT -o json --no-pager`をメモリ上で集計し、本文・URL・資格情報は出力せず既知のイベント名だけ照合：

- Slack Bot：359行、最初2026-10-13 10:39:00.638513、最後2026-10-30 17:13:54.811900 JST。
- この範囲の `AI observation start/success/failed`、`Slack reply sent/failed` は各0件。標準形式の `POST /slack/events` アクセスログも0件。
- sensorサービスとhealthサービスの閲覧可能journalは各0行。
- これは「保持・閲覧できたログに該当記録なし」であり、全期間の利用・失敗が0という意味ではない。

PROJECT_LOG.md:680–691には写真投稿イベント、HTTP 200、Slack返信、care_logs作成の実機E2E確認が記載。:824–834にはLINE/Slack障害・復旧通知試験10ステップ成功と記載。過去の実施報告として引用できるが、原本の送受信ログによる今回の再検証とは区別する。

Supabaseプロジェクト `oawkrkgnjkldfyvjcrgx` に対する読み取りSQL：

```sql
SELECT model, count(*) AS n, min(observed_at), max(observed_at),
       count(sensor_log_id) AS sensor_linked,
       count(*) FILTER (WHERE raw_ai_json ? 'image_sha256') AS image_hash_present
FROM plant_observations GROUP BY model;
```

| 保存モデル文字列 | 件数 | observed_at範囲（JST） | センサー関連付け | hashキーあり |
|---|---:|---|---:|---:|
| gemini-3.5-flash | 5 | 6/17 03:37:32〜7/5 04:58:21.631609 | 5 | 4 |
| gemini-3.1-flash-lite | 2 | 7/11 18:31:05.949099〜7/15 23:34:34.319649 | 0 | 2 |

計7件は保存成果物の存在を示す。うち5件にsensor_log_idがある（71.43%）。成功率の分母ではない。observed_atはAPI実行時刻ではなく、後日補完・backfillの可能性もある。7件をSlack送信成功数やリアルタイムAI実行数と同一視しない。

再現用ソースSHA256：

- ai_observation.py: `504685f20242d59dd160465b2d3075c10c8649df6ded7b7ea3d93ee62c3564c3`
- slack_observation_bot.py: `88ac02ad1e8e20d4ae7cac9b9b23d7c40eeaab6a268565635c73e913fea37737`
- slack_notifier.py: `4be3d819eb8b44593213e4200e263aa456c9c3a1176c68e95475ba50dfee80e7`
- alert_manager.py: `2bc8dee47ac9dcbae0bec8202f5e369cd4b3edeb28f2e717963edc813c64557c`

## 6. QUANTITATIVE_EVALUATION_POTENTIAL

| 指標 | 今回の算出可否・必要証拠 |
|---|---|
| AI観察保存件数 | 7件。モデル別件数は上記。正答率ではない |
| 通知送信件数 | 不可。LINE/Slack別の試行・応答ログが不足 |
| 送信成功率 | 不可。経路別成功試行数／全試行数が必要。共通OR成功を分子にしない |
| 失敗率 | 不可。経路別失敗試行数／全試行数。未確定応答を別区分にする |
| 応答時間 | 不可。受信イベントIDと返信API完了時刻の対応が必要 |
| 通知遅延 | 不可。発生・検知・送信・API受理・利用者受信を別時刻で記録する必要 |
| 異常検知→通知 | 不可。同じイベントIDの検知時刻と経路別送信完了時刻が必要 |
| 再送・復旧 | 実装確認可。OutboxはセンサーDB送信の仕組みで、通知の永続再送保証ではない |
| ユーザー操作 | 写真イベントからユーザー・投稿・画像情報を扱う実装あり。既読、理解、給水実施、効果の完全な操作履歴ではない |

将来評価は期間・タイムゾーン・試行単位・重複除外・backfill/fallback区別を固定する。平均だけでなく中央値・p95、件数と失敗理由を併記。生育管理効果は通知送信の評価とは分離し、人の対応記録と比較条件が必要。

## 7. VERIFIED_VS_UNVERIFIED

A=実装・実稼働・評価済み、B=実装・実稼働済みだが定量評価なし、C=実装済み・実稼働未確認、D=構想・試作のみ。Bの根拠がDB保存か過去報告かを明示する。Aには独立に追跡可能な評価結果を要求する。

| 機能 | 判定 | 根拠と制限 |
|---|---|---|
| LINE Push低水位・復旧／送信障害通知 | C | 実装と過去試験報告あり。経路別成功原本なし |
| LINE受信応答・状態照会 | 未確認（A〜D判定不可） | 実装も構想資料も確認できず、Dを推測付与しない |
| Slack Webhook異常通知 | C | LINEと同じOR成功問題。現在の発火元はinactive |
| Slack写真受信→記録→返信 | B（過去実施報告に依存） | PROJECT_LOGのE2E報告。現在はプロセス稼働のみ直接確認 |
| AI観察結果保存 | B（保存実績） | モデル名付きDB7件。API原応答・全投稿との対応は未照合 |
| センサー・AI観察関連付け | B（保存実績） | 7件中5件に関連IDあり。情報の正確性評価なし |
| OpenAI経由の画像推論 | C | 経路実装あり、今回の保存モデルには見当たらない |
| 前回比較・助言の妥当性 | C | 実装あり、精度・利用成果の検証なし |
| ヘルスチェック定期通知 | C | 実装あり、現在timer非稼働 |
| 専用アプリ移植・再撮影支援等 | D | NEXT_ACTIONSの将来検討項目。現在実装と混同しない |

Aと判断できる機能は今回なし。過去E2E報告を否定するものではなく、定量評価・原本再確認の証拠水準による判断。

## 8. THESIS_CONTRIBUTION

採用可能：写真観察・環境センシング・記録保存・メッセージ返信を統合する実装、運用記録、部分故障時の処理継続、通知経路の状態管理上の限界。研究的価値は「観察・記録の支援基盤と運用上の課題」に置く。

主要成果とするには不足：AI診断精度、管理時間短縮、状態理解向上、給水改善、生育改善、枯死防止。写真数が少なく、正解ラベル・対照条件・利用者評価・全試行ログがない。通知二重化を無条件の信頼性向上とせず、OR成功による片経路失敗の見落としを限界として記載する。

現在の論文ではセンシング・可視化・運用評価を主軸とし、BotとAIは補助機能または探索的実装として扱うのが証拠に整合する。

## 9. ABSTRACT_READY_FACTS

> 植物の写真観察とセンサー記録を統合するSlack観察支援機能、およびLINE・Slackへの異常通知機能を実装した。監査時点でモデル名付きの観察記録7件が保存され、そのうち5件にセンサー記録との関連付けを確認した。一方、通知経路別の送信成功率、応答時間、AI判定精度、利用者の管理改善効果は未評価である。これらの機能は観察・記録支援の実装成果として位置付け、効果の検証とは区別した。

「LINEとの対話」「AIによる正確な診断」「通知で枯死を防止」「二重通知の成功率100%」は今回の証拠では記載できない。
