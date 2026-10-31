import contextlib
import io
import unittest
from unittest.mock import patch

from insightpilot.cli import main


class IngestCliTests(unittest.TestCase):
    def test_report_flag_prints_full_validation_profile(self):
        report = {"table": "sample", "rows": 2, "columns": [{"name": "amount", "null_pct": 0.0}]}
        with patch("insightpilot.cli.Analyst") as analyst_class, contextlib.redirect_stdout(io.StringIO()) as output:
            analyst_class.return_value.ingest.return_value = report
            result = main(["ingest", "sample.csv", "--report"])
        self.assertEqual(result, 0)
        self.assertIn('"null_pct": 0.0', output.getvalue())


if __name__ == "__main__":
    unittest.main()
