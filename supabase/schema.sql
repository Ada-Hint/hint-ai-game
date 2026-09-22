-- Run once in your Supabase project's SQL editor. Safe to run again.
-- Only the Streamlit server's service_role key can access the data or functions.
begin;

create table if not exists public.hint_events (
  id text primary key,
  revision bigint not null default 0,
  document jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.hint_events enable row level security;
revoke all on public.hint_events from anon, authenticated;
grant select, insert, update on public.hint_events to service_role;

create or replace function public.hint_initialize(p_id text, p_document jsonb)
returns boolean language plpgsql security invoker set search_path = '' as $$
begin
  insert into public.hint_events (id, document) values (p_id, p_document)
  on conflict (id) do nothing;
  return true;
end;
$$;

create or replace function public.hint_read(p_id text)
returns jsonb language sql stable security invoker set search_path = '' as $$
  select jsonb_build_object('revision', revision, 'document', document)
  from public.hint_events where id = p_id;
$$;

create or replace function public.hint_compare_swap(p_id text, p_revision bigint, p_document jsonb)
returns boolean language plpgsql security invoker set search_path = '' as $$
declare affected integer;
begin
  update public.hint_events
  set document = p_document, revision = revision + 1, updated_at = now()
  where id = p_id and revision = p_revision;
  get diagnostics affected = row_count;
  return affected = 1;
end;
$$;

revoke all on function public.hint_initialize(text, jsonb) from public, anon, authenticated;
revoke all on function public.hint_read(text) from public, anon, authenticated;
revoke all on function public.hint_compare_swap(text, bigint, jsonb) from public, anon, authenticated;
grant execute on function public.hint_initialize(text, jsonb) to service_role;
grant execute on function public.hint_read(text) to service_role;
grant execute on function public.hint_compare_swap(text, bigint, jsonb) to service_role;
commit;

