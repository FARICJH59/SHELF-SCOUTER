#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

# SHELF-SCOUTER phone-first picker bootstrap.
# 2026-09-09 development milestone.
# Run this from Termux on the Android phone.

ROOT="$(cd "$(dirname "$0")" && pwd)"
export FLASK_HOST="${FLASK_HOST:-0.0.0.0}"
export FLASK_PORT="${FLASK_PORT:-5000}"

if [[ -z "${GOOGLE_API_KEY:-}" ]]; then
  echo "ERROR: set GOOGLE_API_KEY before starting the backend."
  echo "export GOOGLE_API_KEY='YOUR_KEY'"
  exit 1
fi

cd "$ROOT"
python run_mobile_gateway.py &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT

sleep 2
curl -fsS "http://127.0.0.1:${FLASK_PORT}/v1/health" || true
echo
echo "SHELF-SCOUTER backend running on http://127.0.0.1:${FLASK_PORT}"
echo "Open a second Termux session and run:"
echo "  cd $ROOT/mobile"
echo "  npm install"
echo "  EXPO_PUBLIC_BACKEND_URL=http://127.0.0.1:${FLASK_PORT} npx expo start"
wait "$BACKEND_PID"
