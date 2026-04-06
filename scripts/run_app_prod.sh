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
: "${APP_HOST:=127.0.0.1}"
: "${APP_PORT:=8000}"
: "${APP_PYTHON:=}"

if [ -z "${APP_PYTHON}" ]; then
  CANDIDATES=(
    "$(command -v python3 2>/dev/null || true)"
    "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    "/opt/homebrew/bin/python3"
    "/usr/local/bin/python3"
    "/usr/bin/python3"
  )

  for candidate in "${CANDIDATES[@]}"; do
    [ -n "${candidate}" ] || continue
    [ -x "${candidate}" ] || continue
    if "${candidate}" -c "import uvicorn" >/dev/null 2>&1; then
      APP_PYTHON="${candidate}"
      break
    fi
  done
fi

if [ -z "${APP_PYTHON}" ]; then
  echo "No Python with uvicorn was found. Set APP_PYTHON in .env." >&2
  exit 1
fi

export DATABASE_URL APP_HOST APP_PORT APP_PYTHON

exec "${APP_PYTHON}" -m uvicorn src.app:app --host "${APP_HOST}" --port "${APP_PORT}"
