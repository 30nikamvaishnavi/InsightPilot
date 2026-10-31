import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from insightpilot.config import ROOT


class DefaultOptionalImportTests(unittest.TestCase):
    def test_default_analyst_never_imports_optional_packages(self):
        script = """
import builtins
real_import = builtins.__import__
blocked = ("psycopg", "pgvector", "sentence_transformers", "opentelemetry")
def guarded_import(name, *args, **kwargs):
    if any(name == package or name.startswith(package + ".") for package in blocked):
        raise AssertionError("optional import attempted by default: " + name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from insightpilot.config import get_settings
from insightpilot.service import Analyst
settings = get_settings()
assert settings.database_url is None
assert settings.embedder == "lsa"
analyst = Analyst(settings, use_langgraph=False)
answer = analyst.ask("total revenue by region")
assert answer["verified"] is True
assert analyst.agent.mode == "template"
"""
        with tempfile.TemporaryDirectory() as temp_dir:
            env = os.environ.copy()
            for name in (
                "DATABASE_URL", "GEMINI_API_KEY", "IP_EMBEDDER", "OTEL_TRACES_EXPORTER",
                "OTEL_SDK_DISABLED", "TRACE_INCLUDE_TEXT",
            ):
                env.pop(name, None)
            env["IP_DB_PATH"] = str(Path(temp_dir) / "default.db")
            env["IP_TRACE_DIR"] = str(Path(temp_dir) / "traces")
            env["IP_UPLOAD_DIR"] = str(Path(temp_dir) / "uploads")
            env["IP_EMBEDDING_CACHE_DIR"] = str(Path(temp_dir) / "embedding-cache")
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
