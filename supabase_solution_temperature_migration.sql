-- Add DS18B20 solution temperature to existing sensor logs.
-- Existing rows remain valid with a NULL solution_temperature.

alter table public.sensor_logs
  add column if not exists solution_temperature numeric;
