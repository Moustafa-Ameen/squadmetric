-- SquadMetric F2 account foundation.
-- Apply with the Supabase CLI or paste into the Supabase SQL editor.

create extension if not exists pgcrypto;

create or replace function public.set_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = ''
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table if not exists public.profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  display_name text check (char_length(display_name) <= 80),
  onboarding_completed boolean not null default false,
  terms_version text check (char_length(terms_version) <= 32),
  privacy_version text check (char_length(privacy_version) <= 32),
  terms_accepted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.fpl_team_links (
  user_id uuid primary key references auth.users(id) on delete cascade,
  team_id bigint not null check (team_id between 1 and 2147483647),
  source_input text check (char_length(source_input) <= 500),
  verified_team_name text check (char_length(verified_team_name) <= 120),
  verified_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.user_preferences (
  user_id uuid primary key references auth.users(id) on delete cascade,
  risk_style text not null default 'balanced' check (risk_style in ('safe', 'balanced', 'aggressive')),
  alternative_style text not null default 'both' check (alternative_style in ('popular', 'differential', 'both')),
  deadline_reminders boolean not null default true,
  email_notifications boolean not null default false,
  show_fixture_bar boolean not null default true,
  show_bench_players boolean not null default true,
  compact_table_rows boolean not null default false,
  objective_mode text not null default 'points' check (objective_mode in ('points', 'rank')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.saved_drafts (
  id text not null check (char_length(id) between 1 and 128),
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 100),
  season text not null check (char_length(season) <= 16),
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (user_id, id)
);

create table if not exists public.weekly_recommendations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  season text not null check (char_length(season) <= 16),
  gameweek smallint not null check (gameweek between 1 and 38),
  payload jsonb not null,
  decision_hash text not null check (char_length(decision_hash) <= 128),
  model_versions jsonb not null default '{}'::jsonb,
  data_cutoff timestamptz,
  created_at timestamptz not null default now(),
  unique (user_id, season, gameweek, decision_hash)
);

create table if not exists public.decision_history (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  season text not null check (char_length(season) <= 16),
  gameweek smallint not null check (gameweek between 1 and 38),
  decision_type text not null check (decision_type in ('transfer', 'captain', 'bench', 'chip', 'squad')),
  decision_payload jsonb not null,
  outcome_payload jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table if not exists public.favorite_players (
  user_id uuid not null references auth.users(id) on delete cascade,
  player_id integer not null check (player_id > 0),
  player_name text not null check (char_length(player_name) between 1 and 120),
  created_at timestamptz not null default now(),
  primary key (user_id, player_id)
);

create index if not exists saved_drafts_user_updated_idx on public.saved_drafts (user_id, updated_at desc);
create index if not exists recommendations_user_gw_idx on public.weekly_recommendations (user_id, season, gameweek desc);
create index if not exists decision_history_user_gw_idx on public.decision_history (user_id, season, gameweek desc);

drop trigger if exists profiles_set_updated_at on public.profiles;
create trigger profiles_set_updated_at before update on public.profiles for each row execute function public.set_updated_at();
drop trigger if exists fpl_team_links_set_updated_at on public.fpl_team_links;
create trigger fpl_team_links_set_updated_at before update on public.fpl_team_links for each row execute function public.set_updated_at();
drop trigger if exists user_preferences_set_updated_at on public.user_preferences;
create trigger user_preferences_set_updated_at before update on public.user_preferences for each row execute function public.set_updated_at();
drop trigger if exists saved_drafts_set_updated_at on public.saved_drafts;
create trigger saved_drafts_set_updated_at before update on public.saved_drafts for each row execute function public.set_updated_at();
drop trigger if exists decision_history_set_updated_at on public.decision_history;
create trigger decision_history_set_updated_at before update on public.decision_history for each row execute function public.set_updated_at();

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  insert into public.profiles (
    user_id,
    display_name,
    terms_version,
    privacy_version,
    terms_accepted_at
  )
  values (
    new.id,
    left(coalesce(new.raw_user_meta_data ->> 'full_name', ''), 80),
    nullif(left(coalesce(new.raw_user_meta_data ->> 'terms_version', ''), 32), ''),
    nullif(left(coalesce(new.raw_user_meta_data ->> 'privacy_version', ''), 32), ''),
    case when coalesce(new.raw_user_meta_data ->> 'legal_accepted', 'false') = 'true' then now() else null end
  )
  on conflict (user_id) do nothing;
  insert into public.user_preferences (user_id)
  values (new.id)
  on conflict (user_id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created after insert on auth.users for each row execute function public.handle_new_user();

alter table public.profiles enable row level security;
alter table public.fpl_team_links enable row level security;
alter table public.user_preferences enable row level security;
alter table public.saved_drafts enable row level security;
alter table public.weekly_recommendations enable row level security;
alter table public.decision_history enable row level security;
alter table public.favorite_players enable row level security;

drop policy if exists "profiles_owner_all" on public.profiles;
create policy "profiles_owner_all" on public.profiles for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "fpl_team_links_owner_all" on public.fpl_team_links;
create policy "fpl_team_links_owner_all" on public.fpl_team_links for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "user_preferences_owner_all" on public.user_preferences;
create policy "user_preferences_owner_all" on public.user_preferences for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "saved_drafts_owner_all" on public.saved_drafts;
create policy "saved_drafts_owner_all" on public.saved_drafts for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "weekly_recommendations_owner_all" on public.weekly_recommendations;
create policy "weekly_recommendations_owner_all" on public.weekly_recommendations for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "decision_history_owner_all" on public.decision_history;
create policy "decision_history_owner_all" on public.decision_history for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);
drop policy if exists "favorite_players_owner_all" on public.favorite_players;
create policy "favorite_players_owner_all" on public.favorite_players for all to authenticated using ((select auth.uid()) = user_id) with check ((select auth.uid()) = user_id);

revoke all on public.profiles, public.fpl_team_links, public.user_preferences, public.saved_drafts, public.weekly_recommendations, public.decision_history, public.favorite_players from anon;
grant select, insert, update, delete on public.profiles, public.fpl_team_links, public.user_preferences, public.saved_drafts, public.weekly_recommendations, public.decision_history, public.favorite_players to authenticated;
