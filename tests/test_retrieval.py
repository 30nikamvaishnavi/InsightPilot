import unittest

from insightpilot.config import ROOT
from insightpilot.retrieval import HybridRetriever, evaluate_retrieval, load_chunks, load_queries
from insightpilot.retrieval.bm25 import BM25
from insightpilot.retrieval.tokenize import tokenize

DOCS = ROOT / "data" / "docs"
QUERIES = ROOT / "data" / "eval" / "retrieval_queries.jsonl"


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.chunks = load_chunks(DOCS)
        cls.retriever = HybridRetriever(cls.chunks)
        cls.queries = load_queries(QUERIES)

    def test_tokenizer_drops_stopwords_and_stems(self):
        self.assertEqual(tokenize("The discounts are approved"), ["discount", "approv"])

    def test_chunk_ids_are_unique_and_stable(self):
        ids = [c.id for c in self.chunks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("returns_policy::return-window", ids)

    def test_every_expected_id_in_the_benchmark_exists(self):
        self.assertGreaterEqual(len(self.chunks), 60)
        self.assertGreaterEqual(len(self.queries), 100)
        ids = {c.id for c in self.chunks}
        for item in self.queries:
            for expected in item["expected"]:
                self.assertIn(expected, ids)

    def test_bm25_prefers_the_matching_document(self):
        bm = BM25().fit([["cat", "sat"], ["dog", "barked"], ["cat", "cat", "purr"]])
        scores = bm.scores(["cat"])
        self.assertGreater(scores[2], scores[0])
        self.assertEqual(scores[1], 0)

    def test_calculation_question_prefers_formula_without_corpus_prompting(self):
        hits = self.retriever.search("how is revenue calculated", k=3)
        self.assertEqual(hits[0]["chunk_id"], "revenue_definition::revenue-formula")

    def test_all_modes_return_ranked_results(self):
        for mode in ("hybrid", "bm25", "embedding"):
            hits = self.retriever.search("return window for refunds", k=3, mode=mode)
            self.assertTrue(hits, mode)
            scores = [h["score"] for h in hits]
            self.assertEqual(scores, sorted(scores, reverse=True))

    def test_invalid_mode_rejected(self):
        with self.assertRaises(ValueError):
            self.retriever.search("x", mode="magic")

    def test_off_topic_query_has_no_relevant_hit(self):
        hits = self.retriever.search("what is the weather in paris", k=3)
        self.assertFalse(any(h["relevant"] for h in hits))

    def test_benchmark_recall_is_reasonable(self):
        report = evaluate_retrieval(self.retriever, self.queries)
        self.assertEqual(report["n_queries"], len(self.queries))
        self.assertGreaterEqual(report["modes"]["hybrid"]["recall@5"], 0.9)
        self.assertGreaterEqual(report["modes"]["hybrid"]["recall@3"], 0.8)


if __name__ == "__main__":
    unittest.main()
