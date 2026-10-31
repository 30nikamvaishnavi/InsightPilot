"""Hybrid retrieval: BM25 keyword search + embedding similarity, fused with RRF."""
from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from .bm25 import BM25
from .chunking import Chunk
from .embeddings import make_embedder
from .tokenize import tokenize
from .vector_store import NumpyVectorStore

MODES = ("hybrid", "bm25", "embedding")
QUERY_EXPANSIONS = {"calculat": ("formula",), "calculation": ("formula",)}


class HybridRetriever:
    def __init__(self, chunks: list[Chunk], embedder=None, rrf_k: int = 60, cache_dir: str | Path | None = None,
                 vector_store=None) -> None:
        self.chunks = chunks
        self.rrf_k = rrf_k
        texts = [f"{c.heading}. {c.text}" for c in chunks]
        self.bm25 = BM25().fit([tokenize(t) for t in texts])
        self.embedder = (embedder or make_embedder()).fit(texts)
        digest = hashlib.sha256((self.embedder.name + "\n" + "\n".join(texts)).encode("utf-8")).hexdigest()
        cache_file = Path(cache_dir) / f"{digest}.npy" if cache_dir else None
        matrix = None
        if cache_file and cache_file.exists():
            try:
                cached = np.load(cache_file, allow_pickle=False)
                if cached.ndim == 2 and cached.shape[0] == len(texts):
                    matrix = cached
            except (OSError, ValueError):
                matrix = None
        if matrix is None:
            matrix = self.embedder.encode(texts)
            if cache_file:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                with cache_file.open("wb") as handle:
                    np.save(handle, matrix, allow_pickle=False)
        self.matrix = matrix
        self.vector_store = vector_store or NumpyVectorStore()
        self.vector_store.fit(self.matrix, self.chunks)

    @staticmethod
    def _ranked(scores: np.ndarray) -> list[int]:
        order = np.argsort(-scores, kind="stable")
        return [int(i) for i in order if scores[i] > 0]

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        if mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}")
        if not self.chunks or not query.strip():
            return []
        query_terms = tokenize(query)
        query_terms.extend(
            synonym
            for term in query_terms
            for synonym in QUERY_EXPANSIONS.get(term, ())
        )
        bm = self.bm25.scores(query_terms)
        em = self.vector_store.scores(self.embedder.encode([query])[0])
        if mode == "bm25":
            fused = {i: float(bm[i]) for i in self._ranked(bm)}
        elif mode == "embedding":
            fused = {i: float(em[i]) for i in self._ranked(em)}
        else:
            fused = {}
            for scores in (bm, em):
                for rank, idx in enumerate(self._ranked(scores)):
                    fused[idx] = fused.get(idx, 0.0) + 1.0 / (self.rrf_k + rank + 1)
        top = sorted(fused.items(), key=lambda item: (-item[1], item[0]))[:k]
        results = []
        for idx, score in top:
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk.id,
                "doc": chunk.doc,
                "heading": chunk.heading,
                "text": chunk.text,
                "score": round(score, 6),
                "bm25": round(float(bm[idx]), 4),
                "embedding": round(float(em[idx]), 4),
                # Embedding similarity is only used for ranking: on a small corpus it is high even for
                # off-topic text, so a hit counts as relevant only with real keyword evidence.
                "relevant": bool(bm[idx] > 0),
            })
        return results
