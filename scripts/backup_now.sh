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

: "${BACKUP_DIR:=${ROOT_DIR}/backups}"
: "${BACKUP_RETENTION_DAYS:=14}"
: "${BACKUP_INCLUDE_DATA_DIR:=1}"
: "${BACKUP_INCLUDE_PG:=1}"
: "${DATABASE_URL:=}"
: "${BACKUP_PG_DOCKER_CONTAINER:=world-ai-curation-postgres}"
: "${BACKUP_PG_DB_USER:=postgres}"
: "${BACKUP_PG_DB_NAME:=}"

PG_DUMP_BIN="$(command -v pg_dump 2>/dev/null || true)"
if [ -z "${PG_DUMP_BIN}" ]; then
  for candidate in /opt/homebrew/bin/pg_dump /usr/local/bin/pg_dump /usr/bin/pg_dump; do
    if [ -x "${candidate}" ]; then
      PG_DUMP_BIN="${candidate}"
      break
    fi
  done
fi

DOCKER_BIN="$(command -v docker 2>/dev/null || true)"
if [ -z "${DOCKER_BIN}" ]; then
  for candidate in /opt/homebrew/bin/docker /usr/local/bin/docker /Applications/Docker.app/Contents/Resources/bin/docker; do
    if [ -x "${candidate}" ]; then
      DOCKER_BIN="${candidate}"
      break
    fi
  done
fi

STAMP="$(date -u +%Y%m%d_%H%M%SZ)"
RUN_DIR="${BACKUP_DIR}/${STAMP}"

mkdir -p "${RUN_DIR}"

DATA_STATUS="skipped"
PG_STATUS="skipped"

if [ "${BACKUP_INCLUDE_DATA_DIR}" = "1" ]; then
  if [ -d "${ROOT_DIR}/data" ]; then
    tar -C "${ROOT_DIR}" -czf "${RUN_DIR}/data_backup_${STAMP}.tar.gz" data
    DATA_STATUS="ok"
  else
    DATA_STATUS="missing_data_dir"
  fi
fi

if [ "${BACKUP_INCLUDE_PG}" = "1" ]; then
  if [ -n "${DATABASE_URL}" ] && [ -n "${PG_DUMP_BIN}" ]; then
    if "${PG_DUMP_BIN}" --dbname="${DATABASE_URL}" --format=custom --no-owner --no-privileges --file="${RUN_DIR}/postgres_${STAMP}.dump"; then
      PG_STATUS="ok"
    else
      PG_STATUS="pg_dump_failed"
    fi
  elif [ -n "${DOCKER_BIN}" ] && "${DOCKER_BIN}" ps --format '{{.Names}}' | grep -q "^${BACKUP_PG_DOCKER_CONTAINER}$"; then
    DB_NAME="${BACKUP_PG_DB_NAME}"
    if [ -z "${DB_NAME}" ] && [ -n "${DATABASE_URL}" ]; then
      DB_NAME="${DATABASE_URL##*/}"
      DB_NAME="${DB_NAME%%\?*}"
    fi
    : "${DB_NAME:=world_ai_curation}"

    if "${DOCKER_BIN}" exec "${BACKUP_PG_DOCKER_CONTAINER}" pg_dump -U "${BACKUP_PG_DB_USER}" -d "${DB_NAME}" -Fc > "${RUN_DIR}/postgres_${STAMP}.dump"; then
      PG_STATUS="ok"
    else
      PG_STATUS="pg_dump_failed_in_docker"
    fi
  else
    PG_STATUS="pg_dump_unavailable_or_no_database_url"
  fi
fi

export RUN_DIR DATA_STATUS PG_STATUS

python3 - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path

run_dir = Path(os.environ["RUN_DIR"])
manifest = {
    "generated_at": datetime.now(tz=timezone.utc).isoformat(),
    "backup_dir": str(run_dir),
    "data_status": os.environ["DATA_STATUS"],
    "pg_status": os.environ["PG_STATUS"],
}
(run_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
PY

if [ -d "${BACKUP_DIR}" ]; then
  find "${BACKUP_DIR}" -mindepth 1 -maxdepth 1 -type d -mtime +"${BACKUP_RETENTION_DAYS}" -exec rm -rf {} +
fi

echo "Backup finished: ${RUN_DIR} | data=${DATA_STATUS} | pg=${PG_STATUS}"

if [ "${DATA_STATUS}" != "ok" ] && [ "${PG_STATUS}" != "ok" ]; then
  exit 1
fi
