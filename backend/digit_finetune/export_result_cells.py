"""Export RESULT digit cells from sample slips for manual IEC annotation.

Row totals cannot safely be decomposed into cells because real forms use both
leading slashed-zero and trailing-blank conventions. Cell labels are therefore
accepted only from an explicit ``vote_cells`` map in the gold fixture.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.digit_icr import RESULT_BOXES
from backend.page_pipeline import extract_page_from_file

DEFAULT_OUT = Path(__file__).resolve().parent / "data" / "cells"
GOLD_PATH = ROOT / "tests" / "fixtures" / "sample_gold.json"
SAMPLE_DIR = ROOT / "sample_slips"


def validate_cell_labels(labels: Any) -> Optional[List[Optional[int]]]:
    """Validate one manually annotated four-cell sequence."""
    if not isinstance(labels, list) or len(labels) != RESULT_BOXES:
        return None
    normalized: List[Optional[int]] = []
    for label in labels:
        if label is None:
            normalized.append(None)
        elif isinstance(label, int) and 0 <= label <= 9:
            normalized.append(label)
        else:
            return None
    return normalized


def export_cells(
    sample_dir: Path = SAMPLE_DIR,
    gold_path: Path = GOLD_PATH,
    out_dir: Path = DEFAULT_OUT,
    rapidocr_model: str = "small",
) -> Dict[str, Any]:
    gold = json.loads(gold_path.read_text(encoding="utf-8")) if gold_path.exists() else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: List[Dict[str, Any]] = []

    images = sorted(
        p
        for p in sample_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"} and p.is_file()
    )
    for path in images:
        try:
            enh, extracted = extract_page_from_file(
                str(path),
                rapidocr_model=rapidocr_model,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"skip {path.name}: {exc}")
            continue
        img = enh.enhanced_image
        page_gold = gold.get(path.name) or {}
        gold_votes = page_gold.get("votes") or {}
        vote_cells = page_gold.get("vote_cells") or {}

        for row in extracted.get("party_results") or []:
            code = row.get("party_code") or "UNK"
            bb = row.get("bbox") or {}
            x, y = int(bb.get("x", 0)), int(bb.get("y", 0))
            w, h = int(bb.get("width", 0)), int(bb.get("height", 0))
            if w < 8 or h < 8:
                continue
            row_img = img[y : y + h, x : x + w]
            labels = validate_cell_labels(vote_cells.get(code))
            label_source = "manual_cell" if labels is not None else "unlabeled"
            for c in range(RESULT_BOXES):
                x1 = int(w * c / RESULT_BOXES)
                x2 = int(w * (c + 1) / RESULT_BOXES)
                cell = row_img[:, x1:x2]
                rel = f"{path.stem}__{code}__c{c}.png"
                cv2.imwrite(str(out_dir / rel), cell)
                entry: Dict[str, Any] = {
                    "file": rel,
                    "source_image": path.name,
                    "party_code": code,
                    "cell_index": c,
                    "label_source": label_source,
                    "label": None if labels is None else labels[c],
                    "gold_votes": gold_votes.get(code),
                    "heuristic_votes": row.get("votes"),
                }
                manifest.append(entry)

    man_path = out_dir / "manifest.json"
    payload = {
        "note": (
            "Only labels from explicit gold vote_cells arrays are trainable. "
            "Sparse row totals are never auto-decomposed."
        ),
        "count": len(manifest),
        "cells": manifest,
    }
    man_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    labeled = sum(1 for e in manifest if e["label_source"] == "manual_cell")
    print(f"Wrote {len(manifest)} cells ({labeled} manually labeled) → {out_dir}")
    print(f"Manifest: {man_path}")
    return payload


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sample-dir", type=Path, default=SAMPLE_DIR)
    p.add_argument("--gold", type=Path, default=GOLD_PATH)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--rapidocr-model", default="small", choices=("small", "medium"))
    args = p.parse_args(argv)
    export_cells(args.sample_dir, args.gold, args.out, args.rapidocr_model)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
