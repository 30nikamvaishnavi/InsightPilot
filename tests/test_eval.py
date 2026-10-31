import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from insightpilot.config import get_settings
from insightpilot.eval.run_eval import run


class EvaluationSummaryTests(unittest.TestCase):
    def test_run_reports_retrieval_metrics_by_embedder_and_mode(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            settings = replace(
                get_settings(),
                db_path=root / "eval.db",
                database_url=None,
                trace_dir=root / "traces",
                upload_dir=root / "uploads",
                embedding_cache_dir=root / "embeddings",
                results_dir=root / "results",
            )
            with patch("insightpilot.eval.run_eval.get_settings", return_value=settings):
                summary = run(write=False)
        reports = summary["retrieval_by_embedder"]
        self.assertIn(summary["metadata"]["embedder"], reports)
        for report in reports.values():
            self.assertTrue(report["embedder"])
            self.assertEqual(set(report["modes"]), {"hybrid", "bm25", "embedding"})
            for metrics in report["modes"].values():
                self.assertIn("mrr", metrics)
                self.assertIn("recall@5", metrics)


if __name__ == "__main__":
    unittest.main()
