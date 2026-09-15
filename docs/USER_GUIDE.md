# Election Result Slip OCR Platform — User Guide

A step-by-step operational handbook for Data Capture Operators, Election Supervisors, and Electoral Auditors.

---

## 1. Getting Started

### 1.1 Launching the Platform
Run the self-contained startup script in your terminal:
```bash
./run.sh
```
This automatically verifies dependencies, initializes the relational database, and starts the server on `http://127.0.0.1:8000`.

Open your browser to:
- **Web Application**: `http://127.0.0.1:8000`
- **Interactive API Documentation**: `http://127.0.0.1:8000/docs`

### 1.2 User Personas & Role Switching
In the top right of the navigation header, select your active persona:
- **Data Capture Operator**: Upload batches, verify extracted values, perform manual edits with justification, request supervisor approval.
- **Election Supervisor**: Review exceptions, certify & approve slips, reject invalid submissions, perform manual linking/unlinking, configure validation rules.
- **Electoral Auditor**: Read-only oversight of all captures, validation reports, and immutable audit logs.
- **System Administrator**: Full system access, rule engine tuning, and user management.

---

## 2. Upload & Automated Enhancement

1. Navigate to the **"📤 Batch Upload & OCR"** tab.
2. Drag and drop single or multiple photographed slips (JPG, PNG) or multi-page PDF files into the dropzone.
3. **Automated Processing**:
   - The computer vision pipeline automatically detects paper boundaries, warps perspective to flat rectangular alignment, deskews orientation, normalizes contrast, and removes ambient shadows in **$< 0.2$ seconds per page**.
   - Raw uploaded files are stored safely in `storage/raw/` (never overwritten).
   - High-resolution enhanced images are stored in `storage/enhanced/`.
4. **Quick Sample Demo**:
   - Click **"⚡ Load Official Samples"** to automatically process the 4 supplied official 2024 contest sample slips in a single batch.

---

## 3. Results Dashboard

The **"📊 Results Dashboard"** displays:
- **Summary Metrics Cards**: Total Slips, Approved, Pending Review, Incomplete Sets, and Flagged Exceptions.
- **Search & Filters**: Filter by ballot type (`Provincial`, `Regional`, `National`), status (`Pending Review`, `Incomplete`, `Approved`, `Flagged`), or search by Voting District (VD) and station name.
- **Export All**: Click **"📥 Export All (CSV)"** to download the consolidated summary sheet of all ballot records.

---

## 4. Side-by-Side Review Workspace

Click **"Review & Verify"** on any slip in the dashboard table to open the synchronized review workspace:

### 4.1 Image Viewer (Left Pane)
- **Pan**: Click and drag on the image (or swipe on touchscreen) to pan across the slip.
- **Zoom**: Use your mouse wheel or the `🔍+` and `🔍−` toolbar buttons (50% to 400% zoom).
- **Rotate**: Click `↻` to rotate by 90-degree increments.
- **Fit to Screen**: Click `⤢ Fit` to reset framing.
- **Page Tabs**: For multi-page slips, click the `Page 1 of 2` or `Page 2 of 2` pills to switch between pages.

### 4.2 Tabular Data Form (Right Pane)
- **Hover Highlighting**: Hover over any candidate/party row in the table; the image viewer automatically highlights the corresponding tally box coordinates with a bounding box!
- **Confidence Chips**:
  - 🟢 **Green ($\ge 90\%$)**: High OCR confidence.
  - 🟡 **Yellow ($70-89\%$)**: Moderate confidence, review recommended.
  - 🔴 **Red ($< 70\%$)**: Low confidence, operator verification required.
- **Manual Overrides**:
  - Type in the vote input field to correct any digit.
  - The cell is highlighted in blue with an `overridden` marker.
  - An immutable audit log entry is recorded with your operator ID, timestamp, old value, new value, and recorded reason.
  - Totals and validation rules re-calculate instantly in real time!

### 4.3 Mandatory Multi-Page Rules & Incomplete Sets
- **Rule 1 (Automatic Grouping)**: Pages sharing the same barcode slip reference (e.g. Sample 2 and Sample 3 Regional Ballot) automatically consolidate into one unified slip record.
- **Rule 2 (Incomplete Set Alert)**:
  - If a slip is missing pages (e.g. Sample 1 is missing Page 2 of 2; Sample 4 is missing Pages 1 & 2 of 3), a prominent red alert banner is displayed:
    > ⛔ **MANDATORY MULTI-PAGE RULE 2: INCOMPLETE RESULT SET**  
    > Only 1 of 2 expected pages are present. Approval and final export are strictly blocked until all missing pages are uploaded and linked.
  - The **"✓ Approve Result"** button and **"📄 PDF Cert"** export button are automatically disabled.

### 4.4 Manual Linking and Unlinking (Rule 3)
- If a misfiled page needs to be reassigned to another slip:
  1. Click **"🔗 Link"**.
  2. Enter the Target Slip ID and enter a mandatory recorded justification.
  3. Both slips are immediately re-consolidated and audited.
- To detach an incorrect page:
  1. Click **"⛓️ Unlink"**.
  2. Enter the reason to spawn a separate standalone record.

### 4.5 Totals & Reconciliation
The reconciliation block verifies:
- `Sum of Party Tally Votes == Total Valid Votes Cast`
- `Total Valid Votes + Total Spoilt Ballots == Total Votes Cast`
- `Total Votes Cast <= Registered Voters (Turnout % check)`

### 4.6 Approving or Rejecting a Result
- **Approve**: Once all pages are present and all validation rules pass, click **"✓ Approve & Certify Result"**. The record transitions to `Approved` with a timestamp and supervisor sign-off.
- **Flag for Review**: Click **"🚩 Flag for Review"** to route the slip to a supervisor.
- **Reject**: Click **"✕ Reject Slip"** and enter the mandatory rejection reason.

---

## 5. Validation Rule Builder

Navigate to the **"⚙️ Validation Rule Builder"** tab:
- Toggle rules on or off with checkboxes.
- Adjust rule severities:
  - **Critical Error**: Blocks operator approval until corrected.
  - **Warning**: Highlights potential issues for supervisor review without blocking.
- Configure tolerance values and turnout ceiling thresholds.

---

## 6. Audit Trail & Verification

- **Per-Slip Audit**: In the dashboard, click the `📜` icon on any row to open the full chronological history of that slip.
- **System-Wide Audit**: Navigate to **"📜 Audit Trail History"** tab to inspect all historical operations across the entire election database.
- **Immutability**: Every database record is append-only. Edits after approval generate secondary audit entries without overwriting original capture data.
