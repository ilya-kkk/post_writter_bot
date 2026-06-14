CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT NOT NULL UNIQUE,
    username VARCHAR(255),
    first_name VARCHAR(255),
    current_state VARCHAR(64) NOT NULL DEFAULT 'start',
    user_type VARCHAR(64),
    current_project_id INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

ALTER TABLE users ADD COLUMN IF NOT EXISTS current_project_id INTEGER;
CREATE INDEX IF NOT EXISTS ix_users_telegram_id ON users (telegram_id);
CREATE INDEX IF NOT EXISTS ix_users_current_project_id ON users (current_project_id);

CREATE TABLE IF NOT EXISTS projects (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    source_type VARCHAR(64) NOT NULL,
    source_value TEXT,
    raw_input TEXT NOT NULL,
    status VARCHAR(64) NOT NULL DEFAULT 'new',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_projects_user_id ON projects (user_id);

CREATE TABLE IF NOT EXISTS audience_profiles (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL UNIQUE REFERENCES projects(id) ON DELETE CASCADE,
    niche TEXT NOT NULL,
    audience_summary TEXT NOT NULL,
    pains_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    desires_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    beliefs_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    tone_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    raw_analysis_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_audience_profiles_project_id ON audience_profiles (project_id);

CREATE TABLE IF NOT EXISTS ideas (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    angle TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_ideas_project_id ON ideas (project_id);

CREATE TABLE IF NOT EXISTS posts (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    idea_id INTEGER REFERENCES ideas(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    generation_type VARCHAR(64) NOT NULL DEFAULT 'free',
    identity_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_posts_project_id ON posts (project_id);
CREATE INDEX IF NOT EXISTS ix_posts_idea_id ON posts (idea_id);

CREATE TABLE IF NOT EXISTS tariffs (
    id SERIAL PRIMARY KEY,
    code VARCHAR(64) NOT NULL UNIQUE,
    name VARCHAR(128) NOT NULL,
    projects_limit INTEGER NOT NULL,
    posts_limit INTEGER NOT NULL,
    monthly_price INTEGER NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true
);

CREATE TABLE IF NOT EXISTS payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE RESTRICT,
    amount INTEGER NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'RUB',
    status VARCHAR(64) NOT NULL DEFAULT 'pending',
    provider VARCHAR(64) NOT NULL DEFAULT 'mock',
    external_payment_id VARCHAR(255),
    payment_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    paid_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS ix_payments_user_id ON payments (user_id);
CREATE INDEX IF NOT EXISTS ix_payments_tariff_id ON payments (tariff_id);

CREATE TABLE IF NOT EXISTS subscriptions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tariff_id INTEGER NOT NULL REFERENCES tariffs(id) ON DELETE RESTRICT,
    status VARCHAR(64) NOT NULL DEFAULT 'active',
    projects_limit INTEGER NOT NULL,
    posts_limit INTEGER NOT NULL,
    posts_used INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_subscriptions_user_id ON subscriptions (user_id);
CREATE INDEX IF NOT EXISTS ix_subscriptions_tariff_id ON subscriptions (tariff_id);

CREATE TABLE IF NOT EXISTS followup_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    event_type VARCHAR(64) NOT NULL,
    scheduled_at TIMESTAMPTZ NOT NULL,
    sent_at TIMESTAMPTZ,
    status VARCHAR(64) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_followup_user_event_type UNIQUE (user_id, event_type)
);

CREATE INDEX IF NOT EXISTS ix_followup_events_user_id ON followup_events (user_id);
CREATE INDEX IF NOT EXISTS ix_followup_events_scheduled_at ON followup_events (scheduled_at);
