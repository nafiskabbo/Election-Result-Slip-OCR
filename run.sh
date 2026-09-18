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

load_env() {
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
}

db_ready() {
  local url="${DATABASE_URL:-}"
  [[ -n "$url" ]] || return 1
  if [[ -x venv/bin/python ]]; then
    DATABASE_URL="$url" venv/bin/python - <<'PY' >/dev/null 2>&1
import os, sys
try:
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=2) as conn:
        conn.execute("SELECT 1")
except Exception:
    raise SystemExit(1)
PY
    return $?
  fi
  command -v psql >/dev/null 2>&1 || return 1
  psql "$url" -c "SELECT 1" >/dev/null 2>&1
}

ensure_homebrew_postgres() {
  command -v brew >/dev/null 2>&1 || return 1
  command -v psql >/dev/null 2>&1 || return 1
  echo "Starting Homebrew PostgreSQL..."
  brew services start postgresql@16 >/dev/null 2>&1 || brew services start postgresql >/dev/null 2>&1 || true
  local i
  for i in $(seq 1 40); do
    if pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  pg_isready -h 127.0.0.1 -p 5432 >/dev/null 2>&1 || return 1
  psql -d postgres -v ON_ERROR_STOP=1 -c "DO \$\$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ballot') THEN CREATE ROLE ballot LOGIN PASSWORD 'ballot_local_dev'; ELSE ALTER ROLE ballot WITH LOGIN PASSWORD 'ballot_local_dev'; END IF; END\$\$;" >/dev/null
  psql -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='ballot'" | grep -q 1 || \
    psql -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE ballot OWNER ballot;" >/dev/null
  export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ballot_local_dev}"
  export DATABASE_URL="postgresql://ballot:${POSTGRES_PASSWORD}@127.0.0.1:5432/ballot"
  if [[ ! -f .env ]]; then
    cp .env.example .env
  fi
  if ! grep -q '^DATABASE_URL=' .env; then
    printf '\nDATABASE_URL=%s\n' "$DATABASE_URL" >> .env
  else
    # Keep .env in sync with the Homebrew port when Docker is not in use.
    python3 - "$DATABASE_URL" <<'PY' || true
import pathlib, sys
url = sys.argv[1]
path = pathlib.Path(".env")
text = path.read_text()
lines = []
found = False
for line in text.splitlines():
    if line.startswith("DATABASE_URL="):
        lines.append(f"DATABASE_URL={url}")
        found = True
    else:
        lines.append(line)
if not found:
    lines.append(f"DATABASE_URL={url}")
path.write_text("\n".join(lines) + "\n")
PY
  fi
  db_ready
}

ensure_postgres() {
  load_env
  if db_ready; then
    echo "PostgreSQL is reachable."
    return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    echo "Starting PostgreSQL (Docker)..."
    docker compose up -d db
    local i
    for i in $(seq 1 40); do
      if docker compose exec -T db pg_isready -U ballot -d ballot >/dev/null 2>&1; then
        export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-ballot_local_dev}"
        export DATABASE_URL="postgresql://ballot:${POSTGRES_PASSWORD}@127.0.0.1:5433/ballot"
        return 0
      fi
      sleep 0.5
    done
    echo "Docker PostgreSQL did not become ready; trying Homebrew..." >&2
  fi
  if ensure_homebrew_postgres; then
    echo "PostgreSQL is reachable on 127.0.0.1:5432."
    return 0
  fi
  cat >&2 <<'EOF'
Could not start a local PostgreSQL.

Options:
  1. Install Homebrew postgresql@16  (brew install postgresql@16 && brew services start postgresql@16)
  2. Install Docker Desktop, then: docker compose up -d db
  3. Point .env at a remote database:
       DATABASE_URL=postgresql://user:pass@host:5432/ballot
     The VPS database is loopback-only; tunnel first:
       ssh -L 5433:127.0.0.1:5433 ubuntu@139.99.135.121
EOF
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
  ./run.sh accuracy --debug --files ResultSlip.jpg,Result_Slip_2024_Previous_Election_Sample.jpg,Result_Slip_2024_Previous_Election_Sample_lower.jpg
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
