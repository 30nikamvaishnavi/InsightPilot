"""Persist cleaned data into SQLite and describe the resulting schema."""
from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

from ..db import connect_postgres, is_postgres, postgres_read_only
from .loaders import LOADERS, clean, load_file, snake
from .profile import profile


def _postgres_type(series) -> str:
    import pandas as pd

    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_integer_dtype(series):
        return "BIGINT"
    if pd.api.types.is_numeric_dtype(series):
        return "DOUBLE PRECISION"
    return "TEXT"


def _write_postgres_frame(frame, database_url: str, table: str) -> None:
    import pandas as pd

    columns = ", ".join(f'"{column}" {_postgres_type(frame[column])}' for column in frame.columns)
    placeholders = ", ".join(["%s"] * len(frame.columns))
    with connect_postgres(database_url) as conn:
        conn.execute(f'DROP TABLE IF EXISTS "{table}"')
        conn.execute(f'CREATE TABLE "{table}" ({columns})')
        if not frame.empty:
            values = [
                tuple(None if value is None or pd.isna(value) else value for value in row)
                for row in frame.itertuples(index=False, name=None)
            ]
            conn.cursor().executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', values)


def ingest_file(path: str | Path, db_path: str | Path, table: str | None = None) -> dict:
    path = Path(path)
    df, notes = clean(load_file(path))
    name = snake(table or path.stem)
    if is_postgres(db_path):
        _write_postgres_frame(df, str(db_path), name)
    else:
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(sqlite3.connect(db_path)) as conn:
            df.to_sql(name, conn, if_exists="replace", index=False)
            conn.commit()
    return {"table": name, "source": path.name, **profile(df, notes)}


def ingest_directory(directory: str | Path, db_path: str | Path) -> list[dict]:
    reports = []
    for path in sorted(Path(directory).iterdir()):
        if path.is_file() and path.suffix.lower() in LOADERS:
            reports.append(ingest_file(path, db_path))
    return reports


def _connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True)


def get_schema(db_path: str | Path) -> dict[str, list[dict]]:
    if is_postgres(db_path):
        schema: dict[str, list[dict]] = {}
        with postgres_read_only(str(db_path)) as conn:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE' "
                "AND table_name <> 'insightpilot_vectors' "
                "ORDER BY table_name"
            ).fetchall()
            for (table,) in tables:
                rows = conn.execute(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = %s ORDER BY ordinal_position",
                    (table,),
                ).fetchall()
                schema[table] = [{"name": row[0], "type": row[1].upper()} for row in rows]
        return schema
    if not Path(db_path).exists():
        return {}
    schema: dict[str, list[dict]] = {}
    with closing(_connect_readonly(db_path)) as conn:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        for (table,) in tables:
            info = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
            schema[table] = [{"name": row[1], "type": (row[2] or "TEXT")} for row in info]
    return schema


def distinct_values(db_path: str | Path, table: str, column: str, limit: int = 51) -> list[str]:
    if is_postgres(db_path):
        with postgres_read_only(str(db_path)) as conn:
            rows = conn.execute(
                f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT %s', (limit,)
            ).fetchall()
        return [str(row[0]) for row in rows]
    with closing(_connect_readonly(db_path)) as conn:
        rows = conn.execute(
            f'SELECT DISTINCT "{column}" FROM "{table}" WHERE "{column}" IS NOT NULL LIMIT ?', (limit,)
        ).fetchall()
    return [str(row[0]) for row in rows]
