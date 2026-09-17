#!/usr/bin/env bash
# Start the Marimo server in App Mode (read-only presentation app).
# Binds to 0.0.0.0:2718 so it can be reached from the host/proxy.
set -euo pipefail

. /opt/conda/etc/profile.d/conda.sh
conda activate base

NOTEBOOK_FILE="/home/jovyan/apps/aiidalab-feff/notebooks/debye_waller.py"
PID_FILE="/tmp/marimo-server.pid"
LOG_FILE="/tmp/marimo-server.log"

# Stop only the server we started. `pkill -f "marimo run"` would also kill any
# unrelated marimo the user is running in this container.
if [ -f "$PID_FILE" ]; then
    kill "$(cat "$PID_FILE")" 2>/dev/null || true
    rm -f "$PID_FILE"
    sleep 1
fi

if ! command -v marimo >/dev/null 2>&1; then
    echo "WARNING: marimo command not found; skipping notebook server" >&2
    exit 0
fi

if [ ! -f "$NOTEBOOK_FILE" ]; then
    echo "WARNING: $NOTEBOOK_FILE not found; skipping notebook server" >&2
    exit 0
fi

# Only widen CORS when the app is reached through a proxy that rewrites Origin.
# Set e.g. MARIMO_ALLOW_ORIGINS="https://example.org" — avoid "*", which lets any
# page drive the app. Skew protection is deliberately left enabled: a token
# mismatch means a browser tab predates the current server, and the fix is to
# reload the tab, not to disable the check.
EXTRA_ARGS=()
if [ -n "${MARIMO_ALLOW_ORIGINS:-}" ]; then
    EXTRA_ARGS+=(--allow-origins "$MARIMO_ALLOW_ORIGINS")
fi

nohup marimo run "$NOTEBOOK_FILE" \
    --host 0.0.0.0 \
    --port 2718 \
    --headless \
    --watch \
    "${EXTRA_ARGS[@]}" \
    > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "Started marimo app server for ${NOTEBOOK_FILE} on port 2718 (PID $(cat "$PID_FILE"))"
