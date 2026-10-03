#!/bin/bash
# ==============================================================================
# AWS Classroom Proctor — Command Center Launcher
# Starts local FastAPI mission control console connected to Supabase PostgreSQL
# ==============================================================================

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
cd "$DIR"

PORT="${COMMAND_CENTER_PORT:-8090}"

echo "======================================================================"
echo "🛰️  AWS STUDENT BUILDER GROUP — PROCTOR COMMAND CENTER"
echo "📡  Connecting to Supabase PostgreSQL Database..."
echo "👉  Dashboard URL: http://localhost:$PORT"
echo "======================================================================"

# Determine Python binary
if [ -f ".venv/bin/python3" ]; then
    PYTHON_BIN=".venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    echo "❌ Error: Python 3 not found."
    exit 1
fi

# Ensure requirements are installed
$PYTHON_BIN -c "import fastapi, uvicorn, asyncpg, httpx" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "📦 Installing required dependencies (fastapi, uvicorn, asyncpg, httpx)..."
    $PYTHON_BIN -m pip install fastapi uvicorn asyncpg httpx pydantic
fi

# Automatically open browser on macOS
if command -v open >/dev/null 2>&1; then
    (sleep 1.5 && open "http://localhost:$PORT") &
fi

exec $PYTHON_BIN command_center.py
