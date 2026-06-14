#!/usr/bin/env bash
set -euo pipefail

db_url="${SUPABASE_DB_URL:-${DATABASE_URL:-}}"
if [[ -z "$db_url" ]]; then
  echo "Set SUPABASE_DB_URL or DATABASE_URL to a Supabase Postgres connection string" >&2
  exit 1
fi

db_url="${db_url/postgresql+asyncpg:/postgresql:}"
db_url="${db_url/postgres+asyncpg:/postgres:}"
db_url="${db_url//ssl=require/sslmode=require}"

data_file="${1:-tmp/supabase_migration/post_writer_bot_data.sql}"
counts_file="$(dirname "$data_file")/supabase_counts.txt"
source_counts_file="$(dirname "$data_file")/source_counts.txt"

if [[ ! -f "$data_file" ]]; then
  echo "Data file not found: $data_file" >&2
  exit 1
fi

run_psql() {
  psql "$db_url" -v ON_ERROR_STOP=1 "$@"
}

run_psql -f app/db/migrations/0001_initial.sql
run_psql -f app/db/migrations/0004_project_menu_fields.sql
run_psql -c "
truncate table
  followup_events,
  subscriptions,
  payments,
  posts,
  ideas,
  audience_profiles,
  projects,
  users,
  tariffs
restart identity cascade;
"
run_psql -f "$data_file"
run_psql -f app/db/migrations/0002_seed_tariffs.sql
run_psql -f app/db/migrations/0003_enable_rls.sql

for table_name in \
  users \
  projects \
  audience_profiles \
  ideas \
  posts \
  tariffs \
  payments \
  subscriptions \
  followup_events
do
  run_psql -c "vacuum analyze $table_name;"
done

run_psql -Atc "
select table_name || '=' || row_count
from (
  select 'audience_profiles' as table_name, count(*) as row_count from audience_profiles
  union all select 'followup_events', count(*) from followup_events
  union all select 'ideas', count(*) from ideas
  union all select 'payments', count(*) from payments
  union all select 'posts', count(*) from posts
  union all select 'projects', count(*) from projects
  union all select 'subscriptions', count(*) from subscriptions
  union all select 'tariffs', count(*) from tariffs
  union all select 'users', count(*) from users
) counts
order by table_name;
" | tee "$counts_file"

if [[ -f "$source_counts_file" ]]; then
  diff -u "$source_counts_file" "$counts_file"
fi
