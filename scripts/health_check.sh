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

: "${APP_STATUS_URL:=http://127.0.0.1:8000/api/status}"
: "${HEALTH_MAX_STALE_MINUTES:=180}"
: "${HEALTH_MIN_CARD_COUNT:=1}"
: "${HEALTH_ALERT_SLACK:=1}"
: "${SLACK_WEBHOOK_URL:=}"

STATUS_JSON="$(curl -fsS "${APP_STATUS_URL}" || true)"
if [ -z "${STATUS_JSON}" ]; then
  MSG="Health check failed: status endpoint unreachable (${APP_STATUS_URL}). Check app process and launchd logs."
  echo "${MSG}" >&2
  if [ "${HEALTH_ALERT_SLACK}" = "1" ] && [ -n "${SLACK_WEBHOOK_URL}" ]; then
    python3 - <<'PY'
import json
import os
import urllib.request

url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
target = os.getenv("APP_STATUS_URL", "http://127.0.0.1:8000/api/status")
msg = f"World AI Curation Health Alert: status endpoint unreachable ({target})."
if url:
    req = urllib.request.Request(
        url=url,
        data=json.dumps({"text": msg}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20):
        pass
PY
  fi
  exit 1
fi

export STATUS_JSON HEALTH_MAX_STALE_MINUTES HEALTH_MIN_CARD_COUNT

RESULT="$(python3 - <<'PY'
import json
import os
from datetime import datetime, timezone

status_json = os.environ["STATUS_JSON"]
max_stale = int(os.getenv("HEALTH_MAX_STALE_MINUTES", "180"))
min_cards = int(os.getenv("HEALTH_MIN_CARD_COUNT", "1"))

payload = json.loads(status_json)
generated_at = payload.get("generated_at")
card_count = int(payload.get("card_count", 0) or 0)
errors = payload.get("errors", [])
storage = (payload.get("storage") or {}).get("backend", "unknown")

ok = True
reasons = []

if not generated_at:
    ok = False
    reasons.append("generated_at is missing")
else:
    parsed = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    stale_minutes = (datetime.now(tz=timezone.utc) - parsed).total_seconds() / 60.0
    if stale_minutes > max_stale:
        ok = False
        reasons.append(f"data is stale ({stale_minutes:.1f}m > {max_stale}m)")

if card_count < min_cards:
    ok = False
    reasons.append(f"card_count is too low ({card_count} < {min_cards})")

summary = f"generated_at={generated_at or 'none'} | cards={card_count} | backend={storage} | errors={len(errors)}"
if ok:
    print("OK | " + summary)
else:
    print("NG | " + summary + " | reasons=" + "; ".join(reasons))
PY
)"

echo "${RESULT}"

if [[ "${RESULT}" == OK* ]]; then
  exit 0
fi

if [ "${HEALTH_ALERT_SLACK}" = "1" ] && [ -n "${SLACK_WEBHOOK_URL}" ]; then
  export HEALTH_ALERT_TEXT="${RESULT}"
  export APP_STATUS_URL
  python3 - <<'PY'
import json
import os
import urllib.request

url = os.getenv("SLACK_WEBHOOK_URL", "").strip()
target = os.getenv("APP_STATUS_URL", "http://127.0.0.1:8000/api/status")
msg = (
    "World AI Curation Health Alert: "
    + os.getenv("HEALTH_ALERT_TEXT", "unknown")
    + f" | check={target}"
)
if url:
    req = urllib.request.Request(
        url=url,
        data=json.dumps({"text": msg}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20):
        pass
PY
fi

exit 1
