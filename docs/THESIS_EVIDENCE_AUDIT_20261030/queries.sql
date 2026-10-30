-- series
SELECT device_id,source,count(*) n,min(created_at) AT TIME ZONE 'Asia/Tokyo' first_jst,max(created_at) AT TIME ZONE 'Asia/Tokyo' last_jst FROM sensor_logs GROUP BY device_id,source ORDER BY device_id,source;

-- monthly
SELECT device_id,source,to_char(created_at AT TIME ZONE 'Asia/Tokyo','YYYY-MM') month_jst,count(*) n FROM sensor_logs GROUP BY 1,2,3 ORDER BY 1,2,3;

-- preaccident
SELECT source,count(*) n,min(created_at) AT TIME ZONE 'Asia/Tokyo' first_jst,max(created_at) AT TIME ZONE 'Asia/Tokyo' last_jst FROM sensor_logs WHERE device_id='raspberrypi2' AND created_at>='2026-07-22 00:00+09' AND created_at<'2026-08-02 19:15+09' GROUP BY source;

-- care
SELECT id,action_type,created_at AT TIME ZONE 'Asia/Tokyo' time_jst,left(regexp_replace(note,'https?://[^\s]+','[URL]','g'),3500) note FROM care_logs WHERE (created_at>='2026-07-01' AND created_at<'2026-08-10') OR note ~ '倒伏|倒れ|給水|10月|10/19' ORDER BY created_at;

-- tables
SELECT 'sensor_logs' table_name,count(*) n,min(created_at) first_utc,max(created_at) last_utc FROM sensor_logs UNION ALL SELECT 'care_logs',count(*),min(created_at),max(created_at) FROM care_logs UNION ALL SELECT 'plant_observations',count(*),min(observed_at),max(observed_at) FROM plant_observations;

-- daily
SELECT device_id,source,(created_at AT TIME ZONE 'Asia/Tokyo')::date day_jst,count(*) n,count(DISTINCT floor(extract(epoch from created_at)/300)) bins_5min FROM sensor_logs GROUP BY 1,2,3 ORDER BY 1,2,3;

-- gaps
WITH s AS (SELECT device_id,source,created_at,lag(created_at) OVER(PARTITION BY device_id,source ORDER BY created_at,id) prev FROM sensor_logs) SELECT device_id,source,prev AT TIME ZONE 'Asia/Tokyo' prev_jst,created_at AT TIME ZONE 'Asia/Tokyo' next_jst,extract(epoch FROM created_at-prev) seconds FROM s WHERE prev IS NOT NULL ORDER BY created_at-prev DESC LIMIT 25;

-- intervals
WITH s AS (SELECT device_id,source,extract(epoch FROM created_at-lag(created_at) OVER(PARTITION BY device_id,source ORDER BY created_at,id)) dt FROM sensor_logs) SELECT device_id,source,count(dt) n,min(dt),percentile_cont(ARRAY[0.05,0.5,0.95,0.99]) WITHIN GROUP(ORDER BY dt) percentiles,max(dt),count(*) FILTER(WHERE dt=0) duplicate_timestamps,count(*) FILTER(WHERE dt<60) under_60s,count(*) FILTER(WHERE dt>600) over_600s FROM s GROUP BY 1,2;

-- coverage
WITH periods(label,a,b) AS (VALUES ('preaccident','2026-07-22 00:00+09'::timestamptz,'2026-08-02 19:15+09'::timestamptz),('after_recovery','2026-07-22 13:00+09'::timestamptz,'2026-08-02 19:15+09'::timestamptz),('full_grid','2026-06-13 01:20+09'::timestamptz,'2026-10-13 10:40+09'::timestamptz)) SELECT label,a,b,extract(epoch FROM b-a)/300 expected,count(s.id) rows,count(DISTINCT floor(extract(epoch FROM s.created_at)/300)) occupied_bins FROM periods LEFT JOIN sensor_logs s ON s.created_at>=a AND s.created_at<b AND s.device_id='raspberrypi2' AND s.source='raspberrypi2-ds18b20-bh1750-float' GROUP BY label,a,b;

-- distribution
WITH s AS (SELECT CASE WHEN created_at>='2026-07-22 00:00+09' AND created_at<'2026-08-02 19:15+09' THEN 'preaccident' ELSE 'other' END period,* FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float') SELECT period,count(*) n,count(solution_temperature) temp_n,min(solution_temperature),max(solution_temperature),avg(solution_temperature),percentile_cont(ARRAY[0.05,0.5,0.95]) WITHIN GROUP(ORDER BY solution_temperature) temp_percentiles,count(light_lux) lux_n,min(light_lux) lux_min,max(light_lux) lux_max,avg(light_lux) lux_avg,percentile_cont(ARRAY[0.05,0.5,0.95]) WITHIN GROUP(ORDER BY light_lux) lux_percentiles,count(*) FILTER(WHERE float_switch_state='low_water') low_water,count(*) FILTER(WHERE float_switch_state='water_ok') water_ok,count(*) FILTER(WHERE float_switch_state IS NULL) float_null,min(vitality_score) vitality_min,max(vitality_score) vitality_max,avg(vitality_score) vitality_avg FROM s GROUP BY period;

-- nearest_coverage
WITH periods(label,a,b) AS (VALUES ('preaccident','2026-07-22 00:00+09'::timestamptz,'2026-08-02 19:15+09'::timestamptz),('after_recovery','2026-07-22 13:00+09'::timestamptz,'2026-08-02 19:15+09'::timestamptz),('full_grid','2026-06-13 01:20+09'::timestamptz,'2026-10-13 10:40+09'::timestamptz)), s AS (SELECT *,floor((extract(epoch FROM created_at)+150)/300)*300 slot FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float') SELECT label,extract(epoch FROM b-a)/300 expected,count(s.id) rows,count(DISTINCT slot) occupied,count(DISTINCT slot) FILTER(WHERE solution_temperature IS NOT NULL AND light_lux IS NOT NULL AND float_switch_state IS NOT NULL) complete_slots FROM periods LEFT JOIN s ON slot>=extract(epoch FROM a) AND slot<extract(epoch FROM b) GROUP BY label,a,b;

-- daily_quality
SELECT (created_at AT TIME ZONE 'Asia/Tokyo')::date day_jst,count(*) n,count(solution_temperature) temp_n,count(light_lux) lux_n,count(*) FILTER(WHERE float_switch_state='low_water') low_water,min(solution_temperature) temp_min,max(solution_temperature) temp_max,count(DISTINCT floor((extract(epoch FROM created_at)+150)/300)) nearest_slots FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float' GROUP BY 1 ORDER BY 1;

-- anomalies
SELECT 'temp85' kind,count(*) n,min(created_at) first_utc,max(created_at) last_utc FROM sensor_logs WHERE device_id='raspberrypi2' AND solution_temperature=85 UNION ALL SELECT 'temperature_null',count(*),min(created_at),max(created_at) FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float' AND solution_temperature IS NULL UNION ALL SELECT 'lux_null',count(*),min(created_at),max(created_at) FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float' AND light_lux IS NULL;

-- accident_values
SELECT id,created_at AT TIME ZONE 'Asia/Tokyo' time_jst,solution_temperature,light_lux,float_switch_state,vitality_score FROM sensor_logs WHERE device_id='raspberrypi2' AND created_at>='2026-08-02 18:45+09' AND created_at<'2026-08-02 19:30+09' ORDER BY created_at;

-- constraints
SELECT indexdef FROM pg_indexes WHERE schemaname='public' AND tablename='sensor_logs';

-- obs
SELECT id,observed_at AT TIME ZONE 'Asia/Tokyo' observed_jst,created_at AT TIME ZONE 'Asia/Tokyo' created_jst,device_id,model,wilting,yellowing,left(summary,600) summary,raw_ai_json->>'backfilled' backfilled FROM plant_observations ORDER BY observed_at;

-- formal_normalized
WITH slots AS (SELECT generate_series('2026-07-22 13:05+09'::timestamptz,'2026-08-02 19:15+09'::timestamptz,interval '5 min') t), matched AS (SELECT t,s.* FROM slots LEFT JOIN LATERAL (SELECT id,created_at,solution_temperature,light_lux,float_switch_state,vitality_score FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float' AND created_at>=t-interval '150 seconds' AND created_at<t+interval '150 seconds' ORDER BY abs(extract(epoch FROM created_at-t)),id LIMIT 1) s ON true) SELECT count(*) expected,count(id) matched,array_agg(t AT TIME ZONE 'Asia/Tokyo') FILTER(WHERE id IS NULL) missing,avg(abs(extract(epoch FROM created_at-t))) mean_offset,percentile_cont(ARRAY[0.5,0.95]) WITHIN GROUP(ORDER BY abs(extract(epoch FROM created_at-t))) offset_percentiles,max(abs(extract(epoch FROM created_at-t))) max_offset,avg(solution_temperature) temp_mean,stddev_samp(solution_temperature) temp_sd,min(solution_temperature) temp_min,max(solution_temperature) temp_max,percentile_cont(ARRAY[0.25,0.5,0.75]) WITHIN GROUP(ORDER BY solution_temperature) temp_quartiles,count(*) FILTER(WHERE solution_temperature>=30) temp_ge30,count(*) FILTER(WHERE solution_temperature>=35) temp_ge35,avg(light_lux) lux_mean,percentile_cont(ARRAY[0.5,0.95]) WITHIN GROUP(ORDER BY light_lux) lux_percentiles,count(*) FILTER(WHERE float_switch_state='low_water') low_water,avg(vitality_score) vitality_mean FROM matched;

-- valid_ranges
SELECT min(created_at) FILTER(WHERE solution_temperature IS NOT NULL) AT TIME ZONE 'Asia/Tokyo' temp_first,max(created_at) FILTER(WHERE solution_temperature IS NOT NULL) AT TIME ZONE 'Asia/Tokyo' temp_last,max(created_at) FILTER(WHERE light_lux IS NOT NULL) AT TIME ZONE 'Asia/Tokyo' lux_last,count(*) FILTER(WHERE solution_temperature=85) temp85,count(*) FILTER(WHERE solution_temperature<0 OR solution_temperature>50) temp_outside_screen,count(*) FILTER(WHERE light_lux<0 OR light_lux>60000) lux_outside_screen FROM sensor_logs WHERE device_id='raspberrypi2' AND source='raspberrypi2-ds18b20-bh1750-float';

-- other_distributions
SELECT device_id,source,count(*) n,count(temperature) temp_n,min(temperature) temp_min,max(temperature) temp_max,percentile_cont(0.5) WITHIN GROUP(ORDER BY temperature) temp_median,count(humidity) humidity_n,min(humidity) humidity_min,max(humidity) humidity_max,count(pressure) pressure_n,min(water_raw) water_min,max(water_raw) water_max,min(light_raw) light_min,max(light_raw) light_max FROM sensor_logs WHERE device_id IS DISTINCT FROM 'raspberrypi2' GROUP BY 1,2;
