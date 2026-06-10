#!/usr/bin/env bash
set -euo pipefail

out_dir="${1:-tmp/supabase_migration}"
mkdir -p "$out_dir"

docker compose exec -T db pg_dump \
  -U postgres \
  -d post_writer_bot \
  --schema=public \
  --data-only \
  --no-owner \
  --no-privileges \
  --file - > "$out_dir/post_writer_bot_data.sql"

docker compose exec -T db psql -U postgres -d post_writer_bot -Atc "
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
" > "$out_dir/source_counts.txt"

echo "Wrote $out_dir/post_writer_bot_data.sql"
echo "Wrote $out_dir/source_counts.txt"
