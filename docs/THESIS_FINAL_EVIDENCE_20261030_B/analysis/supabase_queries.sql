-- Reproduction SQL for Supabase project oawkrkgnjkldfyvjcrgx (read-only SELECT).
-- The numbers in this audit were computed by supabase_eval.py from a PostgREST GET
-- snapshot (2026-10-30 17:52 JST); these queries implement the same definitions so
-- they can be re-run in the Supabase SQL editor. All local times Asia/Tokyo.

-- Q:main_series  (expect 35407, 2026-06-13 01:22:21.972648 .. 2026-10-13 10:35:00.669265 JST)
SELECT count(*),
       min(created_at AT TIME ZONE 'Asia/Tokyo'),
       max(created_at AT TIME ZONE 'Asia/Tokyo')
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float';

-- Q:monthly  rows and valid-field rows per JST month
SELECT to_char(created_at AT TIME ZONE 'Asia/Tokyo', 'YYYY-MM') AS month_jst,
       count(*) AS rows,
       count(*) FILTER (WHERE solution_temperature BETWEEN 0 AND 50) AS temp_valid,
       count(*) FILTER (WHERE light_lux >= 0) AS lux_valid,
       count(*) FILTER (WHERE float_switch_state IN ('water_ok','low_water')) AS float_valid
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
GROUP BY 1 ORDER BY 1;

-- Q:null_rates
SELECT count(*) AS n,
       round(100.0 * count(*) FILTER (WHERE solution_temperature IS NULL) / count(*), 2) AS temp_null_pct,
       round(100.0 * count(*) FILTER (WHERE light_lux IS NULL) / count(*), 2) AS lux_null_pct,
       count(*) FILTER (WHERE solution_temperature = 85.0) AS temp_85c
FROM public.sensor_logs
WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float';

-- Q:slot_coverage  nearest 300 s slot, window [A,B) (set :a/:b; for inclusive end use B+300 s)
-- slot = 300*floor((epoch+150)/300); A = record exists; B = all three fields valid in the slot
WITH params AS (
  SELECT timestamptz '2026-09-09 15:10:00+09' AS a, timestamptz '2026-10-13 10:40:00+09' AS b
), expected AS (
  SELECT generate_series(extract(epoch FROM a)::bigint, extract(epoch FROM b)::bigint - 300, 300) AS slot
  FROM params
), mapped AS (
  SELECT (300 * floor((extract(epoch FROM created_at) + 150) / 300))::bigint AS slot,
         bool_or(solution_temperature BETWEEN 0 AND 50 AND light_lux >= 0
                 AND float_switch_state IN ('water_ok','low_water')) AS all3
  FROM public.sensor_logs
  WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float'
  GROUP BY 1
)
SELECT count(*) AS expected_slots,
       count(m.slot) AS a_record_slots,
       round(100.0 * count(m.slot) / count(*), 2) AS a_pct,
       count(*) FILTER (WHERE m.all3) AS b_all3_slots,
       round(100.0 * count(*) FILTER (WHERE m.all3) / count(*), 2) AS b_pct
FROM expected e LEFT JOIN mapped m USING (slot);

-- Q:gaps  longest inter-record gaps
SELECT created_at AT TIME ZONE 'Asia/Tokyo' AS to_jst,
       prev AT TIME ZONE 'Asia/Tokyo' AS from_jst,
       created_at - prev AS gap
FROM (SELECT created_at, lag(created_at) OVER (ORDER BY created_at, id) AS prev
      FROM public.sensor_logs
      WHERE device_id = 'raspberrypi2' AND source = 'raspberrypi2-ds18b20-bh1750-float') s
WHERE prev IS NOT NULL ORDER BY gap DESC LIMIT 8;

-- Q:null_onset  rows around the last non-NULL temperature/lux and vitality after onset
SELECT id, created_at AT TIME ZONE 'Asia/Tokyo' AS t_jst, solution_temperature, light_lux,
       float_switch_state, vitality_score, message
FROM public.sensor_logs
WHERE source = 'raspberrypi2-ds18b20-bh1750-float'
  AND created_at BETWEEN '2026-09-09 14:50+09' AND '2026-09-09 16:20+09'
ORDER BY created_at;

SELECT vitality_score, message, count(*)
FROM public.sensor_logs
WHERE source = 'raspberrypi2-ds18b20-bh1750-float' AND created_at > '2026-09-09 15:09:59.462379+09'
GROUP BY 1, 2 ORDER BY 3 DESC;

-- Q:duplicate_timestamp  (found: ids 39518/39519 at 2026-10-02 05:29:59.032954 JST)
SELECT created_at, array_agg(id ORDER BY id), count(*)
FROM public.sensor_logs
WHERE source = 'raspberrypi2-ds18b20-bh1750-float'
GROUP BY created_at HAVING count(*) > 1;

-- Q:observations  AI observation records and sensor linkage
SELECT model, count(*), count(sensor_log_id) AS sensor_linked,
       min(observed_at AT TIME ZONE 'Asia/Tokyo'), max(observed_at AT TIME ZONE 'Asia/Tokyo')
FROM public.plant_observations GROUP BY model;
