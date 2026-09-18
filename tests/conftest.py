import subprocess
import time

import psycopg
import pytest

from backend.config import DATABASE_URL
from backend.database import close_pool, init_db, truncate_operational_tables


def _postgres_ready() -> bool:
    try:
        with psycopg.connect(DATABASE_URL, connect_timeout=2) as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


def _ensure_postgres():
    if _postgres_ready():
        return
    subprocess.run(["docker", "compose", "up", "-d", "db"], check=True)
    for _ in range(40):
        if _postgres_ready():
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"PostgreSQL is not reachable at {DATABASE_URL}. Start it with: ./run.sh"
    )


def pytest_sessionfinish(session, exitstatus):
    close_pool()


@pytest.fixture
def postgres_db():
    _ensure_postgres()
    init_db()
    truncate_operational_tables()
    yield
    truncate_operational_tables()
