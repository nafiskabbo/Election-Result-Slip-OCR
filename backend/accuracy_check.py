"""Score OCR extraction against gold labels for every photo in sample_slips/."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from backend.config import ROOT_DIR, SAMPLE_DIR, STORAGE_DIR
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine
from backend.page_pipeline import extract_page_from_file

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp"}
GOLD_PATH = ROOT_DIR / "tests" / "fixtures" / "sample_gold.json"
CONTAINS_FIELDS = ("barcode_text", "province", "municipality", "station_name", "officer")
EXACT_FIELDS = ("ballot_type", "page_number", "page_total", "voting_district", "registered_voters")
TOTAL_MAP = {
    "valid": "total_valid_votes",
    "spoilt": "total_spoilt_votes",
    "cast": "total_votes_cast",
    "special": "special_votes",
    "s24a": "section_24a_votes",
}
DEFAULT_REPORT_PATH = STORAGE_DIR / "accuracy_report.md"
DEFAULT_TXT_REPORT_PATH = STORAGE_DIR / "accuracy_report.txt"
FOCUS_COMPARE_FILES = ("ResultSlip.jpg", "image1.jpg")
SNAPSHOT_FIELDS = (
    ("ballot_type", "ballot_type"),
    ("page_number", "page_number"),
    ("page_total", "page_total"),
    ("voting_district", "voting_district"),
    ("barcode_text", "barcode_text"),
    ("province", "province"),
    ("municipality", "municipality"),
    ("station_name", "station_name"),
    ("registered_voters", "registered_voters"),
    ("officer", "presiding_officer_name"),
    ("total_valid_votes", "total_valid_votes"),
    ("total_spoilt_votes", "total_spoilt_votes"),
    ("total_votes_cast", "total_votes_cast"),
    ("special_votes", "special_votes"),
    ("section_24a_votes", "section_24a_votes"),
)


def list_sample_images(folder: Path) -> List[Path]:
    files = [
        path for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    ]
    return sorted(files, key=lambda p: p.name.lower())


def load_gold(path: Path) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _contains(actual: Any, expected: Any) -> bool:
    if expected is None or expected == "":
        return True
    return str(expected).upper() in str(actual or "").upper()


def _eq(actual: Any, expected: Any) -> bool:
    if expected is None:
        return True
    return actual == expected


def snapshot_extracted(extracted: Dict[str, Any]) -> Dict[str, Any]:
    """Compact retrieved values for the text report (identity, totals, party votes)."""
    snap: Dict[str, Any] = {}
    for report_key, src_key in SNAPSHOT_FIELDS:
        snap[report_key] = extracted.get(src_key)
    snap["exception_flags"] = list(extracted.get("exception_flags") or [])
    parties: List[Dict[str, Any]] = []
    for row in extracted.get("party_results") or []:
        parties.append({
            "code": row.get("party_code"),
            "name": row.get("party_name"),
            "votes": row.get("votes"),
            "confidence": row.get("confidence_score"),
            "cnn_votes": row.get("cnn_votes"),
            "cnn_confidence": row.get("cnn_confidence"),
        })
    snap["parties"] = parties
    return snap


def compare_page(extracted: Dict[str, Any], gold: Dict[str, Any]) -> List[Tuple[str, Any, Any, bool]]:
    checks: List[Tuple[str, Any, Any, bool]] = []
    for field in CONTAINS_FIELDS:
        if field not in gold:
            continue
        actual = extracted.get(field) if field != "officer" else extracted.get("presiding_officer_name")
        expected = gold[field]
        checks.append((field, actual, expected, _contains(actual, expected)))
    for field in EXACT_FIELDS:
        if field not in gold:
            continue
        checks.append((field, extracted.get(field), gold[field], _eq(extracted.get(field), gold[field])))

    votes_by_code = {row["party_code"]: row["votes"] for row in extracted.get("party_results") or []}
    expected_votes = gold.get("votes") or {}
    # Gold vote maps are sparse: omitted IEC party rows are verified blanks/zeros.
    # Score the union so false-positive votes count as errors.
    vote_codes = sorted(set(votes_by_code) | set(expected_votes))
    for code in vote_codes:
        expected = expected_votes.get(code, 0)
        actual = votes_by_code.get(code)
        checks.append((f"votes.{code}", actual, expected, actual == expected))

    for key, field in TOTAL_MAP.items():
        totals = gold.get("totals") or {}
        if key not in totals:
            continue
        actual = extracted.get(field)
        expected = totals[key]
        checks.append((field, actual, expected, actual == expected))
    return checks


def _desk_path_label(use_known: bool) -> str:
    return "Upload API / raw OCR path (known-slip overrides disabled)"


def _lookup_note(snap: Dict[str, Any], use_known: bool) -> str:
    return "known-slip overrides disabled"


def score_folder(
    folder: Path,
    gold: Dict[str, Dict[str, Any]],
    use_known: bool = False,
    compare_digit_cnn: bool = True,
    rapidocr_model: str = "small",
    digit_backend: str = "heuristic",
) -> Dict[str, Any]:
    engine = OCREngine(rapidocr_model=rapidocr_model)
    enhancer = ImageEnhancer()
    images = list_sample_images(folder)
    pages: List[Dict[str, Any]] = []
    labeled_ok = labeled_total = 0
    iec_ok = iec_total = 0
    heur_vote_ok = heur_vote_total = 0
    nonzero_vote_ok = nonzero_vote_total = 0
    blank_vote_ok = blank_vote_total = 0
    cnn_vote_ok = cnn_vote_total = 0
    backend = (digit_backend or "heuristic").strip().lower()

    for path in images:
        started = time.time()
        try:
            _enh, extracted = extract_page_from_file(
                str(path),
                enhancer=enhancer,
                ocr_engine=engine,
                digit_backend=backend,
                also_cnn_votes=compare_digit_cnn and backend == "heuristic",
                rapidocr_model=rapidocr_model,
            )
        except Exception as exc:
            pages.append({
                "file": path.name,
                "ok": False,
                "seconds": 0.0,
                "error": str(exc),
                "checks": [],
                "unlabeled": path.name not in gold,
            })
            continue
        elapsed = round(time.time() - started, 3)
        snap = snapshot_extracted(extracted)
        expected = gold.get(path.name)
        if not expected:
            pages.append({
                "file": path.name,
                "ok": True,
                "seconds": elapsed,
                "unlabeled": True,
                "extracted": snap,
                "checks": [],
                "vote_compare": [],
            })
            continue

        checks = compare_page(extracted, expected)
        hits = sum(1 for _, _, _, ok in checks if ok)
        labeled_ok += hits
        labeled_total += len(checks)
        if expected.get("template") != "worksheet":
            iec_ok += hits
            iec_total += len(checks)

        vote_compare = _vote_compare_rows(extracted, expected)
        if expected.get("template") != "worksheet":
            for row in vote_compare:
                heur_vote_total += 1
                if row["heuristic_ok"]:
                    heur_vote_ok += 1
                if row["expected"] == 0:
                    blank_vote_total += 1
                    if row["heuristic_ok"]:
                        blank_vote_ok += 1
                else:
                    nonzero_vote_total += 1
                    if row["heuristic_ok"]:
                        nonzero_vote_ok += 1
                if compare_digit_cnn:
                    cnn_vote_total += 1
                    if row["cnn_ok"]:
                        cnn_vote_ok += 1

        pages.append({
            "file": path.name,
            "template": expected.get("template", "iec_slip"),
            "ok": True,
            "seconds": elapsed,
            "unlabeled": False,
            "extracted": snap,
            "hits": hits,
            "total": len(checks),
            "checks": [
                {"field": field, "actual": actual, "expected": expected_val, "ok": ok}
                for field, actual, expected_val, ok in checks
            ],
            "vote_compare": vote_compare,
        })

    return {
        "images": len(images),
        "labeled": sum(1 for page in pages if not page.get("unlabeled")),
        "unlabeled": sum(1 for page in pages if page.get("unlabeled")),
        "labeled_hits": labeled_ok,
        "labeled_total": labeled_total,
        "iec_hits": iec_ok,
        "iec_total": iec_total,
        "heuristic_vote_hits": heur_vote_ok,
        "heuristic_vote_total": heur_vote_total,
        "nonzero_vote_hits": nonzero_vote_ok,
        "nonzero_vote_total": nonzero_vote_total,
        "blank_vote_hits": blank_vote_ok,
        "blank_vote_total": blank_vote_total,
        "cnn_vote_hits": cnn_vote_ok,
        "cnn_vote_total": cnn_vote_total,
        "rapidocr_model": rapidocr_model,
        "digit_backend": backend,
        "pages": pages,
    }


def _vote_compare_rows(extracted: Dict[str, Any], gold: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-party expected vs heuristic ICR vs digit CNN."""
    by_code = {
        row["party_code"]: row for row in (extracted.get("party_results") or [])
    }
    rows: List[Dict[str, Any]] = []
    expected_votes = gold.get("votes") or {}
    for code in sorted(set(by_code) | set(expected_votes)):
        expected = expected_votes.get(code, 0)
        party = by_code.get(code) or {}
        heur = party.get("votes")
        cnn = party.get("cnn_votes")
        rows.append({
            "code": code,
            "expected": expected,
            "heuristic": heur,
            "cnn_votes": cnn,
            "heuristic_ok": heur == expected,
            "cnn_ok": cnn == expected if cnn is not None else False,
            "heuristic_conf": party.get("confidence_score"),
            "cnn_conf": party.get("cnn_confidence"),
        })
    return rows


def _pct(hits: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return round(100.0 * hits / total, 1)


def print_report(result: Dict[str, Any], use_known: bool) -> None:
    model = result.get("rapidocr_model") or "small"
    print(f"Sample-slip accuracy check — {_desk_path_label(use_known)}")
    print(f"RapidOCR PP-OCRv6 model: {model}")
    print(f"Folder: {SAMPLE_DIR}")
    print(f"Images: {result['images']}  labeled: {result['labeled']}  unlabeled: {result['unlabeled']}")
    print()
    for page in result["pages"]:
        seconds = page.get("seconds", 0)
        if page.get("error"):
            print(f"  FAIL  {page['file']}  ({page['error']})")
            continue
        if page.get("unlabeled"):
            extracted = page.get("extracted") or {}
            print(
                f"  ----  {page['file']}  {seconds:.2f}s  unlabeled  "
                f"{extracted.get('ballot_type')} p{extracted.get('page_number')}/"
                f"{extracted.get('page_total')}  VD {extracted.get('voting_district')}"
            )
            continue
        hits = page.get("hits", 0)
        total = page.get("total", 0)
        mark = "PASS" if hits == total else "MISS"
        print(f"  {mark}  {page['file']}  {seconds:.2f}s  {hits}/{total} fields")
        for check in page.get("checks") or []:
            if check["ok"]:
                continue
            print(f"        {check['field']}: got {check['actual']!r}, expected {check['expected']!r}")

    iec_pct = _pct(result["iec_hits"], result["iec_total"])
    all_pct = _pct(result["labeled_hits"], result["labeled_total"])
    print()
    if iec_pct is not None:
        print(f"IEC result slips: {result['iec_hits']}/{result['iec_total']} fields  ({iec_pct}%)")
    if all_pct is not None:
        print(f"All labeled files: {result['labeled_hits']}/{result['labeled_total']} fields  ({all_pct}%)")
    if result.get("heuristic_vote_total"):
        print(
            f"Party rows: {result.get('heuristic_vote_hits', 0)}/"
            f"{result['heuristic_vote_total']} exact  "
            f"(non-zero {result.get('nonzero_vote_hits', 0)}/"
            f"{result.get('nonzero_vote_total', 0)}, blank {result.get('blank_vote_hits', 0)}/"
            f"{result.get('blank_vote_total', 0)})"
        )
    if result["unlabeled"]:
        print(f"{result['unlabeled']} photo(s) have no gold labels — retrieved values are in the .md report.")


def _show(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value)


def _extra_nonzero_votes(page: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Non-zero retrieved parties that gold did not list (possible false positives)."""
    gold_codes = {
        check["field"].split(".", 1)[1]
        for check in page.get("checks") or []
        if check["field"].startswith("votes.")
    }
    extras: List[Dict[str, Any]] = []
    for party in (page.get("extracted") or {}).get("parties") or []:
        votes = party.get("votes") or 0
        code = party.get("code")
        if votes and code not in gold_codes:
            extras.append(party)
    return extras


def _append_all_retrieved_votes(lines: List[str], page: Dict[str, Any]) -> None:
    parties = (page.get("extracted") or {}).get("parties") or []
    if not parties:
        lines.append("retrieved votes: (none)")
        return
    nonzero = [p for p in parties if p.get("votes")]
    zero_n = len(parties) - len(nonzero)
    lines.append("")
    lines.append("Retrieved party votes:")
    if nonzero:
        for party in nonzero:
            conf = party.get("confidence")
            conf_s = f"  conf {conf:.2f}" if isinstance(conf, (int, float)) else ""
            lines.append(
                f"  {str(party.get('code') or ''):<12} {party.get('votes')}{conf_s}  "
                f"{party.get('name') or ''}"
            )
    else:
        lines.append("  (all zero)")
    if zero_n:
        lines.append(f"  ({zero_n} other part{'y' if zero_n == 1 else 'ies'} retrieved as 0)")


def _append_unlabeled_block(
    lines: List[str],
    page: Dict[str, Any],
    heading: bool = True,
    use_known: bool = True,
) -> None:
    snap = page.get("extracted") or {}
    if heading:
        seconds = page.get("seconds", 0)
        lines.append("")
        lines.append(f"{page['file']}  {seconds:.2f}s")
    lines.append(_lookup_note(snap, use_known))
    lines.append(f"{'field':<28} retrieved")
    for key, _src in SNAPSHOT_FIELDS:
        lines.append(f"{key:<28} {_show(snap.get(key))}")
    flags = snap.get("exception_flags") or []
    if flags:
        lines.append(f"{'exception_flags':<28} {', '.join(flags)}")
    _append_all_retrieved_votes(lines, page)


def format_report_text(result: Dict[str, Any], use_known: bool) -> str:
    """Full got-vs-expected dump, including unlabeled retrieved votes."""
    lines: List[str] = []
    lines.append("Sample-slip accuracy report")
    lines.append(f"Generated (UTC): {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"Path: {_desk_path_label(use_known)}")
    lines.append(f"Folder: {SAMPLE_DIR}")
    lines.append(f"Gold: {GOLD_PATH}")
    lines.append("")
    lines.append("=== SUMMARY ===")
    lines.append(
        f"Images: {result['images']}  labeled: {result['labeled']}  unlabeled: {result['unlabeled']}"
    )
    iec_pct = _pct(result["iec_hits"], result["iec_total"])
    all_pct = _pct(result["labeled_hits"], result["labeled_total"])
    if iec_pct is not None:
        lines.append(f"IEC result slips: {result['iec_hits']}/{result['iec_total']} fields  ({iec_pct}%)")
    if all_pct is not None:
        lines.append(f"All labeled files: {result['labeled_hits']}/{result['labeled_total']} fields  ({all_pct}%)")
    miss_count = sum(
        1
        for page in result["pages"]
        for check in page.get("checks") or []
        if not check["ok"]
    )
    extra_count = sum(
        len(_extra_nonzero_votes(page))
        for page in result["pages"]
        if not page.get("unlabeled")
    )
    lines.append(f"Misses (gold fields): {miss_count}")
    lines.append(f"Extra non-zero votes not in gold: {extra_count}")
    lines.append("")

    lines.append("=== MISSES (quick compare) ===")
    any_miss = False
    for page in result["pages"]:
        if page.get("error"):
            lines.append(f"{page['file']}: FAIL  {page['error']}")
            any_miss = True
            continue
        if page.get("unlabeled"):
            continue
        for check in page.get("checks") or []:
            if check["ok"]:
                continue
            any_miss = True
            lines.append(
                f"{page['file']}  {check['field']}: got {_show(check['actual'])}  "
                f"expected {_show(check['expected'])}"
            )
        for party in _extra_nonzero_votes(page):
            any_miss = True
            lines.append(
                f"{page['file']}  votes.{party['code']}: got {party['votes']}  "
                f"expected 0 (not in gold)  EXTRA"
            )
    if not any_miss:
        lines.append("(none)")
    lines.append("")

    unlabeled = [page for page in result["pages"] if page.get("unlabeled") and not page.get("error")]
    if unlabeled:
        lines.append("=== UNLABELED — retrieved values (no gold to score) ===")
        for page in unlabeled:
            _append_unlabeled_block(lines, page, use_known=use_known)
        lines.append("")

    lines.append("=== PER FILE ===")
    for page in result["pages"]:
        lines.append("")
        lines.append("=" * 72)
        if page.get("error"):
            lines.append(f"{page['file']}  FAIL  {page['error']}")
            continue
        seconds = page.get("seconds", 0)
        if page.get("unlabeled"):
            lines.append(f"{page['file']}  unlabeled  {seconds:.2f}s")
            _append_unlabeled_block(lines, page, heading=False, use_known=use_known)
            continue
        hits = page.get("hits", 0)
        total = page.get("total", 0)
        mark = "PASS" if hits == total else "MISS"
        lines.append(f"{page['file']}  {mark}  {seconds:.2f}s  {hits}/{total} gold fields")
        lines.append(_lookup_note(page.get("extracted") or {}, use_known))
        lines.append("-" * 72)
        lines.append(f"{'field':<28} {'got':<22} {'expected':<22} status")
        for check in page.get("checks") or []:
            status = "OK" if check["ok"] else "MISS"
            lines.append(
                f"{check['field']:<28} {_show(check['actual']):<22} "
                f"{_show(check['expected']):<22} {status}"
            )
        extras = _extra_nonzero_votes(page)
        if extras:
            lines.append("")
            lines.append("Extra non-zero votes not listed in gold:")
            for party in extras:
                conf = party.get("confidence")
                conf_s = f"  conf {conf:.2f}" if isinstance(conf, (int, float)) else ""
                lines.append(
                    f"  {party.get('code')}  {party.get('name')}  got {party.get('votes')}{conf_s}  EXTRA"
                )
        _append_all_retrieved_votes(lines, page)
        flags = (page.get("extracted") or {}).get("exception_flags") or []
        if flags:
            lines.append(f"exception_flags: {', '.join(flags)}")

    lines.append("")
    return "\n".join(lines) + "\n"


def format_report_markdown(result: Dict[str, Any], use_known: bool) -> str:
    """Markdown report with summary tables and heuristic vs digit-CNN vote compare."""
    from backend.digit_cnn import active_model_name, load_error, model_available

    lines: List[str] = []
    lines.append("# Sample-slip accuracy report")
    lines.append("")
    lines.append(f"- **Generated (UTC):** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Path:** {_desk_path_label(use_known)}")
    lines.append(f"- **RapidOCR:** PP-OCRv6 **{result.get('rapidocr_model') or 'small'}** (det+rec)")
    lines.append(f"- **Folder:** `{SAMPLE_DIR}`")
    lines.append(f"- **Gold:** `{GOLD_PATH}`")
    lines.append(
        f"- **Digit CNN model:** `{active_model_name() or 'none'}` "
        f"({'loaded' if model_available() else 'missing'}; {load_error() or 'ok'})"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(
        f"| Images | {result['images']} (labeled {result['labeled']}, "
        f"unlabeled {result['unlabeled']}) |"
    )
    iec_pct = _pct(result["iec_hits"], result["iec_total"])
    all_pct = _pct(result["labeled_hits"], result["labeled_total"])
    if iec_pct is not None:
        lines.append(
            f"| IEC fields | {result['iec_hits']}/{result['iec_total']} ({iec_pct}%) |"
        )
    if all_pct is not None:
        lines.append(
            f"| All labeled fields | {result['labeled_hits']}/{result['labeled_total']} ({all_pct}%) |"
        )

    hv = result.get("heuristic_vote_total") or 0
    cv = result.get("cnn_vote_total") or 0
    if hv:
        hp = _pct(result.get("heuristic_vote_hits", 0), hv)
        lines.append(
            f"| Party votes — heuristic ICR (+ RapidOCR fallback) | "
            f"{result.get('heuristic_vote_hits', 0)}/{hv} ({hp}%) |"
        )
        nz_total = result.get("nonzero_vote_total") or 0
        blank_total = result.get("blank_vote_total") or 0
        if nz_total:
            lines.append(
                f"| Non-zero party votes | {result.get('nonzero_vote_hits', 0)}/"
                f"{nz_total} ({_pct(result.get('nonzero_vote_hits', 0), nz_total)}%) |"
            )
        if blank_total:
            lines.append(
                f"| Blank/zero party rows | {result.get('blank_vote_hits', 0)}/"
                f"{blank_total} ({_pct(result.get('blank_vote_hits', 0), blank_total)}%) |"
            )
    if cv:
        cp = _pct(result.get("cnn_vote_hits", 0), cv)
        lines.append(
            f"| Party votes — handwritten digit CNN | "
            f"{result.get('cnn_vote_hits', 0)}/{cv} ({cp}%) |"
        )
        winner = "tie"
        if (result.get("cnn_vote_hits") or 0) > (result.get("heuristic_vote_hits") or 0):
            winner = "digit CNN"
        elif (result.get("heuristic_vote_hits") or 0) > (result.get("cnn_vote_hits") or 0):
            winner = "heuristic / RapidOCR path"
        lines.append(f"| Vote-accuracy winner (this run) | **{winner}** |")
    else:
        lines.append(
            "| Digit CNN compare | skipped (pass `--compare-digit-cnn`) |"
        )
    lines.append("")

    lines.append("## Focus slips (ResultSlip / image1)")
    lines.append("")
    lines.append(
        "Gold votes on these photos (from the handwritten RESULT boxes): "
        "**ANC=9, DA=18, EFF=6, M.K.=1, ACTIONSA=18**. "
        "SUN and VF PLUS rows are blank on the slip; the `1` and `18` sit on "
        "**M.K.** and **ACTIONSA**."
    )
    lines.append("")

    focus_pages = [
        p for p in result["pages"]
        if p.get("file") in FOCUS_COMPARE_FILES and not p.get("error")
    ]
    if not focus_pages:
        lines.append("_No focus slips scored in this run._")
        lines.append("")
    for page in focus_pages:
        lines.append(f"### `{page['file']}`")
        lines.append("")
        snap = page.get("extracted") or {}
        lines.append("| Field | Retrieved |")
        lines.append("| --- | --- |")
        for key, _src in SNAPSHOT_FIELDS:
            if key.startswith("total_") or key in (
                "special_votes", "section_24a_votes", "officer"
            ):
                continue
            lines.append(f"| {key} | {_show(snap.get(key))} |")
        lines.append("")
        compare = page.get("vote_compare") or []
        if compare:
            lines.append(
                "| Party | Expected | Heuristic ICR | Digit CNN | Heuristic | CNN |"
            )
            lines.append("| --- | ---: | ---: | ---: | --- | --- |")
            for row in compare:
                lines.append(
                    f"| {row['code']} | {row['expected']} | "
                    f"{_show(row['heuristic'])} | {_show(row['cnn_votes'])} | "
                    f"{'OK' if row['heuristic_ok'] else 'MISS'} | "
                    f"{'OK' if row['cnn_ok'] else 'MISS'} |"
                )
            lines.append("")
        else:
            lines.append("_No gold party votes for this file._")
            lines.append("")

    lines.append("## Heuristic vs digit CNN (all labeled party votes)")
    lines.append("")
    lines.append(
        "| File | Party | Expected | Heuristic ICR | Digit CNN | Better |"
    )
    lines.append("| --- | --- | ---: | ---: | ---: | --- |")
    any_row = False
    for page in result["pages"]:
        for row in page.get("vote_compare") or []:
            any_row = True
            better = "—"
            if row["heuristic_ok"] and row["cnn_ok"]:
                better = "both"
            elif row["heuristic_ok"]:
                better = "heuristic"
            elif row["cnn_ok"]:
                better = "digit CNN"
            else:
                better = "neither"
            lines.append(
                f"| `{page['file']}` | {row['code']} | {row['expected']} | "
                f"{_show(row['heuristic'])} | {_show(row['cnn_votes'])} | {better} |"
            )
    if not any_row:
        lines.append("| — | — | — | — | — | no gold votes |")
    lines.append("")

    lines.append("## Misses (gold fields)")
    lines.append("")
    lines.append("| File | Field | Got | Expected |")
    lines.append("| --- | --- | --- | --- |")
    any_miss = False
    for page in result["pages"]:
        if page.get("error"):
            lines.append(
                f"| `{page['file']}` | ERROR | {page['error']} | — |"
            )
            any_miss = True
            continue
        for check in page.get("checks") or []:
            if check["ok"]:
                continue
            any_miss = True
            lines.append(
                f"| `{page['file']}` | {check['field']} | "
                f"{_show(check['actual'])} | {_show(check['expected'])} |"
            )
    if not any_miss:
        lines.append("| — | — | — | none |")
    lines.append("")

    lines.append("## Per-file field checks")
    lines.append("")
    for page in result["pages"]:
        if page.get("error"):
            lines.append(f"### `{page['file']}` — FAIL")
            lines.append("")
            lines.append(page["error"])
            lines.append("")
            continue
        seconds = page.get("seconds", 0)
        if page.get("unlabeled"):
            lines.append(f"### `{page['file']}` — unlabeled ({seconds:.2f}s)")
            lines.append("")
            snap = page.get("extracted") or {}
            lines.append("| Field | Retrieved |")
            lines.append("| --- | --- |")
            for key, _src in SNAPSHOT_FIELDS:
                lines.append(f"| {key} | {_show(snap.get(key))} |")
            nonzero = [p for p in (snap.get("parties") or []) if p.get("votes")]
            if nonzero:
                lines.append("")
                lines.append("| Party | Votes | Conf |")
                lines.append("| --- | ---: | ---: |")
                for party in nonzero:
                    conf = party.get("confidence")
                    conf_s = f"{conf:.2f}" if isinstance(conf, (int, float)) else "—"
                    lines.append(
                        f"| {party.get('code')} | {party.get('votes')} | {conf_s} |"
                    )
            lines.append("")
            continue

        hits = page.get("hits", 0)
        total = page.get("total", 0)
        mark = "PASS" if hits == total else "MISS"
        lines.append(
            f"### `{page['file']}` — {mark} ({seconds:.2f}s, {hits}/{total})"
        )
        lines.append("")
        lines.append(f"_{_lookup_note(page.get('extracted') or {}, use_known)}_")
        lines.append("")
        lines.append("| Field | Got | Expected | Status |")
        lines.append("| --- | --- | --- | --- |")
        for check in page.get("checks") or []:
            status = "OK" if check["ok"] else "MISS"
            lines.append(
                f"| {check['field']} | {_show(check['actual'])} | "
                f"{_show(check['expected'])} | {status} |"
            )
        lines.append("")

    return "\n".join(lines) + "\n"


def format_vote_path_compare_markdown(
    hybrid: Dict[str, Any],
    rapid_only: Dict[str, Any],
    use_known: bool,
) -> str:
    """Side-by-side RapidOCR+custom ICR vs RapidOCR-only vote accuracy."""
    lines: List[str] = []
    lines.append("# Vote path compare: RapidOCR + custom ICR vs RapidOCR only")
    lines.append("")
    lines.append(f"- **Generated (UTC):** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Path:** {_desk_path_label(use_known)}")
    lines.append(f"- **RapidOCR:** PP-OCRv6 **{hybrid.get('rapidocr_model') or 'small'}**")
    lines.append(f"- **Folder:** `{SAMPLE_DIR}`")
    lines.append(f"- **Gold:** `{GOLD_PATH}`")
    lines.append(
        "- **Hybrid:** heuristic ICR + digit-tuned RapidOCR RESULT-box fusion "
        "(production desk path)"
    )
    lines.append(
        "- **Rapid only:** RESULT votes from RapidOCR alone (no topology ICR)"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Hybrid (Rapid + custom) | Rapid only | Δ (hybrid − rapid) |")
    lines.append("| --- | --- | --- | --- |")

    def row(label: str, h_hits: int, h_total: int, r_hits: int, r_total: int) -> None:
        hp = _pct(h_hits, h_total)
        rp = _pct(r_hits, r_total)
        h_txt = f"{h_hits}/{h_total}" + (f" ({hp}%)" if hp is not None else "")
        r_txt = f"{r_hits}/{r_total}" + (f" ({rp}%)" if rp is not None else "")
        delta = "—"
        if h_total and r_total and hp is not None and rp is not None:
            delta = f"{hp - rp:+.1f} pp"
        lines.append(f"| {label} | {h_txt} | {r_txt} | {delta} |")

    row("IEC fields", hybrid["iec_hits"], hybrid["iec_total"], rapid_only["iec_hits"], rapid_only["iec_total"])
    row(
        "All labeled fields",
        hybrid["labeled_hits"],
        hybrid["labeled_total"],
        rapid_only["labeled_hits"],
        rapid_only["labeled_total"],
    )
    row(
        "Party votes",
        hybrid.get("heuristic_vote_hits", 0),
        hybrid.get("heuristic_vote_total", 0),
        rapid_only.get("heuristic_vote_hits", 0),
        rapid_only.get("heuristic_vote_total", 0),
    )
    row(
        "Non-zero party votes",
        hybrid.get("nonzero_vote_hits", 0),
        hybrid.get("nonzero_vote_total", 0),
        rapid_only.get("nonzero_vote_hits", 0),
        rapid_only.get("nonzero_vote_total", 0),
    )
    row(
        "Blank/zero party rows",
        hybrid.get("blank_vote_hits", 0),
        hybrid.get("blank_vote_total", 0),
        rapid_only.get("blank_vote_hits", 0),
        rapid_only.get("blank_vote_total", 0),
    )

    h_votes = _pct(hybrid.get("heuristic_vote_hits", 0), hybrid.get("heuristic_vote_total") or 0) or 0
    r_votes = _pct(rapid_only.get("heuristic_vote_hits", 0), rapid_only.get("heuristic_vote_total") or 0) or 0
    h_iec = _pct(hybrid["iec_hits"], hybrid["iec_total"]) or 0
    r_iec = _pct(rapid_only["iec_hits"], rapid_only["iec_total"]) or 0
    if h_votes > r_votes or (h_votes == r_votes and h_iec >= r_iec):
        winner = "hybrid (RapidOCR + custom ICR)"
        recommend = "Keep hybrid as the production desk path."
    else:
        winner = "RapidOCR only"
        recommend = "Consider switching production digit_backend to rapid."
    lines.append("")
    lines.append(f"**Winner:** {winner}")
    lines.append("")
    lines.append(f"**Recommendation:** {recommend}")
    lines.append("")

    focus = [
        "ResultSlip.jpg",
        "image1.jpg",
        "Result_Slip_2024_Previous_Election_Sample.jpg",
    ]
    hybrid_by = {p["file"]: p for p in hybrid["pages"]}
    rapid_by = {p["file"]: p for p in rapid_only["pages"]}
    lines.append("## Focus slips — party votes")
    lines.append("")
    for name in focus:
        hp = hybrid_by.get(name)
        rp = rapid_by.get(name)
        if not hp and not rp:
            continue
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("| Party | Expected | Hybrid | Rapid only | Hybrid | Rapid |")
        lines.append("| --- | ---: | ---: | ---: | --- | --- |")
        codes = [
            r["code"]
            for r in ((rp or hp or {}).get("vote_compare") or (hp or {}).get("vote_compare") or [])
        ]
        h_votes_map = {r["code"]: r for r in ((hp or {}).get("vote_compare") or [])}
        r_votes_map = {r["code"]: r for r in ((rp or {}).get("vote_compare") or [])}
        for code in codes:
            hrow = h_votes_map.get(code) or {}
            rrow = r_votes_map.get(code) or {}
            expected = hrow.get("expected", rrow.get("expected"))
            lines.append(
                f"| {code} | {expected} | {_show(hrow.get('heuristic'))} | "
                f"{_show(rrow.get('heuristic'))} | "
                f"{'OK' if hrow.get('heuristic_ok') else 'MISS'} | "
                f"{'OK' if rrow.get('heuristic_ok') else 'MISS'} |"
            )
        lines.append("")

    lines.append("## Per-file field hits")
    lines.append("")
    lines.append("| File | Hybrid | Rapid only | Better |")
    lines.append("| --- | --- | --- | --- |")
    files = sorted({p["file"] for p in hybrid["pages"] + rapid_only["pages"]})
    for name in files:
        hp = hybrid_by.get(name) or {}
        rp = rapid_by.get(name) or {}
        if hp.get("unlabeled") and rp.get("unlabeled"):
            continue
        h_txt = f"{hp.get('hits', 0)}/{hp.get('total', 0)}" if not hp.get("unlabeled") else "—"
        r_txt = f"{rp.get('hits', 0)}/{rp.get('total', 0)}" if not rp.get("unlabeled") else "—"
        better = "—"
        if not hp.get("unlabeled") and not rp.get("unlabeled"):
            ht, rt = hp.get("hits", 0), rp.get("hits", 0)
            if ht > rt:
                better = "hybrid"
            elif rt > ht:
                better = "rapid"
            else:
                better = "tie"
        lines.append(f"| `{name}` | {h_txt} | {r_txt} | {better} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def format_model_compare_markdown(
    small: Dict[str, Any],
    medium: Dict[str, Any],
    use_known: bool,
) -> str:
    """Side-by-side PP-OCRv6 small vs medium raw-OCR accuracy."""
    lines: List[str] = []
    lines.append("# RapidOCR PP-OCRv6 small vs medium (raw OCR)")
    lines.append("")
    lines.append(f"- **Generated (UTC):** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **Path:** {_desk_path_label(use_known)}")
    lines.append(f"- **Folder:** `{SAMPLE_DIR}`")
    lines.append(f"- **Gold:** `{GOLD_PATH}`")
    lines.append("- **Digit CNN:** not used")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Small | Medium | Δ (medium − small) |")
    lines.append("| --- | --- | --- | --- |")

    def row(label: str, s_hits: int, s_total: int, m_hits: int, m_total: int) -> None:
        sp = _pct(s_hits, s_total)
        mp = _pct(m_hits, m_total)
        s_txt = f"{s_hits}/{s_total}" + (f" ({sp}%)" if sp is not None else "")
        m_txt = f"{m_hits}/{m_total}" + (f" ({mp}%)" if mp is not None else "")
        delta = "—"
        if s_total and m_total and sp is not None and mp is not None:
            delta = f"{mp - sp:+.1f} pp"
        lines.append(f"| {label} | {s_txt} | {m_txt} | {delta} |")

    row("IEC fields", small["iec_hits"], small["iec_total"], medium["iec_hits"], medium["iec_total"])
    row(
        "All labeled fields",
        small["labeled_hits"],
        small["labeled_total"],
        medium["labeled_hits"],
        medium["labeled_total"],
    )
    row(
        "Party votes (heuristic ICR + RapidOCR fallback)",
        small.get("heuristic_vote_hits", 0),
        small.get("heuristic_vote_total", 0),
        medium.get("heuristic_vote_hits", 0),
        medium.get("heuristic_vote_total", 0),
    )
    lines.append("")

    # Winner
    s_iec = _pct(small["iec_hits"], small["iec_total"]) or 0
    m_iec = _pct(medium["iec_hits"], medium["iec_total"]) or 0
    if m_iec > s_iec:
        winner = "medium"
    elif s_iec > m_iec:
        winner = "small"
    else:
        winner = "tie"
    lines.append(f"**IEC field winner:** {winner}")
    lines.append("")

    lines.append("## Focus slips — party votes")
    lines.append("")
    lines.append(
        "Gold: **ANC=9, DA=18, EFF=6, M.K.=1, ACTIONSA=18** "
        "(SUN / VF PLUS rows are blank on the photos)."
    )
    lines.append("")

    small_by_file = {p["file"]: p for p in small["pages"]}
    medium_by_file = {p["file"]: p for p in medium["pages"]}
    for name in FOCUS_COMPARE_FILES:
        sp = small_by_file.get(name)
        mp = medium_by_file.get(name)
        if not sp or not mp or sp.get("error") or mp.get("error"):
            continue
        lines.append(f"### `{name}`")
        lines.append("")
        lines.append("| Party | Expected | Small | Medium | Small | Medium |")
        lines.append("| --- | ---: | ---: | ---: | --- | --- |")
        # Prefer medium vote_compare as source of expected codes
        codes = [r["code"] for r in (mp.get("vote_compare") or sp.get("vote_compare") or [])]
        small_votes = {r["code"]: r for r in (sp.get("vote_compare") or [])}
        medium_votes = {r["code"]: r for r in (mp.get("vote_compare") or [])}
        for code in codes:
            srow = small_votes.get(code) or {}
            mrow = medium_votes.get(code) or {}
            expected = mrow.get("expected", srow.get("expected"))
            lines.append(
                f"| {code} | {expected} | {_show(srow.get('heuristic'))} | "
                f"{_show(mrow.get('heuristic'))} | "
                f"{'OK' if srow.get('heuristic_ok') else 'MISS'} | "
                f"{'OK' if mrow.get('heuristic_ok') else 'MISS'} |"
            )
        lines.append("")

    lines.append("## Per-file field hits")
    lines.append("")
    lines.append("| File | Small | Medium | Better |")
    lines.append("| --- | --- | --- | --- |")
    files = sorted({p["file"] for p in small["pages"] + medium["pages"]})
    for name in files:
        sp = small_by_file.get(name) or {}
        mp = medium_by_file.get(name) or {}
        if sp.get("unlabeled") and mp.get("unlabeled"):
            continue
        if sp.get("error") or mp.get("error"):
            lines.append(f"| `{name}` | error | error | — |")
            continue
        sh, st = sp.get("hits", 0), sp.get("total", 0)
        mh, mt = mp.get("hits", 0), mp.get("total", 0)
        if not st and not mt:
            continue
        better = "tie"
        if mh > sh:
            better = "medium"
        elif sh > mh:
            better = "small"
        lines.append(f"| `{name}` | {sh}/{st} | {mh}/{mt} | {better} |")
    lines.append("")
    return "\n".join(lines) + "\n"


def write_report(result: Dict[str, Any], use_known: bool, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() == ".md":
        path.write_text(format_report_markdown(result, use_known), encoding="utf-8")
    else:
        path.write_text(format_report_text(result, use_known), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run OCR accuracy checks on sample_slips/")
    parser.add_argument(
        "--raw-ocr",
        action="store_true",
        help="Deprecated no-op: raw OCR is always used.",
    )
    parser.add_argument(
        "--rapidocr-model",
        choices=("small", "medium", "both"),
        default="small",
        help="PP-OCRv6 det+rec size. 'both' writes a small-vs-medium compare report.",
    )
    parser.add_argument(
        "--compare-digit-cnn",
        action="store_true",
        help="Also score the experimental MNIST/EMNIST digit CNN vs gold votes.",
    )
    parser.add_argument(
        "--compare-vote-path",
        action="store_true",
        help=(
            "Compare hybrid (RapidOCR + custom ICR) vs pure RapidOCR votes "
            "and write a Markdown report."
        ),
    )
    parser.add_argument(
        "--digit-backend",
        choices=("heuristic", "rapid", "cnn"),
        default="heuristic",
        help="RESULT digit path: heuristic (hybrid), rapid (RapidOCR only), or cnn.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit 1 if IEC-slip field accuracy is below this percent (e.g. 95).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help=f"Write report (.md tables by default, or .txt) (default: {DEFAULT_REPORT_PATH}).",
    )
    args = parser.parse_args(argv)

    if not SAMPLE_DIR.exists():
        print(f"No sample folder at {SAMPLE_DIR}", file=sys.stderr)
        return 1
    images = list_sample_images(SAMPLE_DIR)
    if not images:
        print(f"No photos found in {SAMPLE_DIR}", file=sys.stderr)
        return 1

    gold = load_gold(GOLD_PATH)
    use_known = False
    compare_cnn = bool(args.compare_digit_cnn)

    if args.compare_vote_path:
        model = args.rapidocr_model if args.rapidocr_model != "both" else "small"
        print("=== Hybrid: RapidOCR + custom ICR ===")
        hybrid = score_folder(
            SAMPLE_DIR,
            gold,
            use_known=False,
            compare_digit_cnn=False,
            rapidocr_model=model,
            digit_backend="heuristic",
        )
        print_report(hybrid, use_known=False)
        print("\n=== RapidOCR only (no ICR) ===")
        rapid_only = score_folder(
            SAMPLE_DIR,
            gold,
            use_known=False,
            compare_digit_cnn=False,
            rapidocr_model=model,
            digit_backend="rapid",
        )
        print_report(rapid_only, use_known=False)
        out = args.out
        if out.suffix.lower() != ".md":
            out = out.with_suffix(".md")
        # Default a clear compare filename when using the stock report path.
        if out.name == DEFAULT_REPORT_PATH.name:
            out = out.with_name("accuracy_vote_path_compare.md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            format_vote_path_compare_markdown(hybrid, rapid_only, use_known=False),
            encoding="utf-8",
        )
        print(f"\nWrote {out}")
        result = hybrid
    elif args.rapidocr_model == "both":
        print("=== RapidOCR PP-OCRv6 SMALL ===")
        small = score_folder(
            SAMPLE_DIR,
            gold,
            use_known=use_known,
            compare_digit_cnn=False,
            rapidocr_model="small",
        )
        print_report(small, use_known=use_known)
        print("\n=== RapidOCR PP-OCRv6 MEDIUM ===")
        medium = score_folder(
            SAMPLE_DIR,
            gold,
            use_known=use_known,
            compare_digit_cnn=False,
            rapidocr_model="medium",
        )
        print_report(medium, use_known=use_known)
        out = args.out
        if out.suffix.lower() != ".md":
            out = out.with_suffix(".md")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(format_model_compare_markdown(small, medium, use_known), encoding="utf-8")
        # Also keep the medium full report beside it for detail.
        detail = out.with_name(out.stem + "_medium_detail.md")
        write_report(medium, use_known, detail)
        print(f"\nWrote {out}")
        print(f"Wrote {detail}")
        result = medium
    else:
        result = score_folder(
            SAMPLE_DIR,
            gold,
            use_known=use_known,
            compare_digit_cnn=compare_cnn,
            rapidocr_model=args.rapidocr_model,
            digit_backend=args.digit_backend,
        )
        print_report(result, use_known=use_known)
        if compare_cnn and result.get("cnn_vote_total"):
            print(
                f"Vote compare: heuristic "
                f"{result.get('heuristic_vote_hits', 0)}/{result.get('heuristic_vote_total', 0)}  "
                f"digit-CNN {result.get('cnn_vote_hits', 0)}/{result.get('cnn_vote_total', 0)}"
            )
        report_path = write_report(result, use_known, args.out)
        print(f"\nWrote {report_path}")

    if any(page.get("error") for page in result["pages"]):
        return 1
    if args.fail_under is not None and result["iec_total"]:
        pct = 100.0 * result["iec_hits"] / result["iec_total"]
        if pct < args.fail_under:
            print(f"\nBelow threshold: IEC accuracy {pct:.1f}% < {args.fail_under:g}%")
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
