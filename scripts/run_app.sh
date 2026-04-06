#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

if [ -f ".env" ]; then
  set -a
  source .env
  set +a
fi

: "${DATABASE_URL:=postgresql://postgres:postgres@127.0.0.1:5432/world_ai_curation}"

export DATABASE_URL

exec python3 -m uvicorn src.app:app --reload
