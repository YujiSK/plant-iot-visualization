-- Identify readings from multiple Raspberry Pis and store float switch state.
-- Existing rows remain valid because all new columns are nullable.

alter table public.sensor_logs
  add column if not exists device_id text,
  add column if not exists location_id text,
  add column if not exists float_switch_triggered boolean,
  add column if not exists float_switch_state text;

create index if not exists sensor_logs_device_created_at_idx
  on public.sensor_logs (device_id, created_at desc);

