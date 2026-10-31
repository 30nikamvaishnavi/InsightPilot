import base64
import unittest

try:
    from fastapi.testclient import TestClient
    HAVE_FASTAPI = True
except ImportError:  # fastapi/httpx are listed in requirements; skip if not installed
    HAVE_FASTAPI = False

from tests.helpers import analyst


@unittest.skipUnless(HAVE_FASTAPI, "fastapi/httpx not installed")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from insightpilot import api
        api._state["analyst"] = analyst()
        cls.client = TestClient(api.app)

    def test_health(self):
        body = self.client.get("/api/health").json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("sales", body["tables"])

    def test_ask(self):
        body = self.client.post("/api/ask", json={"question": "total revenue by region"}).json()
        self.assertTrue(body["verified"])
        self.assertEqual(body["route"], "sql")

    def test_ask_validation(self):
        self.assertEqual(self.client.post("/api/ask", json={"question": ""}).status_code, 422)

    def test_search_modes(self):
        for mode in ("hybrid", "bm25", "embedding"):
            res = self.client.get("/api/search", params={"q": "refund for damaged items", "mode": mode})
            self.assertEqual(res.status_code, 200)
        self.assertEqual(self.client.get("/api/search", params={"q": "x", "mode": "bad"}).status_code, 422)

    def test_ingest_rejects_bad_input(self):
        good = base64.b64encode(b"a,b\n1,2\n").decode()
        self.assertEqual(self.client.post("/api/ingest", json={"filename": "x.pdf", "content_base64": good}).status_code, 400)
        self.assertEqual(self.client.post("/api/ingest", json={"filename": "x.csv", "content_base64": "!!!"}).status_code, 400)
        self.assertEqual(self.client.post(
            "/api/ingest", json={"filename": "x.csv", "content_base64": "A" * 7_000_000}
        ).status_code, 413)

    def test_ingest_sanitizes_cross_platform_path_traversal(self):
        content = base64.b64encode(b"city,sales\nAuditTown,13\n").decode()
        response = self.client.post(
            "/api/ingest", json={"filename": r"..\..\audit-safe.csv", "content_base64": content}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["source"], "audit-safe.csv")
        upload_dir = analyst().settings.upload_dir.resolve()
        saved_path = (upload_dir / "audit-safe.csv").resolve()
        self.assertEqual(saved_path.parent, upload_dir)
        self.assertTrue(saved_path.is_file())

    def test_ingest_csv_then_ask(self):
        csv = base64.b64encode(b"city,sales\nPune,10\nMumbai,30\n").decode()
        res = self.client.post("/api/ingest", json={"filename": "cities.csv", "content_base64": csv})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["table"], "cities")
        answer = self.client.post("/api/ask", json={"question": "total sales by city"}).json()
        self.assertIn("Mumbai", answer["answer"])
        report = self.client.get("/api/ingest/report/cities")
        self.assertEqual(report.status_code, 200)
        self.assertEqual(report.json()["table"], "cities")
        self.assertIn("null_pct", report.json()["columns"][0])

    def test_ingest_report_returns_404_for_unknown_table(self):
        self.assertEqual(self.client.get("/api/ingest/report/not_a_table").status_code, 404)

    def test_eval_summary_404_when_missing(self):
        from dataclasses import replace

        from insightpilot import api
        original = api._state["analyst"].settings
        try:
            api._state["analyst"].settings = replace(original, results_dir=original.upload_dir / "none")
            self.assertEqual(self.client.get("/api/eval/summary").status_code, 404)
        finally:
            api._state["analyst"].settings = original


if __name__ == "__main__":
    unittest.main()
