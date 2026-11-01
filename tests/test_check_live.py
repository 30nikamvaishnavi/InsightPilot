import contextlib
import io
import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch

from scripts.check_live import run_checks


class LiveCheckTests(unittest.TestCase):
    def setUp(self):
        class Handler(BaseHTTPRequestHandler):
            health_requests = 0
            ask_requests = 0

            def do_GET(self):
                if self.path == "/api/health":
                    type(self).health_requests += 1
                    if type(self).health_requests == 1:
                        self.send_response(503)
                        self.end_headers()
                        return
                    self._respond(200, {"status": "ok", "public_demo": True})
                elif self.path == "/":
                    self._respond(200, {})
                elif self.path == "/api/traces":
                    self._respond(403, {})
                else:
                    self._respond(404, {})

            def do_POST(self):
                if self.path == "/api/ask":
                    type(self).ask_requests += 1
                    if type(self).ask_requests > 30:
                        self._respond(429, {"detail": "Rate limit exceeded"})
                    else:
                        self._respond(200, {"verified": True})
                elif self.path == "/api/ingest":
                    self._respond(403, {})
                else:
                    self._respond(404, {})

            def _respond(self, status, value):
                body = json.dumps(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                pass

        Handler.health_requests = 0
        Handler.ask_requests = 0
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.thread.join)
        self.addCleanup(self.server.shutdown)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"

    def test_live_check_retries_cold_start_and_checks_all_demo_endpoints(self):
        output = io.StringIO()
        with patch("scripts.check_live.time.sleep"), contextlib.redirect_stdout(output):
            result = run_checks(self.base_url)

        self.assertEqual(result, 0)
        self.assertIn("PASS health:", output.getvalue())
        self.assertIn("PASS home page:", output.getvalue())
        self.assertIn("PASS verified ask:", output.getvalue())
        self.assertIn("PASS ingest disabled:", output.getvalue())
        self.assertIn("PASS traces disabled:", output.getvalue())
        self.assertIn("PASS rate limit:", output.getvalue())
        self.assertEqual(self.server.RequestHandlerClass.health_requests, 2)


if __name__ == "__main__":
    unittest.main()
