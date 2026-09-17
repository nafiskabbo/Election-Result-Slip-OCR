import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.process_timing import make_event, ndjson_stream, percent_complete, remaining_seconds


def test_remaining_seconds_uses_prior_until_work_starts():
    remaining = remaining_seconds(elapsed=2, done_pages=0, total_pages=2, page_fraction=0, prior_per_page=10)
    assert remaining == 18.0


def test_remaining_seconds_scales_with_completed_pages():
    remaining = remaining_seconds(elapsed=10, done_pages=1, total_pages=2, page_fraction=0)
    assert remaining == 10.0


def test_percent_complete_includes_current_page_fraction():
    assert percent_complete(0, 2, 0.5) == 25
    assert percent_complete(2, 2, 0) == 100


def test_ndjson_stream_emits_started_and_complete():
    app = FastAPI()

    @app.get("/stream")
    def stream():
        def run(emit):
            t0 = time.time()
            started = "2026-01-01T00:00:00Z"
            emit(make_event("started", t0=t0, started_at=started, done=0, total=1, filename="p.jpg"))
            emit({
                **make_event("complete", t0=t0, started_at=started, done=1, total=1, elapsed=1.5),
                "ended_at": "2026-01-01T00:00:02Z",
                "result": {"ok": True, "started_at": started, "ended_at": "2026-01-01T00:00:02Z"},
            })

        return ndjson_stream(run)

    client = TestClient(app)
    res = client.get("/stream")
    assert res.status_code == 200
    assert "ndjson" in res.headers["content-type"]
    events = [json.loads(line) for line in res.text.strip().split("\n")]
    assert events[0]["event"] == "started"
    assert events[0]["started_at"] == "2026-01-01T00:00:00Z"
    assert "remaining_seconds" in events[0]
    assert events[-1]["event"] == "complete"
    assert events[-1]["result"]["ok"] is True
