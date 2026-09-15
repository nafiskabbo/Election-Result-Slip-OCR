"""Score OCR extraction against gold labels for every photo in sample_slips/."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2

from backend.config import ROOT_DIR, SAMPLE_DIR
from backend.image_enhancer import ImageEnhancer
from backend.ocr_engine import OCREngine

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
    for code, expected in (gold.get("votes") or {}).items():
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


def score_folder(
    folder: Path,
    gold: Dict[str, Dict[str, Any]],
    use_known: bool = False,
) -> Dict[str, Any]:
    engine = OCREngine()
    enhancer = ImageEnhancer()
    images = list_sample_images(folder)
    pages: List[Dict[str, Any]] = []
    labeled_ok = labeled_total = 0
    iec_ok = iec_total = 0

    for path in images:
        img = cv2.imread(str(path))
        started = time.time()
        if img is None:
            pages.append({
                "file": path.name,
                "ok": False,
                "seconds": 0.0,
                "error": "could not read image",
                "checks": [],
                "unlabeled": path.name not in gold,
            })
            continue
        enh = enhancer.process_image(img)
        extracted = engine.extract_full_slip_data(
            enh.enhanced_image,
            use_known=use_known,
            binary=enh.binary_image,
        )
        elapsed = round(time.time() - started, 3)
        expected = gold.get(path.name)
        if not expected:
            pages.append({
                "file": path.name,
                "ok": True,
                "seconds": elapsed,
                "unlabeled": True,
                "extracted": {
                    "ballot_type": extracted.get("ballot_type"),
                    "page_number": extracted.get("page_number"),
                    "page_total": extracted.get("page_total"),
                    "voting_district": extracted.get("voting_district"),
                    "barcode_text": extracted.get("barcode_text"),
                    "station_name": extracted.get("station_name"),
                },
                "checks": [],
            })
            continue

        checks = compare_page(extracted, expected)
        hits = sum(1 for _, _, _, ok in checks if ok)
        labeled_ok += hits
        labeled_total += len(checks)
        if expected.get("template") != "worksheet":
            iec_ok += hits
            iec_total += len(checks)
        pages.append({
            "file": path.name,
            "template": expected.get("template", "iec_slip"),
            "ok": True,
            "seconds": elapsed,
            "unlabeled": False,
            "hits": hits,
            "total": len(checks),
            "checks": [
                {"field": field, "actual": actual, "expected": expected_val, "ok": ok}
                for field, actual, expected_val, ok in checks
            ],
        })

    return {
        "images": len(images),
        "labeled": sum(1 for page in pages if not page.get("unlabeled")),
        "unlabeled": sum(1 for page in pages if page.get("unlabeled")),
        "labeled_hits": labeled_ok,
        "labeled_total": labeled_total,
        "iec_hits": iec_ok,
        "iec_total": iec_total,
        "pages": pages,
    }


def _pct(hits: int, total: int) -> Optional[float]:
    if total <= 0:
        return None
    return round(100.0 * hits / total, 1)


def print_report(result: Dict[str, Any], use_known: bool) -> None:
    mode = "with KNOWN_SLIPS lookup" if use_known else "raw OCR (no sample lookup)"
    print(f"Sample-slip accuracy check — {mode}")
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
    if result["unlabeled"]:
        print(f"{result['unlabeled']} photo(s) have no gold labels — extracted identity is listed above.")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Run OCR accuracy checks on sample_slips/")
    parser.add_argument(
        "--with-known",
        action="store_true",
        help="Score the production path including hardcoded KNOWN_SLIPS lookups.",
    )
    parser.add_argument(
        "--fail-under",
        type=float,
        default=None,
        help="Exit 1 if IEC-slip field accuracy is below this percent (e.g. 95).",
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
    result = score_folder(SAMPLE_DIR, gold, use_known=args.with_known)
    print_report(result, use_known=args.with_known)

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
