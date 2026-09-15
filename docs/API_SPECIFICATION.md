# REST API Specification

**Base URL**: `http://localhost:8000`  
**Interactive Docs**: [Swagger UI](/docs) · [ReDoc](/redoc)

---

## Authentication & RBAC

### `GET /api/auth/users`
List all registered users.

**Response** `200 OK`
```json
[
  {
    "id": "usr_admin",
    "username": "admin",
    "full_name": "System Administrator",
    "role": "admin",
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

---

### `GET /api/auth/current`
Get the currently active user session.

**Response** `200 OK`
```json
{
  "id": "usr_operator",
  "username": "operator",
  "full_name": "Data Capture Operator (John Doe)",
  "role": "operator"
}
```

---

### `POST /api/auth/switch`
Switch the active user role for demo/testing.

**Request Body**
| Field | Type   | Required | Description                          |
|-------|--------|----------|--------------------------------------|
| role  | string | Yes      | One of: `admin`, `supervisor`, `operator`, `auditor` |

**Response** `200 OK` — Returns the updated active user object.

```bash
curl -X POST http://localhost:8000/api/auth/switch \
  -H "Content-Type: application/json" \
  -d '{"role": "supervisor"}'
```

---

## Upload & Processing Pipeline

### `POST /api/upload`
Upload one or more ballot slip images for automated processing.

**Request**: `multipart/form-data`
| Field | Type            | Required | Description                         |
|-------|-----------------|----------|-------------------------------------|
| files | File[] (binary) | Yes      | Image files (.jpg, .jpeg, .png, .pdf) |

**Processing Pipeline** (per image):
1. Image enhancement (perspective correction, deskew, CLAHE, denoise)
2. OCR/ICR extraction (barcode, metadata, party vote counts)
3. Multi-page auto-grouping (Rule 1)
4. Validation rule evaluation

**Response** `200 OK`
```json
{
  "processed_pages_count": 2,
  "affected_slips": ["slip_abc123"],
  "pages": [
    {
      "page_id": "page_xyz789",
      "slip_id": "slip_abc123",
      "original_filename": "ballot_p1.jpg",
      "page_number": 1,
      "page_total": 2,
      "ballot_type": "Provincial",
      "barcode_text": "001335868205982011",
      "enhanced_file_path": "storage/enhanced/enh_xxx_ballot_p1.jpg",
      "thumbnail_path": "storage/thumbnails/thumb_enh_xxx_ballot_p1.jpg",
      "enhancement_seconds": 0.12,
      "is_perspective_corrected": true,
      "skew_angle": -1.3
    }
  ],
  "total_elapsed_seconds": 2.45,
  "average_per_page_seconds": 1.225
}
```

```bash
curl -X POST http://localhost:8000/api/upload \
  -F "files=@sample_slips/image1.jpg" \
  -F "files=@sample_slips/image2.jpg"
```

---

## Slips Management & Verification

### `GET /api/slips`
List all ballot result slips with optional filters.

**Query Parameters**
| Param           | Type   | Description                                  |
|-----------------|--------|----------------------------------------------|
| status          | string | Filter by status: `incomplete`, `pending_review`, `approved`, `rejected`, `flagged` |
| ballot_type     | string | Filter by ballot type: `National`, `Regional`, `Provincial` |
| voting_district | string | Filter by voting district code               |
| search          | string | Free-text search across slip_reference, station_name, municipality, voting_district |

**Response** `200 OK` — Array of `SlipSummary` objects.

```bash
curl "http://localhost:8000/api/slips?status=pending_review&ballot_type=Provincial"
```

---

### `GET /api/slips/{slip_id}`
Get full detail for a single slip including pages, party results, and validation results.

**Response** `200 OK` — `SlipDetail` object (extends `SlipSummary`).

| Field              | Type                   | Description                    |
|--------------------|------------------------|--------------------------------|
| pages              | SlipPage[]             | All received pages             |
| party_results      | PartyResult[]          | All party vote rows            |
| validation_results | ValidationResult[]     | Current validation rule states |

---

### `PATCH /api/slips/{slip_id}/field`
Update an editable field on a slip. Triggers re-validation and creates an audit log entry.

**Request Body**
| Field      | Type   | Required | Description                       |
|------------|--------|----------|-----------------------------------|
| field_name | string | Yes      | See allowed fields below          |
| new_value  | any    | Yes      | New value for the field           |
| reason     | string | No       | Reason for change (audit trail)   |

**Allowed Fields**: `station_name`, `municipality`, `province`, `registered_voters`, `total_valid_votes`, `total_spoilt_votes`, `total_votes_cast`, `special_votes`, `section_24a_votes`, `presiding_officer_name`

**Response** `200 OK`
```json
{
  "message": "Field updated successfully",
  "validation": { "total_rules": 7, "passed": 5, "failed": 1, "warned": 1, "has_critical_error": true }
}
```

---

### `PATCH /api/slips/{slip_id}/party`
Override a party's vote count. Marks the row as manually overridden.

**Request Body**
| Field           | Type   | Required | Description                     |
|-----------------|--------|----------|---------------------------------|
| party_result_id | string | Yes      | ID of the party_results row     |
| votes           | int    | Yes      | New vote count (≥ 0)            |
| reason          | string | No       | Reason for override             |

**Response** `200 OK` — Same as field update.

---

### `POST /api/slips/{slip_id}/approve`
Approve a verified slip.

**Blocking Rules**:
- **Rule 2**: Incomplete slips (missing pages) cannot be approved.
- Critical validation failures block approval.

**Response** `200 OK`
```json
{ "message": "Slip approved successfully", "slip_id": "slip_abc", "status": "approved" }
```

**Error** `400 Bad Request` — When blocked by Rule 2 or critical validation failure.

---

### `POST /api/slips/{slip_id}/reject`
Reject a slip with an optional reason.

**Request Body**
| Field  | Type   | Required | Description          |
|--------|--------|----------|----------------------|
| status | string | Yes      | Must be `"rejected"` |
| reason | string | No       | Rejection reason     |

---

### `POST /api/slips/{slip_id}/flag`
Flag a slip for supervisor review.

**Request Body**
| Field  | Type   | Required | Description         |
|--------|--------|----------|---------------------|
| status | string | Yes      | Must be `"flagged"` |
| reason | string | No       | Flag reason         |

---

## Multi-Page Linking & Exception Control

### `POST /api/linking/link`
Manually link a page to a different slip record. **Rule 3**: A valid reason (≥ 5 characters) is mandatory.

**Request Body**
| Field          | Type   | Required | Description                              |
|----------------|--------|----------|------------------------------------------|
| page_id        | string | Yes      | ID of the page to re-assign              |
| target_slip_id | string | Yes      | ID of the destination slip               |
| reason         | string | Yes      | Reason for manual link (≥ 5 chars)       |

**Response** `200 OK`
```json
{
  "message": "Page linked successfully",
  "result": {
    "page_id": "page_xyz",
    "old_slip_id": "slip_old",
    "new_slip_id": "slip_new",
    "target_validation": { ... }
  }
}
```

---

### `POST /api/linking/unlink`
Unlink a page from its current slip, creating a new standalone slip record. **Rule 3** applies.

**Request Body**
| Field   | Type   | Required | Description                         |
|---------|--------|----------|-------------------------------------|
| page_id | string | Yes      | ID of the page to unlink            |
| reason  | string | Yes      | Reason for manual unlink (≥ 5 chars)|

---

## Validation Engine & Rule Builder

### `GET /api/rules`
List all configured validation rules.

**Response** `200 OK`
```json
[
  {
    "id": "rule_001",
    "rule_code": "MATH_RECON",
    "name": "Mathematical Reconciliation",
    "description": "total_valid_votes + total_spoilt_votes must equal total_votes_cast",
    "rule_type": "mathematical",
    "is_active": true,
    "severity": "critical",
    "config_json": {}
  }
]
```

**Available Rules**:

| Code           | Name                        | Type          | Default Severity |
|----------------|-----------------------------|---------------|-----------------|
| MATH_RECON     | Mathematical Reconciliation | mathematical  | critical        |
| TURNOUT_CEIL   | Turnout Ceiling             | threshold     | critical        |
| PARTY_TOTAL    | Party Total Cross-check     | mathematical  | warning         |
| SPOILT_THRESH  | Spoilt Ballot Threshold     | threshold     | warning         |
| DUP_DETECT     | Duplicate Detection         | integrity     | warning         |
| REG_VOTER_CEIL | Registered Voter Ceiling    | threshold     | critical        |
| PAGE_COMPLETE  | Page Completeness           | completeness  | critical        |

---

### `PATCH /api/rules/{rule_code}`
Update a validation rule's configuration.

**Request Body**
| Field       | Type   | Required | Description                        |
|-------------|--------|----------|------------------------------------|
| is_active   | bool   | No       | Enable or disable the rule         |
| severity    | string | No       | `"critical"`, `"warning"`, `"info"`|
| config_json | object | No       | Rule-specific configuration        |

```bash
curl -X PATCH http://localhost:8000/api/rules/SPOILT_THRESH \
  -H "Content-Type: application/json" \
  -d '{"severity": "critical", "config_json": {"threshold_percent": 3}}'
```

---

### `POST /api/rules/evaluate/{slip_id}`
Force re-evaluation of all active rules against a specific slip.

**Response** `200 OK`
```json
{
  "slip_id": "slip_abc",
  "total_rules": 7,
  "passed": 5,
  "failed": 1,
  "warned": 1,
  "has_critical_error": true,
  "results": [
    { "rule_code": "MATH_RECON", "status": "pass", "message": "..." },
    { "rule_code": "TURNOUT_CEIL", "status": "fail", "message": "..." }
  ]
}
```

---

## Audit Trail & History

### `GET /api/audit`
Retrieve the global audit trail.

**Query Parameters**
| Param  | Type | Default | Description                  |
|--------|------|---------|------------------------------|
| limit  | int  | 100     | Max entries to return (1–500)|
| offset | int  | 0       | Pagination offset            |

**Response** `200 OK` — Array of `AuditLogItem`.

```json
[
  {
    "id": "aud_abc123",
    "slip_id": "slip_xyz",
    "page_id": null,
    "user_id": "usr_operator",
    "user_name": "operator",
    "user_role": "operator",
    "action": "edit_slip_field",
    "field_name": "total_valid_votes",
    "old_value": "50",
    "new_value": "52",
    "reason": "Corrected based on physical count",
    "ip_address": null,
    "timestamp": "2026-09-15T01:23:45Z"
  }
]
```

---

### `GET /api/audit/slip/{slip_id}`
Retrieve the audit trail for a specific slip.

**Response** `200 OK` — Array of `AuditLogItem` filtered by slip.

---

## Export & Reporting

### `GET /api/export/csv`
Export all slips as a summary CSV file.

**Query Parameters**
| Param  | Type   | Description                |
|--------|--------|----------------------------|
| status | string | Optional status filter     |

**Response**: `text/csv` file download.

```bash
curl "http://localhost:8000/api/export/csv?status=approved" -o results.csv
```

---

### `GET /api/export/slips/{slip_id}/csv`
Export a single slip's detailed results (including party votes) as CSV.

---

### `GET /api/export/slips/{slip_id}/json`
Export a single slip's complete data as JSON.

---

### `GET /api/export/slips/{slip_id}/pdf`
Generate a formal PDF result certificate for a slip.

**Blocking Rule**: Rule 2 — Incomplete slips cannot generate certificates.

**Response**: `application/pdf` inline document.

**Error** `400 Bad Request` — When blocked by Rule 2 (incomplete pages).

---

## Data Schemas

### SlipSummary

| Field                                 | Type    | Nullable |
|---------------------------------------|---------|----------|
| id                                    | string  | No       |
| slip_reference                        | string  | No       |
| ballot_type                           | string  | No       |
| election_name                         | string  | No       |
| province                              | string  | Yes      |
| municipality                          | string  | Yes      |
| voting_district                       | string  | No       |
| station_name                          | string  | Yes      |
| registered_voters                     | int     | No       |
| status                                | enum    | No       |
| presiding_officer_name                | string  | Yes      |
| presiding_officer_signature_detected  | bool    | No       |
| total_valid_votes                     | int     | No       |
| total_spoilt_votes                    | int     | No       |
| total_votes_cast                      | int     | No       |
| special_votes                         | int     | No       |
| section_24a_votes                     | int     | No       |
| total_expected_pages                  | int     | No       |
| total_received_pages                  | int     | No       |
| created_at                            | string  | No       |
| updated_at                            | string  | No       |
| approved_at                           | string  | Yes      |
| approved_by                           | string  | Yes      |
| rejection_reason                      | string  | Yes      |
| has_errors                            | bool    | No       |
| has_warnings                          | bool    | No       |

**Status enum**: `incomplete` | `pending_review` | `approved` | `rejected` | `flagged`

### SlipDetail
Extends `SlipSummary` with:

| Field              | Type               |
|--------------------|--------------------|
| pages              | SlipPage[]         |
| party_results      | PartyResult[]      |
| validation_results | ValidationResult[] |

### PartyResult

| Field              | Type   | Description                      |
|--------------------|--------|----------------------------------|
| id                 | string | Unique row ID                    |
| slip_id            | string | Parent slip                      |
| page_id            | string | Source page                      |
| row_index          | int    | Row position on the page         |
| party_name         | string | Full party name                  |
| party_code         | string | Short code (e.g., ANC, DA)       |
| votes              | int    | Current vote count               |
| confidence_score   | float  | OCR confidence (0.0–1.0)         |
| is_overridden      | bool   | Whether manually overridden      |
| overridden_by      | string | Username who overrode (nullable) |
| original_ocr_votes | int    | Original OCR-extracted value     |
| signature_detected | bool   | Signature mark detected          |
| bbox_json          | string | Bounding box coordinates (JSON)  |

### AuditLogItem

| Field      | Type   | Description                     |
|------------|--------|---------------------------------|
| id         | string | Unique log entry ID             |
| slip_id    | string | Related slip (nullable)         |
| page_id    | string | Related page (nullable)         |
| user_id    | string | User who performed the action   |
| user_name  | string | Username (nullable)             |
| user_role  | string | User's role (nullable)          |
| action     | string | Action performed                |
| field_name | string | Field that was changed          |
| old_value  | string | Previous value                  |
| new_value  | string | New value                       |
| reason     | string | Reason/justification            |
| ip_address | string | Client IP (nullable)            |
| timestamp  | string | ISO 8601 timestamp              |

### Audit Actions

| Action                 | Description                              |
|------------------------|------------------------------------------|
| upload_page            | New page uploaded and processed          |
| edit_slip_field        | Slip metadata field changed              |
| override_party_votes   | Party vote count manually overridden     |
| approve_result         | Slip approved                            |
| reject_result          | Slip rejected                            |
| flag_for_review        | Slip flagged for supervisor review       |
| manual_link_page       | Page manually linked to a different slip |
| manual_unlink_page     | Page unlinked into a new slip            |
| update_validation_rule | Validation rule configuration changed    |

---

## Static File Mounts

| Path            | Description                                |
|-----------------|--------------------------------------------|
| `/storage/*`    | Enhanced images, thumbnails, raw uploads   |
| `/sample_slips/*` | Sample ballot slip images for demo       |
| `/`             | Frontend SPA (index.html)                  |
