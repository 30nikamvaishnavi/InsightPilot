import unittest
from types import SimpleNamespace
from unittest.mock import patch

from insightpilot.tools.sql_guard import SqlError, run_sql


class FakeCursor:
    description = [SimpleNamespace(name="value")]

    def __init__(self, statements):
        self.statements = statements
        self.fetch_count = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql):
        self.statements.append(sql)

    def fetchmany(self, count):
        self.fetch_count = count
        return [(42,), (43,)][:count]


class FakeConnection:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def transaction(self):
        return self

    def execute(self, sql, params=None):
        self.statements.append((sql, params))

    def cursor(self, name):
        self.cursor_instance = FakeCursor(self.statements)
        self.cursor_name = name
        return self.cursor_instance


class PostgresQuerySafetyTests(unittest.TestCase):
    def test_sql_is_validated_and_read_only_timeout_and_row_cap_are_applied(self):
        from insightpilot.tools import sql_guard

        conn = FakeConnection()
        original_validate = sql_guard.validate_sql
        with patch("insightpilot.db.connect_postgres", return_value=conn), patch(
            "insightpilot.tools.sql_guard.validate_sql", wraps=original_validate
        ) as validate:
            result = run_sql("postgresql://db", "SELECT 42 AS value", max_rows=1, timeout_s=2.5)

        validate.assert_called_once_with("SELECT 42 AS value")
        self.assertEqual(conn.statements[0], ("SET TRANSACTION READ ONLY", None))
        self.assertEqual(conn.statements[1], ("SELECT set_config('statement_timeout', %s, true)", ("2500ms",)))
        self.assertEqual(conn.statements[2], "SELECT 42 AS value")
        self.assertEqual(conn.cursor_instance.fetch_count, 2)
        self.assertEqual(result["rows"], [[42]])
        self.assertTrue(result["truncated"])

    def test_invalid_sql_is_rejected_before_opening_postgres_connection(self):
        with patch("insightpilot.db.connect_postgres") as connect:
            with self.assertRaises(SqlError):
                run_sql("postgresql://db", "DELETE FROM sales")
        connect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
