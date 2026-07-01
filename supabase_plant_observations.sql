-- Structured AI observation records created from Slack plant photos.
-- Apply this before enabling normalized plant observation storage.

create table if not exists public.plant_observations (
  id uuid primary key default gen_random_uuid(),
  observed_at timestamptz not null,
  sensor_log_id bigint references public.sensor_logs(id) on delete set null,
  device_id text not null,
  location_id text not null,
  image_url text,
  growth_stage text not null check (
    growth_stage in (
      'seed',
      'germination',
      'cotyledon',
      'true_leaf_1',
      'true_leaf_2',
      'vegetative'
    )
  ),
  true_leaf_detected boolean,
  true_leaf_pair_count integer check (
    true_leaf_pair_count is null or true_leaf_pair_count >= 0
  ),
  plant_count_estimate integer check (
    plant_count_estimate is null or plant_count_estimate >= 0
  ),
  crowding text check (
    crowding is null or crowding in ('low', 'medium', 'high', 'unknown')
  ),
  leaf_color text check (
    leaf_color is null or leaf_color in ('green', 'pale', 'yellowing', 'mixed', 'unknown')
  ),
  leaf_size text check (
    leaf_size is null or leaf_size in ('small', 'medium', 'large', 'unknown')
  ),
  wilting boolean,
  yellowing boolean,
  root_visibility boolean,
  root_length_estimate numeric check (
    root_length_estimate is null or root_length_estimate >= 0
  ),
  confidence numeric check (
    confidence is null or (confidence >= 0 and confidence <= 1)
  ),
  summary text,
  next_action text,
  raw_ai_json jsonb not null,
  model text,
  created_at timestamptz not null default now()
);

create index if not exists plant_observations_device_observed_at_idx
  on public.plant_observations (device_id, observed_at desc);

create index if not exists plant_observations_growth_stage_idx
  on public.plant_observations (growth_stage, observed_at desc);

create index if not exists plant_observations_sensor_log_id_idx
  on public.plant_observations (sensor_log_id);

alter table public.plant_observations enable row level security;

drop policy if exists plant_observations_anon_select
  on public.plant_observations;
drop policy if exists plant_observations_anon_insert
  on public.plant_observations;

create policy plant_observations_anon_select
on public.plant_observations
for select
to anon
using (true);

create policy plant_observations_anon_insert
on public.plant_observations
for insert
to anon
with check (true);
