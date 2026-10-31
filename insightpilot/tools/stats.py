"""Statistics computed by code (never by the language model)."""
from __future__ import annotations

import math
from statistics import mean, median, stdev


def summary(values: list[float]) -> dict:
    if not values:
        raise ValueError("No values")
    return {
        "count": len(values),
        "mean": float(mean(values)),
        "median": float(median(values)),
        "std": float(stdev(values)) if len(values) > 1 else 0.0,
        "min": float(min(values)),
        "max": float(max(values)),
    }


def pct_change(previous: float, current: float) -> float | None:
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100.0


def pearson_from_sums(n: float, sx: float, sy: float, sxy: float, sxx: float, syy: float) -> float:
    """Pearson r from aggregate sums, so the database does the heavy lifting."""
    if n < 3:
        raise ValueError("Need at least 3 rows to compute a correlation")
    denominator = math.sqrt((n * sxx - sx * sx) * (n * syy - sy * sy))
    if denominator == 0:
        raise ValueError("A column is constant, so correlation is undefined")
    return (n * sxy - sx * sy) / denominator


def describe_correlation(r: float) -> str:
    size = abs(r)
    strength = "very weak" if size < 0.2 else "weak" if size < 0.4 else "moderate" if size < 0.6 else "strong" if size < 0.8 else "very strong"
    direction = "positive" if r > 0 else "negative" if r < 0 else "no"
    return f"{strength} {direction}"
