#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

JSON_PATH="${1:-config/affiliate_links.json}"
TARGET_ENV="${2:-production}"

if ! command -v vercel >/dev/null 2>&1; then
  echo "vercel CLI not found. Install with: brew install vercel-cli" >&2
  exit 1
fi

if [ ! -f "${JSON_PATH}" ]; then
  echo "affiliate config not found: ${JSON_PATH}" >&2
  exit 1
fi

PAYLOAD="$(python3 - <<'PY' "${JSON_PATH}"
import json, sys
path = sys.argv[1]
with open(path, "r", encoding="utf-8") as f:
    data = json.load(f)
print(json.dumps(data, ensure_ascii=False))
PY
)"

vercel env rm AFFILIATE_LINKS_JSON "${TARGET_ENV}" --yes >/dev/null 2>&1 || true
printf '%s\n' "${PAYLOAD}" | vercel env add AFFILIATE_LINKS_JSON "${TARGET_ENV}"

echo "AFFILIATE_LINKS_JSON updated for ${TARGET_ENV}."
