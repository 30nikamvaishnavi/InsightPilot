import os
import unittest

from insightpilot.db import is_postgres
from insightpilot.ingestion import get_schema
from insightpilot.tools.sql_guard import run_sql

DATABASE_URL = os.environ.get("DATABASE_URL")
HAVE_POSTGRES_URL = bool(DATABASE_URL and is_postgres(DATABASE_URL))


@unittest.skipUnless(HAVE_POSTGRES_URL, "set DATABASE_URL to a PostgreSQL test database")
class PostgresIntegrationTests(unittest.TestCase):
    def test_read_only_query_and_schema_access(self):
        result = run_sql(DATABASE_URL, "SELECT 1 AS value", max_rows=1, timeout_s=2)
        self.assertEqual(result["rows"], [[1]])
        self.assertIsInstance(get_schema(DATABASE_URL), dict)


if __name__ == "__main__":
    unittest.main()
