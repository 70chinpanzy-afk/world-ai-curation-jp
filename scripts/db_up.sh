#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"
docker compose up -d postgres

echo "Postgres is starting on 127.0.0.1:5432"
echo "DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/world_ai_curation"
