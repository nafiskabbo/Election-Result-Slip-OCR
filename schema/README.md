# Ballot OCR database

PostgreSQL stores slip records, party counts, validation results, and the audit trail. Uploaded images stay on disk under `storage/` (paths only in the database).

| File | Purpose |
|------|---------|
| `ballot.sql` | Full schema to give the client and to create a new database |
| `seed.sql` | Demo users and default validation rules |

## Create

```bash
createdb ballot
psql -U ballot -d ballot -v ON_ERROR_STOP=1 -f schema/ballot.sql
psql -U ballot -d ballot -v ON_ERROR_STOP=1 -f schema/seed.sql
```

On the VPS the API container runs those files at startup. Compose also mounts them into Postgres for a first-time volume init.

## Backup

Plain SQL (readable, easy to hand over):

```bash
pg_dump -U ballot -d ballot --no-owner --format=plain > ballot-$(date -u +%Y%m%d).sql
```

Custom dump (smaller, use with `pg_restore`):

```bash
pg_dump -U ballot -d ballot --format=custom > ballot-$(date -u +%Y%m%d).dump
```

Schema only (same content as `ballot.sql`, without seed data):

```bash
pg_dump -U ballot -d ballot --schema-only --no-owner > ballot-schema.sql
```

From Docker on the VPS:

```bash
./scripts/vps-ballot.sh backup
```

Files land in `/etc/komodo/stacks/ballot-ocr/backups/`. Copy image files from the `ballot-ocr-data` volume separately if you need a full restore of photographs.

## Restore

```bash
psql -U ballot -d ballot -v ON_ERROR_STOP=1 -f ballot-YYYYMMDD.sql
# or
pg_restore --no-owner --role=ballot --clean --if-exists -d ballot ballot-YYYYMMDD.dump
```

## Tables

- `users` — operators and reviewers
- `slips` — one logical result slip
- `slip_pages` — each photographed page and its file paths
- `party_results` — extracted party/candidate rows
- `audit_logs` — append-only edit and approval history
- `validation_rules` — configurable checks
- `validation_results` — last check outcome per slip
