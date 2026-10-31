import unittest

from insightpilot.config import ROOT


class WebUiTests(unittest.TestCase):
    def test_pages_use_api_data_and_safe_text_rendering(self):
        page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
        for endpoint in ("/api/ask", "/api/ingest", "/api/ingest/report/", "/api/schema",
                         "/api/eval/summary", "/api/traces"):
            self.assertIn(endpoint, page)
        for section in ("page-chat", "page-data", "page-evaluation", "page-traces"):
            self.assertIn(section, page)
        self.assertIn("Backend offline", page)
        self.assertIn('const API_ORIGIN = "http://127.0.0.1:8000"', page)
        self.assertIn("window.location.origin !== API_ORIGIN", page)
        self.assertIn("error.requestedUrl = requestedUrl", page)
        self.assertIn("API URL: ${requestedUrl}", page)
        self.assertIn(
            "python -m uvicorn insightpilot.api:app --host 127.0.0.1 --port 8000", page
        )
        self.assertNotIn("innerHTML", page)
        self.assertIn("textContent", page)


if __name__ == "__main__":
    unittest.main()
