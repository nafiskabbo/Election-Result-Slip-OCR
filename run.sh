#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Starting Result desk"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
  ./venv/bin/pip install --upgrade pip
  ./venv/bin/pip install -r requirements.txt
fi

mkdir -p storage/raw storage/enhanced storage/thumbnails

if command -v npm >/dev/null 2>&1; then
  echo "Building the React desk..."
  (cd frontend && npm install && npm run build)
else
  echo "npm not found; serving API only. For the split setup, run: cd frontend && npm run dev"
fi

echo "Initializing database..."
./venv/bin/python -c "from backend.database import init_db; init_db()"

PORT="${PORT:-8000}"
echo "API: http://127.0.0.1:${PORT}"
echo "Desk: same origin after this build, or http://127.0.0.1:5173 via npm run dev"
exec ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
