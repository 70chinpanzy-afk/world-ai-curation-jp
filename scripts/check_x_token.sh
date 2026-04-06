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

: "${X_API_BASE_URL:=https://api.x.com}"
: "${X_TEST_QUERY:=AI OR LLM -is:retweet lang:en}"

if [ -z "${X_BEARER_TOKEN:-}" ]; then
  echo "X_BEARER_TOKEN is empty. Set token in .env first."
  exit 1
fi

export X_API_BASE_URL X_TEST_QUERY X_BEARER_TOKEN

python3 - <<'PY'
import json
import os
import urllib.parse
import urllib.request

base = os.getenv("X_API_BASE_URL", "https://api.x.com").rstrip("/")
query = os.getenv("X_TEST_QUERY", "AI OR LLM -is:retweet lang:en")
token = os.getenv("X_BEARER_TOKEN", "").strip()

url = (
    f"{base}/2/tweets/search/recent"
    f"?query={urllib.parse.quote(query)}"
    "&max_results=10"
    "&tweet.fields=created_at,lang"
)
req = urllib.request.Request(
    url=url,
    method="GET",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
)

with urllib.request.urlopen(req, timeout=20) as res:
    payload = json.loads(res.read().decode("utf-8"))

count = len(payload.get("data", []) or [])
meta = payload.get("meta", {}) or {}
print(f"X token check OK | tweets={count} | meta={meta}")
PY

