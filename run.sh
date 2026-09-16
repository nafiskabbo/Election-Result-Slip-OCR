#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

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

ensure_venv() {
  local PY
  PY="$(pick_python)"
  if ! venv_ok; then
    echo "Creating virtual environment with $PY..."
    rm -rf venv
    "$PY" -m venv venv
    venv/bin/python -m pip install --upgrade pip
    venv/bin/python -m pip install -r requirements.txt
  fi
  mkdir -p storage/raw storage/enhanced storage/thumbnails
}

ensure_postgres() {
  if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required to run PostgreSQL (docker compose up -d db)." >&2
    exit 1
  fi
  echo "Starting PostgreSQL..."
  docker compose up -d db
  local i
  for i in $(seq 1 40); do
    if docker compose exec -T db pg_isready -U ballot -d ballot >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  echo "PostgreSQL did not become ready." >&2
  exit 1
}

usage() {
  cat <<'EOF'
Usage: ./run.sh [command]

Commands:
  start       Start the API (default)
  test        Accuracy-check every photo in sample_slips/, then run pytest
  accuracy    Accuracy-check sample_slips/; writes storage/accuracy_report.md
  digit-export  Export RESULT cell crops for digit fine-tune
  digit-train   Train MNIST/EMNIST digit CNN (hard augment; no handwriting unless confirmed)
  help        Show this help

Examples:
  ./run.sh
  ./run.sh test
  ./run.sh accuracy
  ./run.sh accuracy --raw-ocr
  ./run.sh accuracy --raw-ocr --rapidocr-model both
  ./run.sh accuracy --raw-ocr --compare-vote-path
  ./run.sh accuracy --raw-ocr --compare-digit-cnn
  ./run.sh accuracy --fail-under 95
  ./run.sh accuracy --out /tmp/accuracy_report.md
  ./run.sh digit-export
  ./run.sh digit-train --epochs 5
  # After you confirm handwriting fine-tune:
  ./run.sh digit-train --include-handwriting --i-confirm-handwriting
EOF
}

run_accuracy() {
  echo "Checking OCR accuracy on sample_slips/..."
  venv/bin/python -m backend.accuracy_check "$@"
}

run_tests() {
  run_accuracy
  echo
  echo "Running pytest..."
  venv/bin/python -m pytest tests/ -v
}

start_server() {
  if command -v npm >/dev/null 2>&1; then
    echo "Building the React desk..."
    (cd frontend && npm install && npm run build)
  else
    echo "npm not found; serving API only. For the split setup, run: cd frontend && npm run dev"
  fi

  echo "Initializing database..."
  venv/bin/python -c "from backend.database import init_db; init_db()"

  PORT="${PORT:-8000}"
  echo "API: http://127.0.0.1:${PORT}"
  echo "Desk: same origin after this build, or http://127.0.0.1:5173 via npm run dev"
  exec venv/bin/python -m uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" --reload
}

cmd="${1:-start}"
if [[ $# -gt 0 ]]; then
  shift
fi

case "$cmd" in
  start)
    echo "Starting Result desk"
    ensure_venv
    ensure_postgres
    start_server
    ;;
  test)
    ensure_venv
    ensure_postgres
    run_tests "$@"
    ;;
  accuracy)
    ensure_venv
    run_accuracy "$@"
    ;;
  digit-export)
    ensure_venv
    echo "Exporting RESULT digit cells..."
    venv/bin/python -m backend.digit_finetune.export_result_cells "$@"
    ;;
  digit-train)
    ensure_venv
    if ! venv/bin/python -c "import torch, torchvision" >/dev/null 2>&1; then
      echo "Installing training deps..."
      venv/bin/python -m pip install -r requirements-train.txt
    fi
    echo "Training digit CNN (MNIST/EMNIST + hard augment)..."
    venv/bin/python -m backend.digit_finetune.train_digit_cnn "$@"
    ;;
  help|-h|--help)
    usage
    ;;
  *)
    echo "Unknown command: $cmd" >&2
    usage >&2
    exit 1
    ;;
esac
