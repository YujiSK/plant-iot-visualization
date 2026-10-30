# 再現手順

すべて読み取り専用。秘密値は出力しない。

1. データ取得（raspi2上で実行し、標準出力を `../data/` へ保存する）
   - `ssh pi@raspberrypi2 'python3 -I -' < export_sqlite_snapshot.py > ../data/adc_snapshot_raw.csv`
   - `ssh pi@raspberrypi2 'python3 -I -' < export_outbox.py > ../data/outbox_timing.csv`
   - `ssh pi@raspberrypi2 "python3 -I - sensor_logs" < supabase_rest_export.py`（care_logs・plant_observationsも同様。最後の `__content_range__` 行を除いてjsonl化する。plant_observationsは `image_url` を伏せ、`raw_ai_json` はキー一覧だけ残した）
2. 解析（numpyとmatplotlibが必要）
   - `python3 supabase_eval.py` → `../results/supabase_eval.json`、`supabase_daily_coverage.csv`
   - `python3 moisture_eval.py` → `../results/moisture_eval.json`、`moisture_daily.csv`、`moisture_hourly.csv`
   - `python3 make_figures.py` → `../figures/*.png`
3. `queries.sql`：Supabaseで同じ指標をSELECTだけで再計算するSQL

入力データのハッシュ値：`../data/SHA256SUMS`。今回の実行では、Pythonは標準ライブラリとvenv上の numpy 2.5.4・matplotlib 3.11.2 を使用した。
