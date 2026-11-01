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
        self.assertIn('const isFastApiOrigin = pageUrl.protocol === "https:"', page)
        self.assertIn('pageUrl.origin : "http://127.0.0.1:8000"', page)
        self.assertIn("window.location.origin !== API_ORIGIN", page)
        self.assertIn("error.requestedUrl = requestedUrl", page)
        self.assertIn("API URL: ${requestedUrl}", page)
        self.assertIn('id="retry-backend"', page)
        self.assertIn('>Retry</button>', page)
        self.assertIn("HEALTH_POLL_INTERVAL_MS = 5000", page)
        self.assertIn("window.setInterval", page)
        self.assertIn("startHealthPolling();", page)
        self.assertIn("document.addEventListener(\"visibilitychange\"", page)
        self.assertIn("document.hidden", page)
        self.assertIn("refreshBackendData()", page)
        self.assertIn('api("/api/schema")', page)
        self.assertIn("health.status !== \"ok\"", page)
        self.assertIn("Waking up the server, this can take up to a minute.", page)
        self.assertIn('id="public-demo-notice"', page)
        self.assertIn("Uploads are disabled in the public demo", page)
        self.assertIn("health.public_demo === true", page)
        self.assertIn(
            'const API_START_COMMAND = ".\\\\scripts\\\\run_api.ps1"', page
        )
        self.assertNotIn("innerHTML", page)
        self.assertIn("textContent", page)

    def test_api_start_script_activates_existing_venv_and_binds_localhost(self):
        script = (ROOT / "scripts" / "run_api.ps1").read_text(encoding="utf-8")
        self.assertRegex(script, r"(?s)param\s*\(.*?\[int\]\$Port\s*=\s*8000")
        self.assertIn("Get-NetTCPConnection -LocalPort $Port -State Listen", script)
        self.assertIn("insightpilot\\.api:app", script)
        self.assertIn('Read-Host "Stop it and restart? (y/N)"', script)
        self.assertIn("Try another port", script)
        self.assertIn(".\\scripts\\run_api.ps1 -Port 8001", script)
        self.assertIn(".venv\\Scripts\\Activate.ps1", script)
        self.assertIn("if (Test-Path $activateScript)", script)
        self.assertIn('http://127.0.0.1:$Port/', script)
        self.assertIn(
            "python -m uvicorn insightpilot.api:app --host 127.0.0.1 --port $Port", script
        )

    def test_render_container_uses_port_and_excludes_secrets(self):
        dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
        dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")
        render = (ROOT / "render.yaml").read_text(encoding="utf-8")
        self.assertIn("${PORT:-8000}", dockerfile)
        self.assertIn("--host 0.0.0.0", dockerfile)
        self.assertIn("USER appuser", dockerfile)
        self.assertIn("chown -R appuser:appuser /app/data/uploads /app/traces", dockerfile)
        self.assertIn("HEALTHCHECK", dockerfile)
        self.assertIn("-r requirements.txt", dockerfile)
        self.assertIn(".env", dockerignore)
        self.assertIn("runtime: docker", render)
        self.assertIn("healthCheckPath: /api/health", render)
        self.assertIn('value: "1"', render)


if __name__ == "__main__":
    unittest.main()
