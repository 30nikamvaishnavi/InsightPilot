"""Read-only SQL execution with validation, a row cap and a time limit."""
from __future__ import annotations

import re
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from ..db import is_postgres, postgres_read_only


class SqlError(ValueError):
    """Raised when a query is rejected or fails."""


_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|pragma|vacuum|reindex|truncate|grant|revoke)\b",
    re.IGNORECASE,
)


def validate_sql(sql: str) -> str:
    """Return a cleaned single SELECT statement or raise ``SqlError``."""
    cleaned = (sql or "").strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    if not cleaned:
        raise SqlError("Empty query")
    if ";" in cleaned:
        raise SqlError("Only one statement is allowed")
    if "--" in cleaned or "/*" in cleaned:
        raise SqlError("SQL comments are not allowed")
    if not re.match(r"^(select|with)\b", cleaned, re.IGNORECASE):
        raise SqlError("Only SELECT queries are allowed")
    match = _FORBIDDEN.search(cleaned)
    if match:
        raise SqlError(f"Keyword '{match.group(0).lower()}' is not allowed")
    return cleaned


def run_sql(db_path: str | Path, sql: str, max_rows: int = 200, timeout_s: float = 5.0) -> dict:
    cleaned = validate_sql(sql)
    if is_postgres(db_path):
        started = time.monotonic()
        try:
            with postgres_read_only(str(db_path), timeout_s) as conn:
                with conn.cursor(name=f"insightpilot_{time.monotonic_ns()}") as cursor:
                    cursor.execute(cleaned)
                    columns = [d.name for d in cursor.description or []]
                    rows = cursor.fetchmany(max_rows + 1)
        except Exception as exc:
            if isinstance(exc, SqlError):
                raise
            raise SqlError(f"Query failed: {exc}") from exc
        if time.monotonic() - started > timeout_s:
            raise SqlError(f"Query exceeded the {timeout_s:g} second time limit")
        truncated = len(rows) > max_rows
        return {"sql": cleaned, "columns": columns, "rows": [list(r) for r in rows[:max_rows]], "truncated": truncated}
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    started = time.monotonic()

    def _abort_if_slow() -> int:
        return 1 if time.monotonic() - started > timeout_s else 0

    try:
        with closing(sqlite3.connect(uri, uri=True)) as conn:
            conn.set_progress_handler(_abort_if_slow, 10_000)
            cursor = conn.execute(cleaned)
            columns = [d[0] for d in cursor.description or []]
            rows = cursor.fetchmany(max_rows + 1)
    except sqlite3.Error as exc:
        raise SqlError(f"Query failed: {exc}") from exc
    truncated = len(rows) > max_rows
    return {
        "sql": cleaned,
        "columns": columns,
        "rows": [list(r) for r in rows[:max_rows]],
        "truncated": truncated,
    }
