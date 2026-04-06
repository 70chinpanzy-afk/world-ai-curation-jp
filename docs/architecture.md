# Architecture (Production-Oriented)

## 1. System Components
- Ingestion Workers
  - Pull from RSS, official APIs, and selected websites
  - Store raw payloads for traceability
- Normalization Layer
  - Convert each input into `source_items`
  - Standardize language, timestamp, author, URL, and content hash
- Intelligence Processing Layer
  - deduplicate cluster creation
  - scoring (trust, novelty, impact, actionability)
  - classification (topic, company, model, category)
  - LLM summarization + Japanese translation
- Curation Layer
  - Generate one master curation card per cluster
  - Generate audience variants (`raw`, `vibe`, `builder`)
- Delivery Layer
  - Read API for web/mobile
  - Admin API for editorial overrides

## 2. Data Flow
1. Source connector writes raw event
2. Normalizer builds canonical source item
3. Similarity service groups items into clusters
4. Ranking service computes editorial score
5. Enrichment service produces variants
6. API serves ranked cards by audience and topic

## 3. Reliability and Operations
- Queue-based jobs for ingestion and enrichment
- Idempotent writes using `source_id + source_native_id`
- Retry with dead-letter queue for failed jobs
- Observability:
  - connector success rate
  - enrichment latency
  - duplicate ratio
  - publication freshness

## 4. Suggested Stack
- App/API: Python (FastAPI) or TypeScript (NestJS)
- Jobs: Celery/RQ (Python) or BullMQ (Node)
- DB: PostgreSQL
- Cache/Queue: Redis
- Search: OpenSearch or Postgres full-text first
- Object storage: S3-compatible bucket for raw payloads

## 5. Security and Governance
- Keep source URLs and timestamps for every generated card
- Mark machine-generated text clearly
- Include source-license checks in connector policy
- Separate staging and production prompts/models
