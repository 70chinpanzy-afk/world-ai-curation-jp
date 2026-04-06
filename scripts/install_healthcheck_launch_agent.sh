#!/usr/bin/env bash
set -euo pipefail

LABEL="com.naoya.world-ai-curation.healthcheck"
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_PATH="${HOME}/Library/LaunchAgents/${LABEL}.plist"
LOG_OUT="/tmp/world-ai-curation-healthcheck.out.log"
LOG_ERR="/tmp/world-ai-curation-healthcheck.err.log"
UID_VALUE="$(id -u)"
DOMAIN="gui/${UID_VALUE}"

mkdir -p "${HOME}/Library/LaunchAgents"

cat > "${PLIST_PATH}" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${LABEL}</string>

  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${ROOT_DIR}/scripts/health_check.sh</string>
  </array>

  <key>WorkingDirectory</key>
  <string>${ROOT_DIR}</string>

  <key>RunAtLoad</key>
  <true/>

  <key>StartInterval</key>
  <integer>3600</integer>

  <key>StandardOutPath</key>
  <string>${LOG_OUT}</string>

  <key>StandardErrorPath</key>
  <string>${LOG_ERR}</string>

  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONUNBUFFERED</key>
    <string>1</string>
  </dict>
</dict>
</plist>
EOF

launchctl bootout "${DOMAIN}" "${PLIST_PATH}" >/dev/null 2>&1 || true
launchctl bootstrap "${DOMAIN}" "${PLIST_PATH}"
launchctl enable "${DOMAIN}/${LABEL}" >/dev/null 2>&1 || true
launchctl kickstart -k "${DOMAIN}/${LABEL}"

echo "Installed and started: ${LABEL}"
echo "Plist: ${PLIST_PATH}"
echo "Logs: ${LOG_OUT} / ${LOG_ERR}"

