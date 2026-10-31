"""Numeric grounding check.

Every number in an answer must appear in the facts (query result, numbers computed
by code, retrieved text, or the question itself). This catches invented figures;
it does not judge whether the wording is right.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
TOLERANCE = 0.0051


def extract_numbers(text: str) -> list[float]:
    values = []
    for token in _NUMBER.findall(str(text)):
        try:
            values.append(float(token.replace(",", "")))
        except ValueError:
            continue
    return values


def _walk(obj: Any) -> Iterable[Any]:
    if isinstance(obj, dict):
        for value in obj.values():
            yield from _walk(value)
    elif isinstance(obj, (list, tuple, set)):
        for value in obj:
            yield from _walk(value)
    else:
        yield obj


def collect_facts(*sources: Any) -> list[float]:
    facts: list[float] = []
    for source in sources:
        for item in _walk(source):
            if item is None or isinstance(item, bool):
                continue
            if isinstance(item, (int, float)):
                value = float(item)
                facts.append(value)
                for places in range(0, 5):
                    facts.append(round(value, places))
            else:
                facts.extend(extract_numbers(str(item)))
    return facts


def check_numbers(text: str, facts: list[float]) -> dict:
    numbers = extract_numbers(text)
    unsupported = [n for n in numbers if not any(abs(n - f) <= TOLERANCE for f in facts)]
    return {"checked": len(numbers), "unsupported": unsupported, "ok": not unsupported}
