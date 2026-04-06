-- PostgreSQL schema for world AI curation platform

CREATE TABLE IF NOT EXISTS sources (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL,
  kind TEXT NOT NULL, -- rss, api, website, social
  tier TEXT NOT NULL, -- A, B, C
  base_url TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS source_items (
  id BIGSERIAL PRIMARY KEY,
  source_id BIGINT NOT NULL REFERENCES sources(id),
  source_native_id TEXT,
  url TEXT NOT NULL,
  title TEXT NOT NULL,
  author TEXT,
  language TEXT,
  published_at TIMESTAMPTZ,
  content_text TEXT,
  content_hash TEXT NOT NULL,
  raw_payload_json JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (source_id, source_native_id),
  UNIQUE (content_hash)
);

CREATE TABLE IF NOT EXISTS story_clusters (
  id BIGSERIAL PRIMARY KEY,
  canonical_item_id BIGINT REFERENCES source_items(id),
  topic TEXT,
  confidence NUMERIC(4,3) NOT NULL DEFAULT 0.500,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS cluster_items (
  cluster_id BIGINT NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  source_item_id BIGINT NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (cluster_id, source_item_id)
);

CREATE TABLE IF NOT EXISTS curation_cards (
  id BIGSERIAL PRIMARY KEY,
  cluster_id BIGINT NOT NULL REFERENCES story_clusters(id) ON DELETE CASCADE,
  headline TEXT NOT NULL,
  score_total NUMERIC(5,2) NOT NULL DEFAULT 0,
  score_trust NUMERIC(4,3) NOT NULL DEFAULT 0,
  score_novelty NUMERIC(4,3) NOT NULL DEFAULT 0,
  score_impact NUMERIC(4,3) NOT NULL DEFAULT 0,
  score_actionability NUMERIC(4,3) NOT NULL DEFAULT 0,
  status TEXT NOT NULL DEFAULT 'draft', -- draft, published, archived
  published_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS card_variants (
  id BIGSERIAL PRIMARY KEY,
  card_id BIGINT NOT NULL REFERENCES curation_cards(id) ON DELETE CASCADE,
  audience TEXT NOT NULL, -- raw, vibe, builder
  language TEXT NOT NULL DEFAULT 'ja',
  summary TEXT NOT NULL,
  why_it_matters TEXT,
  action_steps TEXT,
  risks TEXT,
  model_name TEXT,
  model_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (card_id, audience, language)
);

CREATE TABLE IF NOT EXISTS card_sources (
  id BIGSERIAL PRIMARY KEY,
  card_id BIGINT NOT NULL REFERENCES curation_cards(id) ON DELETE CASCADE,
  source_item_id BIGINT NOT NULL REFERENCES source_items(id) ON DELETE CASCADE,
  citation_label TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (card_id, source_item_id)
);

CREATE INDEX IF NOT EXISTS idx_source_items_published_at ON source_items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_curation_cards_score_total ON curation_cards(score_total DESC);
CREATE INDEX IF NOT EXISTS idx_card_variants_audience ON card_variants(audience);
