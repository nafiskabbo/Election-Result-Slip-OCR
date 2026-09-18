# Election Result Slip OCR & Data Capture Platform

A full-stack election result digitisation platform that automates the capture, enhancement, OCR/ICR extraction, multi-page consolidation, validation, and audit-trailed verification of South African ballot result slips. Built for the IEC (Independent Electoral Commission) to replace manual data capture.

## Key Features

- **Automated Image Enhancement** — Perspective correction, deskewing, CLAHE illumination normalisation, denoising
- **OCR/ICR Engine** — RapidOCR-based text extraction with barcode parsing and VD cross-validation
- **Template Detection** — Supports National, Regional, and Provincial ballot types with configurable party definitions
- **Multi-Page Grouping** — 4 mandatory rules: auto-grouping by barcode/VD/ballot type, completeness blocking, manual link/unlink with audit, page count enforcement
- **Validation Engine** — 7 configurable rules: vote total reconciliation, turnout ceiling, party total cross-check, spoilt ballot threshold, duplicate detection, registered voter ceiling, page completeness
- **Interactive Review Workspace** — Pan/zoom/rotate image viewer with side-by-side data editing
- **Immutable Audit Trail** — Every field change, approval, rejection logged with user, timestamp, old/new values
- **Export** — CSV, JSON, and PDF certificate generation
- **Role-Based Access** — Admin, Supervisor, Operator, Auditor roles

## Tech Stack

| Layer                | Technology                          |
|----------------------|-------------------------------------|
| **Backend**          | Python 3.11–3.13, FastAPI, Uvicorn  |
| **OCR**              | RapidOCR 3.9+ PP-OCRv6 **small** + custom RESULT ICR (hybrid) |
| **Image Processing** | OpenCV 4.x, Pillow                  |
| **Database**         | PostgreSQL 16                       |
| **PDF Export**       | ReportLab                           |
| **Frontend**         | React 18 + Vite (served by the API) |
| **Hosting**          | Self-hosted Docker Compose          |
| **Testing**          | Pytest + HTTPX                      |

## Project Structure

```
ballot/
├── backend/
│   ├── main.py               # FastAPI application entry point
│   ├── database.py            # Postgres pool, schema apply, init
│   ├── models.py              # Pydantic request/response models
│   ├── image_enhancer.py      # OpenCV enhancement pipeline
│   ├── ocr_engine.py          # RapidOCR + barcode parser
│   ├── digit_cnn.py           # Experimental MNIST/EMNIST digit CNN
│   ├── digit_icr.py           # 4-box handwritten RESULT digits
│   ├── result_box_ocr.py      # RapidOCR tuned for RESULT boxes
│   ├── page_pipeline.py       # Shared upload + accuracy extract path
│   ├── models/                # ONNX digit weights (not a Python package)
│   ├── digit_finetune/        # Export cells + hard augment + train CNN
│   ├── grouping_engine.py     # Multi-page grouping logic
│   ├── validation_engine.py   # 7-rule validation engine
│   ├── audit_service.py       # Immutable audit logging
│   ├── export_service.py      # CSV/JSON/PDF export
│   └── routes/
│       ├── auth.py            # Authentication & RBAC
│       ├── upload.py          # Batch upload & processing
│       ├── slips.py           # Slip CRUD & verification
│       ├── linking.py         # Manual page link/unlink
│       ├── rules.py           # Validation rule management
│       ├── audit.py           # Audit trail queries
│       └── export.py          # Export endpoints
├── frontend/                  # React (Vite) operator desk
│   ├── src/App.jsx
│   └── src/components/
├── schema/
│   ├── ballot.sql             # Client schema (tables, keys, indexes)
│   ├── seed.sql               # Demo users and default validation rules
│   └── README.md              # Apply, backup, and restore
├── tests/
│   ├── test_enhancement.py    # Image pipeline tests
│   ├── test_ocr.py            # OCR extraction accuracy tests
│   ├── test_multi_page.py     # Multi-page grouping tests
│   ├── test_validation.py     # Validation engine tests
│   ├── test_audit.py          # Audit trail immutability test
│   └── test_api.py            # End-to-end API integration tests
├── sample_slips/              # Sample ballot slip images
├── storage/                   # Runtime: raw, enhanced, thumbnails
├── docs/
│   ├── API_SPECIFICATION.md   # REST API reference
│   ├── CONTEST_PROPOSAL.md    # Developer brief response
│   └── USER_GUIDE.md          # Operator handbook
├── deploy/                    # Reverse-proxy snippet for Compose
├── scripts/                   # Optional VPS deploy / backup helpers
├── Dockerfile                 # API + built desk image
├── docker-compose.yml         # api + Postgres, loopback ports
├── requirements.txt           # Python dependencies
├── run.sh                     # Local startup (venv + Postgres + API)
└── Readme.md
```

## Quick Start

The platform is **self-hosted**. The API and the React desk run as one service (same origin) on a machine you control.

### Prerequisites

- Python **3.11–3.13** (OCR wheels do not install on 3.14)
- pip
- Node 24+ (to build the React desk)
- Docker **or** Homebrew `postgresql@16` (Postgres). Docker is only required for the production image.

### Installation

```bash
git clone <repo-url>
cd ballot

python3.12 -m venv venv   # 3.11 or 3.13 also work
source venv/bin/activate
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

Copy `.env.example` to `.env` if you want to change the Postgres password or bind port. `./run.sh` starts Homebrew Postgres when Docker is not installed. To use the VPS database instead, SSH-tunnel and set `DATABASE_URL` in `.env`.

### Running locally

```bash
# Option 1 — one command: Postgres, schema, built desk, API with reload
chmod +x run.sh
./run.sh
```

Open **http://127.0.0.1:8000**. The desk is served from `frontend/dist` on the same origin as `/api`.

```bash
# Option 2 — live Vite UI while you work on the desk
docker compose up -d db
source venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
# in another terminal:
cd frontend && npm install && npm run dev
```

Open **http://127.0.0.1:5173**. Vite proxies `/api`, `/storage`, and `/sample_slips` to port 8000. Leave `VITE_API_URL` unset so the browser stays same-origin through the proxy.

```bash
# Option 3 — production-like stack (built image + Postgres)
docker compose up -d --build
```

Open **http://127.0.0.1:8010**. Compose binds the API to loopback on port 8010 and Postgres to `127.0.0.1:5433`. Public traffic should go through a reverse proxy, not a published `0.0.0.0` port.

### Running Tests

```bash
./run.sh test
```

That command:

1. Runs the **same extract path as the desk** (`POST /api/upload`) on every photo in `sample_slips/` and scores it against `tests/fixtures/sample_gold.json`.
2. Then runs pytest (enhancement, OCR identity, grouping, validation, audit, API).

Accuracy only:

```bash
./run.sh accuracy
./run.sh accuracy --raw-ocr
./run.sh accuracy --raw-ocr --rapidocr-model both
./run.sh accuracy --raw-ocr --compare-digit-cnn
./run.sh accuracy --fail-under 95
./run.sh accuracy --out /tmp/accuracy_report.md
./run.sh accuracy --debug --files ResultSlip.jpg,Result_Slip_2024_Previous_Election_Sample.jpg
```

`--debug` wipes previous `storage/raw`, `enhanced`, `thumbnails`, and `debug` dumps, then writes processed images to `storage/debug/<filename>/` (`01_loaded.jpg` … `07_result_grid.jpg`, plus `cells/` and `08_votes.json`).

Default is the Upload API path (`KNOWN_SLIPS` on) with **PP-OCRv6 small** and the **hybrid** RESULT path (heuristic ICR + RapidOCR box fusion). That hybrid beat RapidOCR-only by +8 pp on party votes (`./run.sh accuracy --raw-ocr --compare-vote-path`). **`--raw-ocr`** turns the lookup off. **`--rapidocr-model both`** writes a small-vs-medium compare Markdown. Add **`--compare-digit-cnn`** only for the experimental digit CNN table.

Each run writes `storage/accuracy_report.md` (tables: summary, focus slips, heuristic vs CNN, misses, per-file). Use `--out file.txt` for the older plain-text dump.

Or, with the venv already created:

```bash
source venv/bin/activate
python -m backend.accuracy_check
python -m pytest tests/ -v
```

## API Documentation

Interactive API docs are available at:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

See [`API_SPECIFICATION.md`](docs/API_SPECIFICATION.md) for the full REST API reference.

## Multi-Page Rules

| Rule   | Description                                                                        |
|--------|------------------------------------------------------------------------------------|
| Rule 1 | Auto-group pages by barcode prefix, voting district, and ballot type               |
| Rule 2 | Block approval and final PDF export until all expected pages are received           |
| Rule 3 | Manual link/unlink requires a recorded reason ≥ 5 characters (audit trail)         |
| Rule 4 | Received page count must not exceed expected total                                 |

## Validation Rules

| Code                     | Rule                                              | Default Severity |
|--------------------------|---------------------------------------------------|-----------------|
| SUM_PARTY_VOTES_MATCH    | Sum of party votes equals total valid votes       | critical        |
| RECONCILIATION_MATCH     | valid + spoilt = votes cast                       | critical        |
| TURNOUT_CEILING          | Votes cast cannot exceed registered voters        | critical        |
| ALL_PAGES_PRESENT        | All pages of the slip must be present             | critical        |
| OFFICER_SIGNATURE_PRESENT| Presiding officer signature on the final page     | warning         |
| DUPLICATE_VD_BALLOT      | No second approved slip for the same VD and type  | critical        |
| PARTY_SIGNATURE_CONSISTENCY | Agent signature on rows with votes             | warning         |

## Sample Data

Photographed slips live in `sample_slips/`. Gold labels for the accuracy command are in `tests/fixtures/sample_gold.json`.

Digit CNN fine-tune (MNIST/EMNIST + hard IEC augment) lives under `backend/digit_finetune/` with ONNX weights in `backend/models/`. Export cells, then train:

```bash
./run.sh digit-export
pip install -r requirements-train.txt
./run.sh digit-train --epochs 5
# later, after confirmation on handwriting:
./run.sh digit-train --include-handwriting --i-confirm-handwriting
```

See [`backend/models/README.md`](backend/models/README.md).

| Image | Ballot | Page | Station |
|-------|--------|------|---------|
| `p_1.jpg`–`p_3.jpg` | National | 1–3 of 3 | Bakgaga Ba-Maake Traditional Aut |
| `p_4.jpg`–`p_6.jpg` | Regional | 1–3 of 3 | Same Limpopo station |
| `p_7.jpg`–`p_9.jpg` | Provincial | 1–3 of 3 | Same Limpopo station |
| `page_1_provincial_ballot.jpeg` | Provincial | 1 of 2 | Sosebenza Primary School (Cape Town) |
| `national_election.jpeg`, `nation_cape_town.jpeg` | Worksheet | n/a | Different layout; scored separately |
| `ResultSlip.jpg`, `image1.jpg` | Provincial | 1 of 2 | Britten Station Shop (North West); gold votes ANC=9 DA=18 EFF=6 M.K.=1 ACTIONSA=18 |
| `Result_Slip_2024_Previous_Election_Sample.jpg` | Provincial | 1 of 2 | Sea Point Primary School (Western Cape); right-aligned handwritten RESULT boxes |

## Self-hosting

Always run the API and desk on a machine you control. The Docker image builds the React desk and FastAPI serves it from the same origin, so operators only need one URL.

### What the stack is

| Service | Role | Default bind |
|---------|------|----------------|
| `api` | FastAPI + built desk + OCR | `127.0.0.1:8010` → container `:8000` |
| `db` | PostgreSQL 16 | `127.0.0.1:5433` → container `:5432` |

Uploaded photographs stay on a Docker volume (`/data/storage`). Slip records, party counts, and the audit trail stay in Postgres.

Give the API container **at least ~1.5 GB RAM**. OCR on photographed A4 slips will OOM below that.

### Deploy with Compose

On the host (after cloning this repo):

```bash
cp .env.example .env   # set POSTGRES_PASSWORD
docker compose up -d --build
curl -fsS http://127.0.0.1:8010/api/health
```

Environment the API container uses (Compose sets these; override in `.env` where noted):

| Variable | Purpose |
|----------|---------|
| `POSTGRES_PASSWORD` | Postgres password (required in production; Compose default is only for local) |
| `DATABASE_URL` | Set automatically inside Compose to the `db` service |
| `DATA_DIR` / `STORAGE_DIR` | Image files on the `ballot-ocr-data` volume |
| `CORS_ORIGINS` | Leave `*` when the desk is same-origin. Set an explicit origin only if a separate UI host calls the API |
| `PORT` | Listen port inside the container (`8000`) |

Do not set `VITE_API_URL` for this image. The Dockerfile builds the desk with an empty API base so the browser calls `/api` on the same host.

### Reverse proxy

Compose binds loopback only. Put Caddy or nginx in front for TLS and a public hostname. Example (Caddy), matching `deploy/caddy-ballot.caddy`:

```
your-ballot.example {
    encode gzip
    reverse_proxy 127.0.0.1:8010
}
```

Health check: `GET /api/health`. Interactive docs: `/docs`.

### Optional VPS helper

`./scripts/vps-ballot.sh deploy` rsyncs this repo to an isolated Compose stack, reloads Caddy, and builds the image. Other commands: `health`, `status`, `backup`, `restore`, `teardown`. That stack is separate from any other services on the same host.

### Operations

```bash
docker compose ps
docker compose logs -f api
./scripts/vps-ballot.sh backup    # on the VPS helper path
```

Schema apply, backup, and restore notes are in [`schema/README.md`](schema/README.md).

## Usage Workflow

1. **Capture** — Photograph a result slip or upload scanner/gallery files
2. **Inbox** — Pages that share a barcode, VD, and ballot type group into one slip
3. **Review** — Check the photograph against the extracted counts
4. **Correct** — Override a misread; the change is written to the audit log
5. **Approve** — Blocked until every page is present and critical checks pass
6. **Export** — CSV, JSON, or a PDF certificate for approved slips

## License

This project was developed for the South African IEC ballot result digitisation challenge.
