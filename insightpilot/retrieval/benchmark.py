"""Benchmark retrieval quality (recall@k and MRR) for each retrieval mode."""
from __future__ import annotations

import json
from pathlib import Path

from .hybrid import MODES, HybridRetriever


def load_queries(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def evaluate_retrieval(retriever: HybridRetriever, queries: list[dict], ks=(1, 3, 5)) -> dict:
    report: dict = {"n_queries": len(queries), "embedder": retriever.embedder.name, "modes": {}}
    for mode in MODES:
        hits = {k: 0 for k in ks}
        reciprocal = 0.0
        misses = []
        for item in queries:
            expected = set(item["expected"])
            ranked = [r["chunk_id"] for r in retriever.search(item["query"], k=max(ks), mode=mode)]
            first = next((i for i, cid in enumerate(ranked) if cid in expected), None)
            if first is not None:
                reciprocal += 1.0 / (first + 1)
                for k in ks:
                    if first < k:
                        hits[k] += 1
            else:
                misses.append(item["query"])
        n = len(queries) or 1
        report["modes"][mode] = {
            **{f"recall@{k}": round(hits[k] / n, 4) for k in ks},
            "mrr": round(reciprocal / n, 4),
            "queries_with_no_hit_in_top_k": misses,
        }
    return report
