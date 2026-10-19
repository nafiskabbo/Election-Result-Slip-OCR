import os
import subprocess
import time
from urllib.parse import urlparse, urlunparse

import psycopg
import pytest

# Isolate pytest from the desk DB and from production *before* backend.config
# loads .env. load_dotenv() does not override variables already in the environment.
os.environ["BALLOT_ALLOW_TRUNCATE"] = "1"
os.environ["DATABASE_URL"] = os.environ.get(
    "BALLOT_TEST_DATABASE_URL",
    "postgresql://ballot:ballot_local_dev@127.0.0.1:5432/ballot_test",
)

from backend.config import DATABASE_URL
from backend import config as backend_config
from backend.database import close_pool, init_db, truncate_operational_tables


def _ready(url: str) -> bool:
    try:
        with psycopg.connect(url, connect_timeout=2) as conn:
            conn.execute("select 1")
        return True
    except Exception:
        return False


def _admin_url(url: str) -> str:
    parts = urlparse(url)
    return urlunparse(parts._replace(path="/postgres"))


def _ensure_database_exists(url: str) -> None:
    name = (urlparse(url).path or "").lstrip("/").split("?")[0] or "ballot_test"
    admin = _admin_url(url)
    with psycopg.connect(admin, connect_timeout=5, autocommit=True) as conn:
        row = conn.execute(
            "select 1 from pg_database where datname = %s",
            (name,),
        ).fetchone()
        if not row:
            conn.execute(f'create database "{name}" owner ballot')


def _set_database_url(url: str) -> None:
    os.environ["DATABASE_URL"] = url
    backend_config.DATABASE_URL = url
    close_pool()


def _ensure_postgres():
    url = os.environ["DATABASE_URL"]
    admin = _admin_url(url)
    if _ready(admin):
        _ensure_database_exists(url)
        return
    subprocess.run(["docker", "compose", "up", "-d", "db"], check=True)
    docker_url = "postgresql://ballot:ballot_local_dev@127.0.0.1:5433/ballot_test"
    docker_admin = _admin_url(docker_url)
    for _ in range(40):
        if _ready(docker_admin):
            _set_database_url(docker_url)
            _ensure_database_exists(docker_url)
            return
        time.sleep(0.5)
    raise RuntimeError(
        f"PostgreSQL is not reachable at {url}. Start it with: ./run.sh"
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
