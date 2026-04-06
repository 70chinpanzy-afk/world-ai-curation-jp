#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ -f ".env" ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${PUBLIC_BASE_URL:=http://127.0.0.1:8000}"
: "${AFFILIATE_LINKS_PATH:=${ROOT_DIR}/config/affiliate_links.json}"
: "${CLOUDFLARED_TUNNEL_TOKEN:=}"
: "${PUBLIC_SMOKE_TIMEOUT_SECONDS:=5}"
: "${PUBLIC_SMOKE_BOOT_RETRIES:=10}"
: "${PUBLIC_SMOKE_BOOT_SLEEP_SECONDS:=2}"

echo "[check] public_base_url=${PUBLIC_BASE_URL}"
if [[ "${PUBLIC_BASE_URL}" == "http://127.0.0.1:8000" ]]; then
  echo "[warn] PUBLIC_BASE_URL is still local. Set your production domain before release."
else
  echo "[ok] PUBLIC_BASE_URL looks set for public use."
fi

if [ ! -f "${AFFILIATE_LINKS_PATH}" ]; then
  echo "[warn] affiliate config not found: ${AFFILIATE_LINKS_PATH}"
else
  echo "[ok] affiliate config exists: ${AFFILIATE_LINKS_PATH}"
  python3 - <<'PY' "${AFFILIATE_LINKS_PATH}"
import json, sys
path = sys.argv[1]
try:
    data = json.loads(open(path, "r", encoding="utf-8").read())
except Exception as exc:
    print(f"[warn] affiliate config parse failed: {exc}")
    raise SystemExit(0)

links = data.get("links", [])
if not isinstance(links, list):
    print("[warn] affiliate config links is not a list.")
    raise SystemExit(0)

active = [x for x in links if isinstance(x, dict) and x.get("is_active", True)]
print(f"[check] affiliate_links_total={len(links)} active={len(active)}")
if len(active) == 0:
    print("[warn] no active affiliate links. set is_active=true to display.")
else:
    print("[ok] affiliate links are configured.")
PY
fi

if [ -z "${CLOUDFLARED_TUNNEL_TOKEN}" ]; then
  echo "[warn] CLOUDFLARED_TUNNEL_TOKEN is empty. tunnel auto-run cannot start yet."
else
  echo "[ok] CLOUDFLARED_TUNNEL_TOKEN is set."
fi

echo "[hint] public seo urls (after app is reachable):"
echo "       ${PUBLIC_BASE_URL}/robots.txt"
echo "       ${PUBLIC_BASE_URL}/sitemap.xml"
echo "       ${PUBLIC_BASE_URL}/feed.xml"
echo "       ${PUBLIC_BASE_URL}/privacy"
echo "       ${PUBLIC_BASE_URL}/terms"
echo "       ${PUBLIC_BASE_URL}/affiliate-disclosure"
echo

echo "[check] wait for app reachability before smoke test"
ready=0
for attempt in $(seq 1 "${PUBLIC_SMOKE_BOOT_RETRIES}"); do
  code="$(curl -sS -L -m "${PUBLIC_SMOKE_TIMEOUT_SECONDS}" -o /dev/null -w "%{http_code}" "${PUBLIC_BASE_URL}/" || true)"
  if [ "${code}" = "200" ]; then
    ready=1
    echo "[ok] app reachable (${attempt}/${PUBLIC_SMOKE_BOOT_RETRIES})"
    break
  fi
  if [ "${attempt}" -lt "${PUBLIC_SMOKE_BOOT_RETRIES}" ]; then
    sleep "${PUBLIC_SMOKE_BOOT_SLEEP_SECONDS}"
  fi
done
if [ "${ready}" -ne 1 ]; then
  echo "[warn] app did not become reachable within wait window."
fi
echo

echo "[check] public endpoint smoke test (timeout=${PUBLIC_SMOKE_TIMEOUT_SECONDS}s)"
for path in / /robots.txt /sitemap.xml /feed.xml /rss.xml /privacy /terms /affiliate-disclosure; do
  url="${PUBLIC_BASE_URL}${path}"
  code="$(curl -sS -L -m "${PUBLIC_SMOKE_TIMEOUT_SECONDS}" -o /dev/null -w "%{http_code}" "${url}" || true)"
  if [ "${code}" = "200" ]; then
    echo "[ok] ${path} -> 200"
  elif [ -z "${code}" ] || [ "${code}" = "000" ]; then
    echo "[warn] ${path} -> unreachable (check app/tunnel/domain)"
  else
    echo "[warn] ${path} -> status=${code}"
  fi
done
echo

echo "[done] public readiness check completed."
