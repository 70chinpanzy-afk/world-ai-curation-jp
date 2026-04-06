-- Runtime snapshot table for Postgres persistence

CREATE TABLE IF NOT EXISTS curation_snapshots (
  id SMALLINT PRIMARY KEY CHECK (id = 1),
  generated_at TEXT,
  payload_json JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
