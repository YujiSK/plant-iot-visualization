-- Add current wired sensor fields to sensor_logs.
-- Existing Sense HAT-era temperature/humidity/pressure rows remain valid.

alter table public.sensor_logs
  add column if not exists water_raw integer,
  add column if not exists water_voltage numeric,
  add column if not exists water_status text,
  add column if not exists light_raw integer,
  add column if not exists light_voltage numeric,
  add column if not exists light_status text;
