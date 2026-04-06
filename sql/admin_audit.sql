-- Editorial state and admin audit tables

CREATE TABLE IF NOT EXISTS card_editorial_states (
  card_id TEXT PRIMARY KEY,
  status TEXT NOT NULL DEFAULT 'published',
  is_pinned BOOLEAN NOT NULL DEFAULT FALSE,
  pin_rank INTEGER NOT NULL DEFAULT 1000,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS admin_audit_logs (
  id TEXT PRIMARY KEY,
  timestamp TIMESTAMPTZ NOT NULL,
  actor TEXT NOT NULL,
  action TEXT NOT NULL,
  card_id TEXT NOT NULL,
  details_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_timestamp ON admin_audit_logs(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_admin_audit_logs_card_id ON admin_audit_logs(card_id);
