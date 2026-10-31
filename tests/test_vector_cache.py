import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from insightpilot.retrieval.chunking import Chunk
from insightpilot.retrieval.embeddings import make_embedder
from insightpilot.retrieval.hybrid import HybridRetriever
from insightpilot.retrieval.vector_store import NumpyVectorStore, make_vector_store


class CountingEmbedder:
    name = "test-counting"
    calls = 0

    def fit(self, texts):
        return self

    def encode(self, texts):
        self.calls += 1
        return np.ones((len(texts), 2), dtype=float)


class EmbeddingCacheTests(unittest.TestCase):
    def test_document_embeddings_are_loaded_from_disk_on_rebuild(self):
        cache = Path(tempfile.mkdtemp())
        chunks = [Chunk("doc::one", "doc", "One", "example content")]
        first = CountingEmbedder()
        HybridRetriever(chunks, embedder=first, cache_dir=cache)
        second = CountingEmbedder()
        retriever = HybridRetriever(chunks, embedder=second, cache_dir=cache)
        self.assertEqual(first.calls, 1)
        self.assertEqual(second.calls, 0)
        self.assertEqual(len(retriever.search("example")), 1)
        self.assertEqual(len(list(cache.glob("*.npy"))), 1)

    def test_sbert_embedder_loads_and_encodes(self):
        class FakeModel:
            def encode(self, texts, normalize_embeddings):
                self.normalized = normalize_embeddings
                return np.asarray([[0.6, 0.8] for _ in texts])

        model = FakeModel()
        module = types.SimpleNamespace(SentenceTransformer=lambda _name: model)
        with patch.dict(sys.modules, {"sentence_transformers": module}):
            embedder = make_embedder("sbert").fit(["text"])
            result = embedder.encode(["query"])
        self.assertTrue(model.normalized)
        np.testing.assert_allclose(result, [[0.6, 0.8]])

    def test_unknown_embedder_is_rejected(self):
        with self.assertRaises(ValueError):
            make_embedder("not-a-real-embedder")

    def test_numpy_vector_store_is_default(self):
        self.assertIsInstance(make_vector_store(), NumpyVectorStore)

    def test_postgres_url_selects_pgvector_store(self):
        with patch("insightpilot.retrieval.vector_store.PgVectorStore") as postgres_store:
            make_vector_store("postgresql://example", "test-model")
        postgres_store.assert_called_once_with("postgresql://example", "test-model")

    def test_pgvector_store_uses_mocked_database_for_writes_and_read_only_search(self):
        class FakeConnection:
            def __init__(self):
                self.statements = []
                self.rows = [("chunk::one", 0.75)]

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def transaction(self):
                return self

            def execute(self, statement, params=None):
                self.statements.append((statement, params))
                return self

            def cursor(self):
                return self

            def executemany(self, statement, values):
                self.statements.append((statement, values))

            def fetchall(self):
                return self.rows

        pgvector_package = types.ModuleType("pgvector")
        pgvector_package.__path__ = []
        pgvector_psycopg = types.ModuleType("pgvector.psycopg")
        register_vector = unittest.mock.Mock()
        pgvector_psycopg.register_vector = register_vector
        conn = FakeConnection()
        with patch.dict(sys.modules, {"pgvector": pgvector_package, "pgvector.psycopg": pgvector_psycopg}), patch(
            "insightpilot.retrieval.vector_store.connect_postgres", return_value=conn
        ), patch("insightpilot.db.connect_postgres", return_value=conn):
            from insightpilot.retrieval.vector_store import PgVectorStore

            store = PgVectorStore("postgresql://example", "test-model")
            chunks = [Chunk("chunk::one", "doc", "One", "example content")]
            store.fit(np.asarray([[1.0, 0.0]]), chunks)
            scores = store.scores(np.asarray([1.0, 0.0]))

        self.assertIn(("SET TRANSACTION READ ONLY", None), conn.statements)
        self.assertTrue(any("CREATE TABLE IF NOT EXISTS insightpilot_vectors" in sql for sql, _ in conn.statements))
        self.assertTrue(any("ON CONFLICT" in sql for sql, _ in conn.statements))
        np.testing.assert_allclose(scores, [0.75])
        self.assertEqual(register_vector.call_count, 2)


if __name__ == "__main__":
    unittest.main()
