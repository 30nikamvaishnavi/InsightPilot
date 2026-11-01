import unittest

from insightpilot.config import ROOT
from insightpilot.service import Analyst
from tests.helpers import make_settings


class ServiceTests(unittest.TestCase):
    def test_missing_database_is_created_from_sample_data(self):
        settings = make_settings(sample_dir=ROOT / "data" / "sample")
        self.assertFalse(settings.db_path.exists())

        service = Analyst(settings, use_langgraph=False, explainer=None)

        self.assertTrue(settings.db_path.is_file())
        self.assertIn("sales", service.schema())
        self.assertIn("returns", service.schema())
        self.assertIn("targets", service.schema())


if __name__ == "__main__":
    unittest.main()
