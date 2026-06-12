-- Add BH1750 illuminance while preserving historical photoresistor ADC fields.
-- Existing rows remain valid with a NULL light_lux.

alter table public.sensor_logs
  add column if not exists light_lux numeric;

