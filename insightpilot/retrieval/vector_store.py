"""Vector ranking backends used by hybrid retrieval."""
from __future__ import annotations

import hashlib
from typing import Protocol

import numpy as np

from ..db import connect_postgres, postgres_read_only
from .chunking import Chunk


class VectorStore(Protocol):
    def fit(self, matrix: np.ndarray, chunks: list[Chunk]) -> None: ...

    def scores(self, query: np.ndarray) -> np.ndarray: ...


class NumpyVectorStore:
    def __init__(self) -> None:
        self.matrix = np.empty((0, 0), dtype=float)

    def fit(self, matrix: np.ndarray, chunks: list[Chunk]) -> None:
        self.matrix = matrix
        self.chunks = chunks

    def scores(self, query: np.ndarray) -> np.ndarray:
        return self.matrix @ query


class PgVectorStore:
    def __init__(self, database_url: str, embedder_name: str = "unspecified") -> None:
        try:
            from pgvector.psycopg import register_vector
        except ImportError as exc:
            raise RuntimeError("PostgreSQL vector search requires pgvector. Install requirements-postgres.txt.") from exc
        self.database_url = database_url
        self.embedder_name = embedder_name
        self.register_vector = register_vector

    def fit(self, matrix: np.ndarray, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.corpus_hash = hashlib.sha256(
            (
                f"{self.embedder_name}\0{matrix.shape[1]}\n"
                + "\n".join(f"{chunk.id}\0{chunk.text}" for chunk in chunks)
            ).encode("utf-8")
        ).hexdigest()
        with connect_postgres(self.database_url) as conn:
            conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            self.register_vector(conn)
            conn.execute(
                "CREATE TABLE IF NOT EXISTS insightpilot_vectors ("
                "corpus_hash TEXT NOT NULL, chunk_id TEXT NOT NULL, embedding VECTOR NOT NULL, "
                "PRIMARY KEY (corpus_hash, chunk_id))"
            )
            conn.cursor().executemany(
                "INSERT INTO insightpilot_vectors (corpus_hash, chunk_id, embedding) VALUES (%s, %s, %s) "
                "ON CONFLICT (corpus_hash, chunk_id) DO UPDATE SET embedding = EXCLUDED.embedding",
                [(self.corpus_hash, chunk.id, vector.tolist()) for chunk, vector in zip(chunks, matrix)],
            )

    def scores(self, query: np.ndarray) -> np.ndarray:
        with postgres_read_only(self.database_url) as conn:
            self.register_vector(conn)
            rows = conn.execute(
                "SELECT chunk_id, 1 - (embedding <=> %s) AS similarity FROM insightpilot_vectors "
                "WHERE corpus_hash = %s",
                (query.tolist(), self.corpus_hash),
            ).fetchall()
        by_id = {chunk_id: float(score) for chunk_id, score in rows}
        return np.asarray([by_id.get(chunk.id, 0.0) for chunk in self.chunks], dtype=float)


def make_vector_store(database_url: str | None = None, embedder_name: str = "unspecified"):
    return PgVectorStore(database_url, embedder_name) if database_url else NumpyVectorStore()
