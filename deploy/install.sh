#!/usr/bin/env bash
# Idempotent one-time setup for the Laeser launchd service.
set -euo pipefail

LABEL="org.laeser.app"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE="${PROJECT_DIR}/deploy/org.laeser.app.plist.template"
PLIST_DIR="${HOME}/Library/LaunchAgents"
PLIST="${PLIST_DIR}/${LABEL}.plist"
LOG_DIR="${HOME}/Library/Logs/laeser"
TARGET="gui/$(id -u)/${LABEL}"

# 1. Locate uv.
UV_PATH="$(command -v uv || true)"
if [[ -z "$UV_PATH" ]]; then
	echo "Error: 'uv' not found on PATH. Install uv first." >&2
	exit 1
fi
SERVICE_PATH="$(dirname "$UV_PATH"):/usr/bin:/bin:/usr/sbin:/sbin"

# 2. Advise on the /etc/hosts entry (never edited here — needs sudo).
if ! grep -q 'app\.laeser\.org' /etc/hosts; then
	echo "NOTE: app.laeser.org is not in /etc/hosts. Add it with:"
	echo "    echo '127.0.0.1 app.laeser.org' | sudo tee -a /etc/hosts"
	echo
fi

# 3. Create the log directory.
mkdir -p "$LOG_DIR"

# 4. Render the plist template into ~/Library/LaunchAgents.
mkdir -p "$PLIST_DIR"
sed -e "s|__UV_PATH__|${UV_PATH}|g" \
    -e "s|__PROJECT_DIR__|${PROJECT_DIR}|g" \
    -e "s|__LOG_DIR__|${LOG_DIR}|g" \
    -e "s|__SERVICE_PATH__|${SERVICE_PATH}|g" \
    "$TEMPLATE" > "$PLIST"
echo "Wrote ${PLIST}"

# 5. (Re-)bootstrap the LaunchAgent so launchd picks up the current plist.
launchctl bootout "$TARGET" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Bootstrapped ${LABEL} (loaded, not started)"

echo
echo "Setup complete. Start the service with:"
echo "    deploy/laeserctl start"
