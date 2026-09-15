import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence

from psycopg import ClientCursor
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from backend.config import DATABASE_URL, SCHEMA_DIR

_pool: Optional[ConnectionPool] = None

JSON_AS_TEXT_COLUMNS = {"bbox_json", "exception_flags"}


def ballot_dict_row(cursor):
    desc = cursor.description
    if not desc:
        return lambda values: values
    fields = [col.name for col in desc]

    def make_row(values):
        row = {}
        for key, value in zip(fields, values):
            if isinstance(value, datetime):
                value = value.isoformat()
            elif key in JSON_AS_TEXT_COLUMNS and isinstance(value, (dict, list)):
                value = json.dumps(value) if value else None
            row[key] = value
        return row

    return make_row


def parse_config_json(value: Any) -> dict:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        return json.loads(value) if value else {}
    return dict(value)


def as_jsonb(value: Any):
    if value is None or value == "":
        return None
    if isinstance(value, Jsonb):
        return value
    if value == []:
        return None
    return Jsonb(value)


class DatabaseCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, query: str, params: Optional[Sequence[Any]] = None):
        query = query.replace("?", "%s")
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, tuple(params))
        return self

    def executemany(self, query: str, params_seq: Iterable[Sequence[Any]]):
        query = query.replace("?", "%s")
        self._cursor.executemany(query, list(params_seq))
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description


class PooledConnection:
    def __init__(self, conn, pool: ConnectionPool):
        self._conn = conn
        self._pool = pool
        self._closed = False

    def cursor(self) -> DatabaseCursor:
        return DatabaseCursor(self._conn.cursor())

    def execute(self, query: str, params: Optional[Sequence[Any]] = None):
        return self.cursor().execute(query, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self._conn.rollback()
        except Exception:
            pass
        self._pool.putconn(self._conn)


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = ConnectionPool(
            conninfo=DATABASE_URL,
            min_size=1,
            max_size=10,
            open=True,
            kwargs={"row_factory": ballot_dict_row},
        )
    return _pool


def get_db_connection() -> PooledConnection:
    return PooledConnection(get_pool().getconn(), get_pool())


def close_pool():
    global _pool
    if _pool is not None and not _pool.closed:
        _pool.close()
    _pool = None


def _run_sql_file(conn, path: Path):
    sql = path.read_text()
    with ClientCursor(conn) as cursor:
        cursor.execute(sql)


def init_db():
    pool = get_pool()
    with pool.connection() as conn:
        _run_sql_file(conn, SCHEMA_DIR / "ballot.sql")
        _run_sql_file(conn, SCHEMA_DIR / "seed.sql")
        conn.commit()


def truncate_operational_tables():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            truncate table
                validation_results,
                party_results,
                audit_logs,
                slip_pages,
                slips
            restart identity cascade
            """
        )
        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
