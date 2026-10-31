import unittest

from insightpilot.agent.planner import NUMERIC_TYPES, RulePlanner, TableInfo


class PlannerDialectTests(unittest.TestCase):
    def setUp(self):
        self.info = TableInfo("sales", {"order_date": "TEXT"}, [], {}, "order_date")

    def test_sqlite_time_expression_is_unchanged(self):
        self.assertEqual(RulePlanner._time_expr(self.info, "month"), 'strftime(\'%Y-%m\', "order_date")')

    def test_postgres_time_expressions_use_date_functions(self):
        planner = RulePlanner("postgresql")
        self.assertEqual(
            planner._time_expr(self.info, "month", planner.dialect),
            'to_char(date_trunc(\'month\', "order_date"::date), \'YYYY-MM\')',
        )
        self.assertIn("EXTRACT(QUARTER", planner._time_expr(self.info, "quarter", planner.dialect))

    def test_postgres_date_filters_use_extract(self):
        clauses, _ = RulePlanner._filters("sales in march 2025 q1", self.info, "postgresql")
        self.assertEqual(
            clauses,
            ['EXTRACT(YEAR FROM "order_date"::date)::integer = 2025',
             'EXTRACT(MONTH FROM "order_date"::date)::integer = 3',
             'EXTRACT(QUARTER FROM "order_date"::date)::integer = 1'],
        )

    def test_postgres_double_precision_is_numeric(self):
        self.assertIn("DOUBLE PRECISION", NUMERIC_TYPES)


if __name__ == "__main__":
    unittest.main()
