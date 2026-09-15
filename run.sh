#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "Starting Result desk"

pick_python() {
  local cmd ver
  for cmd in python3.12 python3.11 python3.13 python3; do
    if command -v "$cmd" >/dev/null 2>&1; then
      ver="$("$cmd" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
      case "$ver" in
        3.11|3.12|3.13)
          echo "$cmd"
          return 0
          ;;
      esac
    fi
  done
  echo "Need Python 3.11–3.13. Homebrew python3 is 3.14 here and OCR wheels do not install on it." >&2
  exit 1
}

venv_ok() {
  [[ -x venv/bin/python ]] || return 1
  venv/bin/python - <<'PY' >/dev/null 2>&1
import sys
raise SystemExit(0 if sys.version_info[:2] in {(3, 11), (3, 12), (3, 13)} else 1)
PY
  venv/bin/python -c "import fastapi, uvicorn, cv2" >/dev/null 2>&1
}

PY="$(pick_python)"
if ! venv_ok; then
  echo "Creating virtual environment with $PY..."
  rm -rf venv
  "$PY" -m venv venv
  venv/bin/python -m pip install --upgrade pip
  venv/bin/python -m pip install -r requirements.txt
fi

mkdir -p storage/raw storage/enhanced storage/thumbnails

if command -v npm >/dev/null 2>&1; then
  if [[ "${FORCE_FRONTEND_BUILD:-}" == "1" || ! -f frontend/dist/index.html ]]; then
    echo "Building the React desk..."
    (cd frontend && npm install && npm run build)
  else
    echo "Using existing frontend/dist (set FORCE_FRONTEND_BUILD=1 to rebuild)."
  fi
else
  echo "npm not found; serving API only. For the split setup, run: cd frontend && npm run dev"
fi

echo "Initializing database..."
venv/bin/python -c "from backend.database import init_db; init_db()"

PORT="${PORT:-8000}"
echo "API: http://127.0.0.1:${PORT}"
echo "Desk: same origin after this build, or http://127.0.0.1:5173 via npm run dev"
exec venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
