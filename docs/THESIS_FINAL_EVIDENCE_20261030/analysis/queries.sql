-- THESIS_FINAL_EVIDENCE_20261030: reproducible read-only SQL (PostgreSQL / Supabase).
-- These mirror analysis/supabase_eval.py. Run only SELECTs. Times reported in Asia/Tokyo.
-- Main series = device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float'.

-- Q:series  device/source inventory
SELECT device_id, source, count(*) AS n,
       min(created_at AT TIME ZONE 'Asia/Tokyo') AS first_jst,
       max(created_at AT TIME ZONE 'Asia/Tokyo') AS last_jst
FROM public.sensor_logs GROUP BY 1, 2 ORDER BY 4;

-- Q:monthly  rows and NULL rates per JST month
SELECT to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS month, count(*) AS n,
       round(100.0 * count(*) FILTER (WHERE solution_temperature IS NULL) / count(*), 2) AS temp_null_pct,
       round(100.0 * count(*) FILTER (WHERE light_lux IS NULL) / count(*), 2) AS lux_null_pct,
       count(*) FILTER (WHERE solution_temperature = 85.0) AS temp_85
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
GROUP BY 1 ORDER BY 1;

-- Q:window_ab  A (record) and B (valid) slot coverage for a half-open window [:a, :b)
-- Example values: P6 = ['2026-09-09 15:10+09', '2026-10-13 10:40+09')
WITH params AS (SELECT timestamptz '2026-09-09 15:10+09' AS a, timestamptz '2026-10-13 10:40+09' AS b),
slots AS (
  SELECT to_timestamp(300 * floor((extract(epoch FROM created_at) + 150) / 300)) AS slot,
         bool_or(solution_temperature BETWEEN 0 AND 50) AS t_ok,
         bool_or(light_lux >= 0) AS l_ok,
         bool_or(float_switch_state IN ('water_ok', 'low_water')) AS f_ok
  FROM public.sensor_logs
  WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
  GROUP BY 1),
expected AS (
  SELECT generate_series(a, b - interval '5 minutes', interval '5 minutes') AS slot FROM params)
SELECT count(*) AS expected_slots,
       count(s.slot) AS a_record_slots,
       round(100.0 * count(s.slot) / count(*), 2) AS a_pct,
       count(*) FILTER (WHERE s.t_ok AND s.l_ok AND s.f_ok) AS b_all3_slots,
       round(100.0 * count(*) FILTER (WHERE s.t_ok AND s.l_ok AND s.f_ok) / count(*), 2) AS b_all3_pct
FROM expected e LEFT JOIN slots s USING (slot);

-- Q:gaps  longest internal gaps
SELECT created_at AT TIME ZONE 'Asia/Tokyo' AS to_jst,
       lag(created_at) OVER w AT TIME ZONE 'Asia/Tokyo' AS from_jst,
       created_at - lag(created_at) OVER w AS gap
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
WINDOW w AS (ORDER BY created_at)
ORDER BY gap DESC NULLS LAST LIMIT 8;

-- Q:last_valid  last non-NULL temperature / illuminance
SELECT max(created_at) FILTER (WHERE solution_temperature IS NOT NULL) AT TIME ZONE 'Asia/Tokyo' AS temp_last,
       max(created_at) FILTER (WHERE light_lux IS NOT NULL) AT TIME ZONE 'Asia/Tokyo' AS lux_last
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float';

-- Q:sep9_vitality  vitality during the NULL period
SELECT vitality_score, float_switch_state, count(*)
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
  AND created_at >= timestamptz '2026-09-09 15:10+09'
GROUP BY 1, 2;

-- Q:duplicates  identical measurement timestamps
SELECT created_at AT TIME ZONE 'Asia/Tokyo', array_agg(id ORDER BY id), count(*)
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
GROUP BY created_at HAVING count(*) > 1;

-- Q:observations
SELECT model, count(*), count(sensor_log_id) AS linked FROM public.plant_observations GROUP BY 1;
