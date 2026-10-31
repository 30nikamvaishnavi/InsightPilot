"""Tiny tokenizer + stemmer used by the keyword (BM25) side of retrieval."""
from __future__ import annotations

import re

STOPWORDS = frozenset(
    """a an and are as at be by can do does for from has have how i in is it its of on or
    that the their there these this to was we what when where which who why will with you your
    our us me my""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")


def stem(word: str) -> str:
    for suffix in ("ing", "ed", "s"):
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            word = word[: -len(suffix)]
            break
    if len(word) > 4 and word.endswith("e"):
        word = word[:-1]
    return word


def tokenize(text: str) -> list[str]:
    return [stem(tok) for tok in _TOKEN.findall(text.lower()) if tok not in STOPWORDS]
