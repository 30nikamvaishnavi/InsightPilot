"""Database selection and low-level connection helpers."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Generator


def is_postgres(database: Any) -> bool:
    return isinstance(database, str) and database.lower().startswith(("postgresql://", "postgres://"))


def dialect_for(database: Any) -> str:
    return "postgresql" if is_postgres(database) else "sqlite"


def connect_postgres(database_url: str):
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("PostgreSQL support requires psycopg 3. Install requirements-postgres.txt.") from exc
    return psycopg.connect(database_url)


@contextmanager
def postgres_read_only(database_url: str, timeout_s: float = 5.0) -> Generator[Any, None, None]:
    with connect_postgres(database_url) as conn:
        with conn.transaction():
            conn.execute("SET TRANSACTION READ ONLY")
            conn.execute("SELECT set_config('statement_timeout', %s, true)", (f"{int(timeout_s * 1000)}ms",))
            yield conn
