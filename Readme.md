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
| **Frontend**      | Vanilla HTML/CSS/JS SPA            |
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
├── frontend/
│   ├── index.html             # SPA with 5 tabs
│   ├── css/style.css          # Election command theme
│   └── js/
│       ├── app.js             # State management & API client
│       ├── viewer.js          # Pan/zoom/rotate image viewer
│       └── components.js      # UI component renderers
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
```

### Running the Application

```bash
# Option 1: Use the startup script
chmod +x run.sh
./run.sh

# Option 2: Manual start
source venv/bin/activate
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Open **http://localhost:8000** in your browser.

### Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v
```

All **14 tests** should pass:

| Test File               | Tests | Coverage Area                    |
|-------------------------|-------|----------------------------------|
| `test_enhancement.py`   | 2     | Image pipeline performance       |
| `test_ocr.py`           | 4     | OCR extraction accuracy (4 slips)|
| `test_multi_page.py`    | 3     | Multi-page grouping rules        |
| `test_validation.py`    | 2     | Validation engine checks         |
| `test_audit.py`         | 1     | Audit trail immutability         |
| `test_api.py`           | 2     | End-to-end API integration       |

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

| Code           | Rule                                              | Default Severity |
|----------------|---------------------------------------------------|-----------------|
| MATH_RECON     | total_valid + total_spoilt = total_votes_cast      | critical        |
| TURNOUT_CEIL   | total_votes_cast ≤ registered_voters               | critical        |
| PARTY_TOTAL    | Σ party votes = total_valid_votes                  | warning         |
| SPOILT_THRESH  | spoilt_votes < 5% of total                         | warning         |
| DUP_DETECT     | No duplicate slip_reference in database            | warning         |
| REG_VOTER_CEIL | total_valid ≤ registered_voters                    | critical        |
| PAGE_COMPLETE  | All expected pages received                        | critical        |

## Sample Data

4 sample ballot slip images are included in `sample_slips/`:

| Image        | Ballot Type | Page   | Station               |
|--------------|-------------|--------|-----------------------|
| `image1.jpg` | Provincial  | 1 of 2 | Britten Station Shop  |
| `image2.jpg` | Regional    | 1 of 2 | —                     |
| `image3.jpg` | Regional    | 2 of 2 | Links with image2     |
| `image4.jpg` | National    | 3 of 3 | —                     |

## Usage Workflow

1. **Upload** — Drag & drop ballot slip images on the Upload tab
2. **Auto-Process** — System enhances images, extracts data via OCR, groups pages
3. **Review** — Operators verify extracted data side-by-side with the enhanced image
4. **Correct** — Override any misread values with reason (audit logged)
5. **Validate** — System checks mathematical reconciliation and business rules
6. **Approve** — Supervisor approves verified results
7. **Export** — Download CSV/JSON/PDF certificate for approved results

## License

This project was developed for the South African IEC ballot result digitisation challenge.
