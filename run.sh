#!/usr/bin/env bash
set -e

echo "=========================================================="
echo " Starting Election Result Slip OCR & Data Capture Platform "
echo "=========================================================="

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    ./venv/bin/pip install --upgrade pip
    ./venv/bin/pip install -r requirements.txt
fi

# Ensure storage directories exist
mkdir -p storage/raw storage/enhanced storage/thumbnails

echo "Initializing database..."
./venv/bin/python -c "from backend.database import init_db; init_db()"

echo ""
echo "Server listening at: http://127.0.0.1:8000"
echo "Interactive API docs: http://127.0.0.1:8000/docs"
echo "Web Interface: http://127.0.0.1:8000"
echo ""

./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
