#!/usr/bin/env bash
set -euo pipefail

LABEL="com.naoya.world-ai-curation.tunnel"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
UID_VALUE="$(id -u)"
DOMAIN="gui/${UID_VALUE}"

launchctl bootout "${DOMAIN}" "${PLIST_PATH}" >/dev/null 2>&1 || true
rm -f "${PLIST_PATH}"

echo "Uninstalled: ${LABEL}"
