"""Lightweight data validation and profiling."""
from __future__ import annotations

import pandas as pd
from pandas.api.types import infer_dtype


def profile(df: pd.DataFrame, notes: dict | None = None) -> dict:
    columns = []
    issues: list[str] = []
    total = len(df)
    for name in df.columns:
        series = df[name]
        nulls = int(series.isna().sum())
        info = {
            "name": name,
            "dtype": str(series.dtype),
            "inferred_type": infer_dtype(series, skipna=True),
            "nulls": nulls,
            "null_pct": round(nulls / total * 100, 2) if total else 0.0,
            "unique": int(series.nunique(dropna=True)),
            "duplicate_count": int(series.duplicated().sum()),
        }
        is_number = pd.api.types.is_numeric_dtype(series) and not pd.api.types.is_bool_dtype(series)
        if is_number and series.notna().any():
            info.update(min=float(series.min()), max=float(series.max()), mean=float(series.mean()))
            if (series < 0).any():
                issues.append(f"{name}: contains negative values")
        if total and nulls / total > 0.2:
            issues.append(f"{name}: {nulls} of {total} values are missing")
        columns.append(info)
    result = {"rows": total, "columns": columns, "issues": issues}
    result.update(notes or {})
    return result
