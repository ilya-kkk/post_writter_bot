ALTER TABLE users ADD COLUMN IF NOT EXISTS current_project_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_users_current_project_id ON users (current_project_id);

ALTER TABLE posts ADD COLUMN IF NOT EXISTS identity_json JSONB NOT NULL DEFAULT '{}'::jsonb;
