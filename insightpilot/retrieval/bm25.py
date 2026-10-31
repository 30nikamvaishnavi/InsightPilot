"""A small, dependency-free BM25 implementation."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np


class BM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.docs: list[list[str]] = []

    def fit(self, docs: list[list[str]]) -> "BM25":
        self.docs = docs
        self.n = len(docs)
        self.avgdl = (sum(len(d) for d in docs) / self.n) if self.n else 1.0
        self.avgdl = self.avgdl or 1.0
        self.tf = [Counter(d) for d in docs]
        df: Counter = Counter()
        for d in docs:
            df.update(set(d))
        self.idf = {t: math.log(1 + (self.n - c + 0.5) / (c + 0.5)) for t, c in df.items()}
        return self

    def scores(self, query: list[str]) -> np.ndarray:
        out = np.zeros(self.n)
        for i, (tf, doc) in enumerate(zip(self.tf, self.docs)):
            length = len(doc)
            total = 0.0
            for term in query:
                freq = tf.get(term, 0)
                if freq:
                    norm = freq + self.k1 * (1 - self.b + self.b * length / self.avgdl)
                    total += self.idf[term] * freq * (self.k1 + 1) / norm
            out[i] = total
        return out
