-- Enable UUID functions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    department TEXT NOT NULL,
    experience_years INTEGER NOT NULL,
    active_task_count INTEGER NOT NULL,
    location TEXT,
    uid UUID NOT NULL DEFAULT uuid_generate_v4(),
    email TEXT,
    role TEXT NOT NULL DEFAULT 'USER',
    password_hash TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_department ON users (department);
CREATE INDEX IF NOT EXISTS idx_users_experience ON users (experience_years);
CREATE INDEX IF NOT EXISTS idx_users_active_count ON users (active_task_count);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    uid UUID NOT NULL DEFAULT uuid_generate_v4(),
    status TEXT NOT NULL DEFAULT 'TODO' CHECK (status IN ('TODO','IN_PROGRESS','DONE','WAITING_FOR_ELIGIBLE_USER')),
    priority INTEGER NOT NULL DEFAULT 0,
    due_date DATE
);

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS description TEXT;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'tasks_status_check') THEN
        ALTER TABLE tasks
            ADD CONSTRAINT tasks_status_check CHECK (status IN ('TODO','IN_PROGRESS','DONE','WAITING_FOR_ELIGIBLE_USER'));
    END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_tasks_rules_gin ON tasks USING GIN (rules);

CREATE TABLE IF NOT EXISTS assignments (
    id SERIAL PRIMARY KEY,
    task_id INTEGER NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'ASSIGNED',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    task_uid UUID,
    user_uid UUID
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_task_unique ON assignments (task_id);
CREATE INDEX IF NOT EXISTS idx_assignments_user ON assignments (user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assignments_task_uid_unique ON assignments (task_uid);
CREATE INDEX IF NOT EXISTS idx_assignments_user_uid ON assignments (user_uid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_uid_unique ON users (uid);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tasks_uid_unique ON tasks (uid);

-- Suggested schema alignment (integer-based, non-breaking)
CREATE TABLE IF NOT EXISTS user_task_counters (
    user_id INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    active_task_count INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_user_active_tasks ON user_task_counters (active_task_count);

CREATE TABLE IF NOT EXISTS task_eligible_users (
    task_id INTEGER REFERENCES tasks(id) ON DELETE CASCADE,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    score INTEGER NOT NULL,
    computed_at TIMESTAMP NOT NULL DEFAULT NOW(),
    PRIMARY KEY (task_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_eligible_users_task ON task_eligible_users (task_id);
CREATE INDEX IF NOT EXISTS idx_eligible_users_user ON task_eligible_users (user_id);

CREATE TABLE IF NOT EXISTS audit_logs (
    id BIGSERIAL PRIMARY KEY,
    entity_type TEXT,
    entity_id INTEGER,
    action TEXT,
    metadata JSONB,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS access_logs (
    id BIGSERIAL PRIMARY KEY,
    service TEXT NOT NULL,
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status INTEGER,
    time_ms INTEGER,
    req_headers JSONB,
    req_body TEXT,
    resp_headers JSONB,
    resp_body TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_access_logs_service ON access_logs (service, created_at);
CREATE INDEX IF NOT EXISTS idx_access_logs_path ON access_logs (path);

-- Seed Data (idempotent)
INSERT INTO users (id, name, department, experience_years, active_task_count, location) VALUES
  (1, 'Alice', 'Finance', 5, 1, 'Delhi'),
  (2, 'Bob', 'Finance', 3, 0, 'Mumbai'),
  (3, 'Carol', 'HR', 7, 2, 'Bangalore'),
  (4, 'Dave', 'Engineering', 10, 4, 'Delhi'),
  (5, 'Eve', 'Engineering', 2, 0, 'Pune')
ON CONFLICT (id) DO NOTHING;

INSERT INTO tasks (id, title, rules) VALUES
  (100, 'Finance Audit', '{"department":"Finance","min_experience":4,"max_active_tasks":5}'),
  (101, 'HR Onboarding', '{"department":"HR","min_experience":5}'),
  (102, 'Bug Triage', '{"department":"Engineering","max_active_tasks":3}')
ON CONFLICT (id) DO NOTHING;
