import base64
import os
import unittest
import uuid
from unittest.mock import patch

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
        response = self.client.get("/api/health")
        body = response.json()
        self.assertEqual(body["status"], "ok")
        self.assertIn("sales", body["tables"])
        self.assertIn("public_demo", body)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])

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

    def test_public_demo_disables_ingest_and_traces_but_keeps_ask_and_search(self):
        content = base64.b64encode(b"a,b\n1,2\n").decode()
        with patch.dict(os.environ, {"PUBLIC_DEMO": "1"}):
            self.assertTrue(self.client.get("/api/health").json()["public_demo"])
            self.assertEqual(
                self.client.post(
                    "/api/ingest", json={"filename": "sample.csv", "content_base64": content}
                ).status_code,
                403,
            )
            self.assertEqual(self.client.get("/api/traces").status_code, 403)
            ip = f"demo-availability-{uuid.uuid4()}"
            ask_response = self.client.post(
                "/api/ask",
                json={"question": "total revenue by region"},
                headers={"X-Forwarded-For": ip},
            )
            self.assertEqual(ask_response.status_code, 200)
            search_response = self.client.get(
                "/api/search",
                params={"q": "refund policy"},
                headers={"X-Forwarded-For": ip},
            )
            self.assertEqual(search_response.status_code, 200)

    def test_rate_limit_returns_429_for_ask_and_search_using_first_forwarded_ip(self):
        from insightpilot import api

        with patch.object(api, "RATE_LIMIT_PER_MINUTE", 1):
            ask_ip = f"ask-rate-{uuid.uuid4()}"
            first_ask = self.client.post(
                "/api/ask",
                json={"question": "total revenue"},
                headers={"X-Forwarded-For": f"{ask_ip}, proxy-a"},
            )
            second_ask = self.client.post(
                "/api/ask",
                json={"question": "total revenue"},
                headers={"X-Forwarded-For": f"{ask_ip}, proxy-b"},
            )
            self.assertEqual(first_ask.status_code, 200)
            self.assertEqual(second_ask.status_code, 429)
            self.assertIn("Rate limit exceeded", second_ask.json()["detail"])

            search_ip = f"search-rate-{uuid.uuid4()}"
            first_search = self.client.get(
                "/api/search", params={"q": "refund"},
                headers={"X-Forwarded-For": f"{search_ip}, proxy-a"},
            )
            second_search = self.client.get(
                "/api/search", params={"q": "refund"},
                headers={"X-Forwarded-For": f"{search_ip}, proxy-b"},
            )
            self.assertEqual(first_search.status_code, 200)
            self.assertEqual(second_search.status_code, 429)


if __name__ == "__main__":
    unittest.main()
