"""Data ingestion: read a file into a DataFrame and clean it.

Adding a new input format is one function plus one ``register_loader`` call
(see ``tests/test_ingestion.py`` for a worked example with a pipe-delimited file).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import pandas as pd

Loader = Callable[[Path], pd.DataFrame]


def snake(name: object) -> str:
    """Turn any header into a safe snake_case identifier."""
    text = re.sub(r"[^0-9a-zA-Z]+", "_", str(name).strip()).strip("_").lower()
    return text or "column"


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def _tsv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="\t")


def _pipe_text(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, sep="|")


def _xlsx(path: Path) -> pd.DataFrame:
    return pd.read_excel(path)


def _parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path)


def _json(path: Path) -> pd.DataFrame:
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if isinstance(data, dict):
        lists = [value for value in data.values() if isinstance(value, list)]
        data = lists[0] if lists else [data]
    return pd.json_normalize(data)


def _jsonl(path: Path) -> pd.DataFrame:
    return pd.read_json(path, lines=True)


LOADERS: dict[str, Loader] = {
    ".csv": _csv,
    ".tsv": _tsv,
    ".txt": _pipe_text,
    ".xlsx": _xlsx,
    ".parquet": _parquet,
    ".json": _json,
    ".jsonl": _jsonl,
}


def register_loader(extension: str, loader: Loader) -> None:
    """Teach the pipeline a new input format."""
    LOADERS[extension.lower()] = loader


def load_file(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    loader = LOADERS.get(path.suffix.lower())
    if loader is None:
        supported = ", ".join(sorted(LOADERS))
        raise ValueError(f"Unsupported file type '{path.suffix}'. Supported: {supported}")
    return loader(path)


def _looks_like_date_column(name: str) -> bool:
    return "date" in name or name.endswith("_at")


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Normalise headers, trim text, parse dates and drop empty or duplicate rows."""
    rows_in = len(df)
    df = df.copy()

    seen: dict[str, int] = {}
    names = []
    for column in df.columns:
        base = snake(column)
        seen[base] = seen.get(base, 0) + 1
        names.append(base if seen[base] == 1 else f"{base}_{seen[base]}")
    df.columns = names

    df = df.dropna(how="all")
    rows_after_empty = len(df)

    for column in df.columns:
        series = df[column]
        if pd.api.types.is_string_dtype(series) or pd.api.types.is_object_dtype(series):
            df[column] = series.map(
                lambda value: (value.strip() or None) if isinstance(value, str) else value
            )

    for column in df.columns:
        if not _looks_like_date_column(column):
            continue
        parsed = pd.to_datetime(df[column], errors="coerce", format="mixed")
        if len(parsed) and parsed.notna().mean() >= 0.8:
            df[column] = parsed.dt.strftime("%Y-%m-%d")

    df = df.drop_duplicates().reset_index(drop=True)
    notes = {
        "rows_in": rows_in,
        "empty_rows_removed": rows_in - rows_after_empty,
        "duplicates_removed": rows_after_empty - len(df),
    }
    return df, notes
