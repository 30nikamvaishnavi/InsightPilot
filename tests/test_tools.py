import sqlite3
import tempfile
import unittest
from pathlib import Path

import numpy as np

from insightpilot.tools import SqlError, run_sql, validate_sql
from insightpilot.tools.stats import describe_correlation, pct_change, pearson_from_sums, summary


class SqlGuardTests(unittest.TestCase):
    def setUp(self):
        self.db = Path(tempfile.mkdtemp()) / "g.db"
        with sqlite3.connect(self.db) as conn:
            conn.execute("CREATE TABLE t (a INTEGER, b TEXT)")
            conn.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"r{i}") for i in range(10)])

    def test_accepts_select_and_with(self):
        self.assertEqual(validate_sql("SELECT 1;"), "SELECT 1")
        self.assertTrue(validate_sql("WITH x AS (SELECT 1) SELECT * FROM x"))

    def test_rejects_dangerous_sql(self):
        for sql in ["DROP TABLE t", "SELECT 1; DROP TABLE t", "DELETE FROM t", "UPDATE t SET a=1",
                    "SELECT * FROM t -- x", "SELECT /* x */ 1", "PRAGMA table_info(t)", "", "INSERT INTO t VALUES (1,'x')",
                    "ATTACH DATABASE 'x' AS y"]:
            with self.assertRaises(SqlError, msg=sql):
                validate_sql(sql)

    def test_row_cap_and_truncation(self):
        result = run_sql(self.db, "SELECT a FROM t ORDER BY a", max_rows=4)
        self.assertEqual(len(result["rows"]), 4)
        self.assertTrue(result["truncated"])
        self.assertFalse(run_sql(self.db, "SELECT a FROM t", max_rows=50)["truncated"])

    def test_connection_is_read_only(self):
        # Even if validation were bypassed, the database is opened read-only.
        uri = self.db.resolve().as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as conn:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("DELETE FROM t")

    def test_bad_sql_becomes_sqlerror(self):
        with self.assertRaises(SqlError):
            run_sql(self.db, "SELECT nope FROM t")


class StatsTests(unittest.TestCase):
    def test_pearson_matches_numpy(self):
        rng = np.random.RandomState(1)
        x = rng.rand(200)
        y = 3 * x + rng.rand(200)
        r = pearson_from_sums(len(x), x.sum(), y.sum(), (x * y).sum(), (x * x).sum(), (y * y).sum())
        self.assertAlmostEqual(r, float(np.corrcoef(x, y)[0, 1]), places=9)

    def test_pearson_edge_cases(self):
        with self.assertRaises(ValueError):
            pearson_from_sums(2, 1, 1, 1, 1, 1)
        with self.assertRaises(ValueError):
            pearson_from_sums(5, 10, 10, 20, 20, 20)  # constant columns

    def test_pct_change_and_summary(self):
        self.assertAlmostEqual(pct_change(100, 150), 50.0)
        self.assertIsNone(pct_change(0, 5))
        stats = summary([1, 2, 3, 4])
        self.assertEqual(stats["mean"], 2.5)
        self.assertEqual(stats["median"], 2.5)
        self.assertAlmostEqual(stats["std"], 1.2909944487, places=6)

    def test_describe_correlation(self):
        self.assertEqual(describe_correlation(0.9), "very strong positive")
        self.assertEqual(describe_correlation(-0.45), "moderate negative")


if __name__ == "__main__":
    unittest.main()
