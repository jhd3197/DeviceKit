#!/usr/bin/env bash
# DeviceKit - Start backend and frontend in dev mode

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

cleanup() {
    echo ""
    echo "Shutting down..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    wait $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit 0
}

trap cleanup INT TERM

echo "Starting DeviceKit dev servers..."
echo ""
echo "  Backend  : http://localhost:7317"
echo "  Frontend : http://localhost:7318"
echo ""

# Start backend
cd "$SCRIPT_DIR/backend"
python app.py &
BACKEND_PID=$!

# Give backend a moment to start
sleep 2

# Start frontend
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

echo "Press Ctrl+C to stop both servers."
wait
