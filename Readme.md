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

| Layer             | Technology                         |
|-------------------|------------------------------------|
| **Backend**       | Python 3.10+, FastAPI, Uvicorn     |
| **OCR**           | RapidOCR (ONNX Runtime)            |
| **Image Processing** | OpenCV 5.0, Pillow              |
| **Database**      | SQLite (WAL mode)                  |
| **PDF Export**     | ReportLab                         |
| **Frontend**      | React 18 + Vite                     |
| **Testing**       | Pytest + HTTPX                     |

## Project Structure

```
ballot/
├── backend/
│   ├── main.py               # FastAPI application entry point
│   ├── database.py            # SQLite schema, init, seed data
│   ├── models.py              # Pydantic request/response models
│   ├── image_enhancer.py      # OpenCV enhancement pipeline
│   ├── ocr_engine.py          # RapidOCR + barcode parser
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
├── requirements.txt           # Python dependencies
├── run.sh                     # Single-command startup
└── Readme.md
```

## Quick Start

### Prerequisites

- Python 3.10 or higher
- pip
- Node 24+ (to build the React UI)

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd ballot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
cd frontend && npm install && npm run build && cd ..
```

### Running the Application

```bash
# Option 1: Use the startup script
chmod +x run.sh
./run.sh

# Option 2: API and Vite separately (this is how Render + Vercel run)
source venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
# in another terminal:
cd frontend && npm install && npm run dev
```

Open **http://localhost:5173** for the desk (Vite proxies `/api` to port 8000), or **http://localhost:8000** if you used `./run.sh`.

### Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

Pytest covers enhancement, OCR, grouping, validation, audit, and the API. Run it after a `pip install`.

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

High-quality photographed slips live in `sample_slips/`. Debug crops were removed.

| Image        | Ballot Type | Page   | Station                          |
|--------------|-------------|--------|----------------------------------|
| `image1.jpg` | Provincial  | 1 of 2 | Britten Station Shop             |
| `image2.jpg` | Regional    | 1 of 2 | Britten Station Shop             |
| `image3.jpg` | Regional    | 2 of 2 | Groups with image2               |
| `image4.jpg` | National    | 3 of 3 | Britten Station Shop             |
| `i_1.jpg`    | National    | 1 of 3 | Bakgaga Ba-Maake Traditional Aut |
| `i_2.jpg`    | National    | 2 of 3 | Same Limpopo station             |
| `i_3.jpg`    | National    | 3 of 3 | Completes the national set       |
| `i_4.jpg`    | Regional    | 1 of 3 | Same Limpopo station             |
| `i_5.jpg`    | Regional    | 2 of 3 | Missing page 3                   |

Contest photographs 1–4 become **three slips**, not four: regional pages 1 and 2 are one result. Provincial is missing page 2. National is missing pages 1 and 2. That is grouping working, not a lost file.

## Render + Vercel

The Python API runs on Render. The React desk runs on Vercel and calls that API.

### 1. Backend on Render

1. Push this repo to GitHub.
2. In Render, create a **Blueprint** from the repo (`render.yaml`) or a **Web Service** with:
   - Runtime: **Docker**
   - Dockerfile path: `./Dockerfile`
   - Health check: `/api/health`
3. After the first deploy, copy the service URL, e.g. `https://ballot-api.onrender.com`.
4. Set `CORS_ORIGINS` to your Vercel origin (no trailing slash), or leave `*` while you are wiring things up.

Optional persistent disk (paid plans): mount `/data` and set `DATA_DIR=/data`, `BALLOT_DB_PATH=/data/ballot_ocr.db`, `STORAGE_DIR=/data/storage`. Without a disk, SQLite and uploads reset on each deploy.

OCR needs more than Render’s free 512 MB. Use at least a **Starter** instance if uploads die with out-of-memory errors.

### 2. Frontend on Vercel

1. Import the same GitHub repo in Vercel.
2. Prefer **Root Directory = `frontend`**. Vercel then uses `frontend/package.json` (Node `24.x`) and `frontend/vercel.json`. Leave Install / Build / Output **blank** so Vite defaults apply (`npm install`, `npm run build`, `dist`).
3. If you instead leave Root Directory as the repo root, use the root `vercel.json` (it runs `npm … --prefix frontend`). Do **not** combine Root Directory `frontend` with those `--prefix frontend` commands — that looks for `frontend/frontend/package.json` and fails.
4. Add environment variable **`VITE_API_URL`** = the Render URL from step 1, **no trailing slash**.
5. Deploy. Vite bakes `VITE_API_URL` into the bundle, so change it only by redeploying.

Local check of the split: `VITE_API_URL=http://127.0.0.1:8000 npm run build --prefix frontend && npm run preview --prefix frontend`.

## Usage Workflow

1. **Capture** — Drop result slip photographs, or load one of the sample packs
2. **Inbox** — Four contest photos become three slips because regional pages 1 and 2 belong together
3. **Review** — Check the photograph against the extracted counts
4. **Correct** — Override a misread; the change is written to the audit log
5. **Approve** — Blocked until every page is present and critical checks pass
6. **Export** — CSV, JSON, or a PDF certificate for approved slips

## License

This project was developed for the South African IEC ballot result digitisation challenge.
