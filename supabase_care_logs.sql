-- care_logs table for Flutter management-support app.
-- Public clients must use only the anon public key with RLS.
-- Never place service_role keys in Flutter or GitHub Pages.

create table if not exists public.care_logs (
  id uuid primary key default gen_random_uuid(),
  action_type text not null check (
    action_type in ('watered', 'moved', 'checked', 'memo')
  ),
  note text,
  sensor_log_id bigint references public.sensor_logs(id) on delete set null,
  temperature numeric,
  humidity numeric,
  pressure numeric,
  vitality_score integer,
  message text,
  created_at timestamptz not null default now()
);

alter table public.care_logs enable row level security;

drop policy if exists care_logs_anon_select on public.care_logs;
drop policy if exists care_logs_anon_insert on public.care_logs;

create policy care_logs_anon_select
on public.care_logs
for select
to anon
using (true);

create policy care_logs_anon_insert
on public.care_logs
for insert
to anon
with check (
  action_type in ('watered', 'moved', 'checked', 'memo')
);
