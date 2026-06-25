#!/bin/bash

# Terminate all spawned background processes when this script exits or is killed
trap "trap - SIGTERM && kill -- -$$" SIGINT SIGTERM EXIT

echo "==============================================="
echo "  AICryptoSMC - Smart Money Concepts Bot  "
echo "==============================================="

# Navigate to the workspace root
cd "$(dirname "$0")"

# Start the Backend FastAPI Server
echo "🚀 Launching Python Backend on http://localhost:8005..."
PYTHONPATH=. venv/bin/python backend/main.py &

# Wait briefly for backend startup
sleep 2

# Start the Frontend Vite Server
echo "🎨 Launching Frontend Dashboard..."
cd frontend && npm run dev
