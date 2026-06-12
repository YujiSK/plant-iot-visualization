-- Secondary sensor nodes may not have ambient temperature/humidity sensors.
-- Existing values are preserved; only the NOT NULL constraints are removed.

alter table public.sensor_logs
  alter column temperature drop not null,
  alter column humidity drop not null;
