alter table public.sensor_logs enable row level security;

drop policy if exists "sensor_logs_anon_select" on public.sensor_logs;

create policy "sensor_logs_anon_select"
on public.sensor_logs
for select
to anon
using (true);
