#!/usr/bin/env bash
# Run on the VPS as root. Dumps Postgres and the storage volume without mutating data.
set -euo pipefail
STAMP="${1:?stamp}"
STACK=/etc/komodo/stacks/ballot-ocr
OUT="$STACK/backups/$STAMP"
mkdir -p "$OUT"

fingerprint() {
  sudo docker compose -p ballot-ocr -f "$STACK/docker-compose.yml" exec -T db \
    psql -U ballot -d ballot -At -c "$1" </dev/null
}

write_fingerprint() {
  local dest="$1"
  {
    echo "users=$(fingerprint 'select count(*) from users;')"
    echo "slips=$(fingerprint 'select count(*) from slips;')"
    echo "slip_pages=$(fingerprint 'select count(*) from slip_pages;')"
    echo "party_results=$(fingerprint 'select count(*) from party_results;')"
    echo "audit_logs=$(fingerprint 'select count(*) from audit_logs;')"
    echo "validation_results=$(fingerprint 'select count(*) from validation_results;')"
    echo "validation_rules=$(fingerprint 'select count(*) from validation_rules;')"
    echo "slip_ids=$(fingerprint "select md5(coalesce(string_agg(id, ',' order by id), '')) from slips;")"
    echo "page_ids=$(fingerprint "select md5(coalesce(string_agg(id, ',' order by id), '')) from slip_pages;")"
    echo "party_ids=$(fingerprint "select md5(coalesce(string_agg(id, ',' order by id), '')) from party_results;")"
    echo "audit_ids=$(fingerprint "select md5(coalesce(string_agg(id, ',' order by id), '')) from audit_logs;")"
  } | tee "$dest"
}

write_fingerprint "$OUT/fingerprint-before.txt"

echo "Dumping SQL..."
sudo docker compose -p ballot-ocr -f "$STACK/docker-compose.yml" exec -T db \
  pg_dump -U ballot -d ballot --no-owner --format=plain \
  > "$OUT/ballot.sql"

echo "Dumping custom..."
sudo docker compose -p ballot-ocr -f "$STACK/docker-compose.yml" exec -T db \
  pg_dump -U ballot -d ballot --format=custom \
  > "$OUT/ballot.dump"

echo "Archiving storage volume..."
sudo docker run --rm \
  -v ballot-ocr_ballot-ocr-data:/data \
  -v "$OUT":/out \
  alpine tar czf /out/storage.tar.gz -C /data .

write_fingerprint "$OUT/fingerprint-after.txt"

if ! cmp -s "$OUT/fingerprint-before.txt" "$OUT/fingerprint-after.txt"; then
  echo "ERROR: production fingerprint changed during backup" >&2
  diff -u "$OUT/fingerprint-before.txt" "$OUT/fingerprint-after.txt" >&2 || true
  exit 1
fi

( cd "$OUT" && sha256sum ballot.sql ballot.dump storage.tar.gz fingerprint-before.txt fingerprint-after.txt > SHA256SUMS )
ls -lh "$OUT"
sudo chown -R ubuntu:ubuntu "$STACK/backups"
echo "BACKUP_OK $STAMP"
