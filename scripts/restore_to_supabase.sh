#!/usr/bin/env bash
set -euo pipefail

: "${SUPABASE_DB_URL:?Set SUPABASE_DB_URL to a psql-compatible Supabase Postgres URL}"

data_file="${1:-tmp/supabase_migration/post_writer_bot_data.sql}"

if [[ ! -f "$data_file" ]]; then
  echo "Data file not found: $data_file" >&2
  exit 1
fi

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f app/db/migrations/0001_initial.sql
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f "$data_file"
psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -f app/db/migrations/0003_enable_rls.sql

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
  psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -c "vacuum analyze $table_name;"
done

psql "$SUPABASE_DB_URL" -v ON_ERROR_STOP=1 -Atc "
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
"
