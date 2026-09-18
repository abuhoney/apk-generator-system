#!/usr/bin/env bash
# start.sh — Launch the BardomPro APK Generator backend.
set -euo pipefail
cd "$(dirname "$0")"

# Load .env into environment (if present)
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

# Ensure Python deps are installed
if ! python3 -c "import flask" 2>/dev/null; then
  echo "Installing Python dependencies..."
  pip install -r requirements.txt
fi

# Default port
export PORT="${PORT:-3000}"
export NODE_ENV="${NODE_ENV:-production}"

echo "Starting BardomPro APK Generator on port $PORT ..."
exec python3 -m gunicorn --chdir backend app:app \
  --bind "0.0.0.0:$PORT" \
  --workers "${WORKERS:-2}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
