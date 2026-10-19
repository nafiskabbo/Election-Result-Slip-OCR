#!/usr/bin/env bash
# Isolated ballot-ocr stack on the WeRent OVH VPS.
# Does not touch /etc/komodo/stacks/werent-backend or api.werent.com.au.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST="${BALLOT_VPS_HOST:-ubuntu@139.99.135.121}"
PASSFILE="${BALLOT_VPS_PASSFILE:-$ROOT/.local-secrets/vps-ubuntu-password.txt}"
REMOTE_STACK="/etc/komodo/stacks/ballot-ocr"
PUBLIC_HOST="ballot.139.99.135.121.sslip.io"
CMD="${1:-}"

ssh_cmd() {
  sshpass -f "$PASSFILE" ssh -o StrictHostKeyChecking=accept-new "$HOST" "$@"
}

need() {
  [[ -n "$CMD" ]] || { echo "usage: $0 deploy|health|teardown|status|backup|pull-backup|restore <file>"; exit 1; }
  [[ -f "$PASSFILE" ]] || { echo "Missing $PASSFILE"; exit 1; }
  command -v sshpass >/dev/null || { echo "sshpass is required"; exit 1; }
}

deploy() {
  echo "Backing up production DB + files before deploying..."
  backup
  echo "Syncing isolated stack to $REMOTE_STACK (werent-backend is not touched)..."
  echo "Docker volumes ballot-ocr-pgdata and ballot-ocr-data are not touched."
  ssh_cmd "sudo mkdir -p '$REMOTE_STACK' && sudo chown ubuntu:ubuntu '$REMOTE_STACK'"
  sshpass -f "$PASSFILE" rsync -az --delete \
    --exclude '.git' \
    --exclude 'venv' \
    --exclude '.venv' \
    --exclude 'node_modules' \
    --exclude 'frontend/dist' \
    --exclude '.local-secrets' \
    --exclude 'storage/' \
    --exclude 'backend/digit_finetune/data' \
    --exclude 'backend/digit_finetune/runs' \
    --exclude '__pycache__' \
    --exclude '.agents' \
    --exclude '.cursor' \
    --exclude '.env' \
    --exclude 'backups/' \
    "$ROOT/" "$HOST:$REMOTE_STACK/"

  ssh_cmd "sudo bash -s" <<'EOS'
set -euo pipefail
STACK=/etc/komodo/stacks/ballot-ocr
CADDY=/etc/caddy/Caddyfile
if ! grep -q 'BEGIN ballot-ocr' "$CADDY"; then
  printf '\n' | sudo tee -a "$CADDY" >/dev/null
  sudo tee -a "$CADDY" >/dev/null < "$STACK/deploy/caddy-ballot.caddy"
fi
sudo caddy validate --config "$CADDY"
sudo systemctl reload caddy
cd "$STACK"
if [[ ! -f .env ]]; then
  umask 077
  printf 'POSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 24)" > .env
  chmod 600 .env
fi
sudo docker compose --env-file .env -p ballot-ocr up -d --build
EOS
  echo "Public desk: https://$PUBLIC_HOST"
  echo "JSON index:  https://$PUBLIC_HOST/api"
}

health() {
  echo "=== ballot-ocr ==="
  ssh_cmd "sudo docker compose -p ballot-ocr -f $REMOTE_STACK/docker-compose.yml ps"
  echo "=== ballot public ==="
  curl -fsS "https://$PUBLIC_HOST/api/health" && echo
  echo "=== werent api (must stay up) ==="
  curl -fsS "https://api.werent.com.au/health" && echo
  echo "=== komodo ui ==="
  curl -fsSI "https://komodo.werent.com.au" | head -n 1
}

teardown() {
  if [[ "${2:-}" != "--yes-delete-volumes" ]]; then
    echo "Refusing to teardown. This deletes the ballot-ocr Docker volumes (Postgres + photos)."
    echo "If you really want that: $0 teardown --yes-delete-volumes"
    exit 1
  fi
  echo "Backing up production DB + files before teardown..."
  backup
  echo "Removing isolated ballot-ocr stack only..."
  ssh_cmd "sudo bash -s" <<'EOS'
set -euo pipefail
STACK=/etc/komodo/stacks/ballot-ocr
CADDY=/etc/caddy/Caddyfile
if [[ -f "$STACK/docker-compose.yml" ]]; then
  sudo docker compose -p ballot-ocr -f "$STACK/docker-compose.yml" down -v || true
fi
sudo rm -rf "$STACK"
if grep -q 'BEGIN ballot-ocr' "$CADDY"; then
  sudo python3 - <<'PY'
from pathlib import Path
p = Path("/etc/caddy/Caddyfile")
text = p.read_text()
start = text.find("# BEGIN ballot-ocr")
end = text.find("# END ballot-ocr")
if start != -1 and end != -1:
    end = text.find("\n", end)
    if end == -1:
        end = len(text)
    else:
        end += 1
    p.write_text(text[:start] + text[end:])
PY
  sudo caddy validate --config "$CADDY"
  sudo systemctl reload caddy
fi
EOS
  echo "Removed. WeRent Caddy sites and werent-backend were not rebuilt."
}

status() {
  ssh_cmd 'sudo docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"'
}

backup() {
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  echo "Dumping PostgreSQL + storage volume to $REMOTE_STACK/backups/$stamp"
  sshpass -f "$PASSFILE" scp -o StrictHostKeyChecking=accept-new \
    "$ROOT/scripts/remote-ballot-backup.sh" "$HOST:/tmp/remote-ballot-backup.sh"
  ssh_cmd "sudo bash /tmp/remote-ballot-backup.sh $stamp"
  echo "Remote backup: $REMOTE_STACK/backups/$stamp"
}

pull_backup() {
  stamp="${2:-}"
  if [[ -z "$stamp" ]]; then
    stamp="$(ssh_cmd "ls -1 $REMOTE_STACK/backups" | tail -n 1)"
  fi
  [[ -n "$stamp" ]] || { echo "No remote backups found"; exit 1; }
  mkdir -p "$ROOT/backups/$stamp"
  echo "Pulling $REMOTE_STACK/backups/$stamp -> backups/$stamp"
  sshpass -f "$PASSFILE" rsync -az \
    "$HOST:$REMOTE_STACK/backups/$stamp/" "$ROOT/backups/$stamp/"
  echo "$stamp" > "$ROOT/backups/LATEST"
  ( cd "$ROOT/backups/$stamp" && sha256sum -c SHA256SUMS 2>/dev/null || shasum -a 256 -c SHA256SUMS )
}

restore() {
  dump="${2:-}"
  [[ -n "$dump" ]] || { echo "usage: $0 restore <file> --yes-restore-production"; exit 1; }
  if [[ "${3:-}" != "--yes-restore-production" ]]; then
    echo "Refusing. Restore overwrites the live ballot-ocr database."
    echo "usage: $0 restore <file> --yes-restore-production"
    exit 1
  fi
  echo "Restoring $REMOTE_STACK/backups/$dump"
  ssh_cmd "sudo bash -s" <<EOS
set -euo pipefail
STACK=$REMOTE_STACK
FILE="\$STACK/backups/$dump"
[[ -f "\$FILE" ]] || { echo "Missing \$FILE"; exit 1; }
if [[ "\$FILE" == *.dump ]]; then
  sudo docker compose -p ballot-ocr -f "\$STACK/docker-compose.yml" exec -T db \\
    pg_restore --no-owner --role=ballot --clean --if-exists -d ballot < "\$FILE"
else
  sudo docker compose -p ballot-ocr -f "\$STACK/docker-compose.yml" exec -T db \\
    psql -U ballot -d ballot -v ON_ERROR_STOP=1 < "\$FILE"
fi
EOS
}

need
case "$CMD" in
  deploy) deploy ;;
  health) health ;;
  teardown) teardown "$@" ;;
  status) status ;;
  backup) backup ;;
  pull-backup) pull_backup "$@" ;;
  restore) restore "$@" ;;
  *) echo "usage: $0 deploy|health|teardown|status|backup|pull-backup|restore <file>"; exit 1 ;;
esac
