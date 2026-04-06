#!/usr/bin/env bash
set -euo pipefail

LABEL="com.naoya.world-ai-curation"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
UID_VALUE="$(id -u)"
DOMAIN="gui/${UID_VALUE}"

launchctl bootout "${DOMAIN}" "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl disable "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true

if [ -f "${PLIST_PATH}" ]; then
  rm -f "${PLIST_PATH}"
fi

echo "Uninstalled: ${LABEL}"

