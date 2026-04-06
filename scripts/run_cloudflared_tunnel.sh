#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${CLOUDFLARED_TUNNEL_TOKEN:=}"
: "${CLOUDFLARED_BIN:=}"

if [ -z "${CLOUDFLARED_BIN}" ]; then
  CLOUDFLARED_BIN="$(command -v cloudflared || true)"
fi

if [ -z "${CLOUDFLARED_BIN}" ] || [ ! -x "${CLOUDFLARED_BIN}" ]; then
  echo "cloudflared command not found. Install: brew install cloudflared" >&2
  exit 1
fi

if [ -z "${CLOUDFLARED_TUNNEL_TOKEN}" ]; then
  echo "CLOUDFLARED_TUNNEL_TOKEN is not set in .env" >&2
  exit 1
fi

exec "${CLOUDFLARED_BIN}" tunnel --no-autoupdate run --token "${CLOUDFLARED_TUNNEL_TOKEN}"
