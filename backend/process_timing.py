"""Elapsed / remaining time for live upload and replace progress."""

from __future__ import annotations

import json
import queue
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from fastapi.responses import StreamingResponse

PRIOR_SECONDS_PER_PAGE = 18.0

STAGE_MESSAGE = {
    "started": "Starting",
    "enhancing": "Straightening the photo",
    "reading": "Reading the counts",
    "grouping": "Matching the page to a slip",
    "checking": "Checking totals",
    "page": "Page ready",
    "complete": "Finished",
}

STAGE_PAGE_FRACTION = {
    "started": 0.0,
    "enhancing": 0.12,
    "reading": 0.55,
    "grouping": 0.9,
    "checking": 0.97,
    "page": 0.0,
    "complete": 0.0,
}


def iso_utc(dt: Optional[datetime] = None) -> str:
    stamp = dt or datetime.now(timezone.utc)
    return stamp.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def remaining_seconds(
    elapsed: float,
    done_pages: float,
    total_pages: float,
    page_fraction: float = 0.0,
    prior_per_page: float = PRIOR_SECONDS_PER_PAGE,
) -> float:
    if total_pages <= 0:
        return 0.0
    work_done = max(0.0, float(done_pages) + float(page_fraction))
    if work_done < 0.05:
        return max(0.0, prior_per_page * float(total_pages) - float(elapsed))
    rate = float(elapsed) / work_done
    return max(0.0, rate * (float(total_pages) - work_done))


def percent_complete(done_pages: float, total_pages: float, page_fraction: float = 0.0) -> int:
    if total_pages <= 0:
        return 100
    value = 100.0 * (float(done_pages) + float(page_fraction)) / float(total_pages)
    return int(max(0, min(100, round(value))))


def make_event(
    stage: str,
    *,
    t0: float,
    started_at: str,
    done: float,
    total: float,
    filename: str = "",
    message: Optional[str] = None,
    elapsed: Optional[float] = None,
    **extra,
) -> dict:
    elapsed_s = round(time.time() - t0, 3) if elapsed is None else round(float(elapsed), 3)
    fraction = STAGE_PAGE_FRACTION.get(stage, 0.0)
    remaining = remaining_seconds(elapsed_s, done, total, fraction)
    estimated_end = datetime.now(timezone.utc) + timedelta(seconds=remaining)
    event_name = stage if stage in {"started", "complete", "error"} else "progress"
    payload = {
        "event": event_name,
        "stage": stage,
        "started_at": started_at,
        "elapsed_seconds": elapsed_s,
        "remaining_seconds": round(remaining, 1),
        "estimated_end_at": iso_utc(estimated_end),
        "percent": percent_complete(done, total, fraction),
        "done": int(done),
        "page_count": int(total),
        "filename": filename,
        "message": message or STAGE_MESSAGE.get(stage, "Processing"),
    }
    payload.update(extra)
    return payload


def ndjson_stream(run_fn: Callable[[Callable[[dict], None]], None]) -> StreamingResponse:
    def generate():
        mailbox: queue.Queue = queue.Queue()

        def emit(event: dict) -> None:
            mailbox.put(event)

        def worker() -> None:
            try:
                run_fn(emit)
            except Exception as exc:
                mailbox.put({"event": "error", "detail": str(exc)})
            finally:
                mailbox.put(None)

        threading.Thread(target=worker, daemon=True).start()
        while True:
            item = mailbox.get()
            if item is None:
                break
            yield json.dumps(item, default=str) + "\n"

    return StreamingResponse(
        generate(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
