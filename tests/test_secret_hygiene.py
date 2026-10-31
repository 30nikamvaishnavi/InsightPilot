import re
import unittest

from insightpilot.config import ROOT


class SecretHygieneTests(unittest.TestCase):
    def test_environment_file_is_ignored(self):
        ignored = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".env", [line.strip() for line in ignored])

    def test_source_compose_and_trace_files_have_no_embedded_credentials(self):
        key_pattern = re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")
        password_pattern = re.compile(
            r"(?m)^\s*(?:POSTGRES_PASSWORD|GEMINI_API_KEY)\s*[:=]\s*[\"']?([^\s\"'#$][^\s\"'#]*)"
        )
        postgres_url_pattern = re.compile(r"postgres(?:ql)?://[^:/@\s]+:[^/@\s]+@", re.IGNORECASE)
        relevant_suffixes = {".py", ".yml", ".yaml", ".md", ".html", ".json", ".jsonl", ".log"}
        exclusions = {".venv", ".pytest_cache", ".ruff_cache", "__pycache__"}

        for path in ROOT.rglob("*"):
            if not path.is_file() or path.name == ".env" or exclusions.intersection(path.parts):
                continue
            if path.suffix.lower() not in relevant_suffixes:
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            self.assertIsNone(key_pattern.search(content), f"credential-like API key in {path}")
            self.assertIsNone(password_pattern.search(content), f"literal password/key assignment in {path}")
            for match in postgres_url_pattern.finditer(content):
                url = match.group()
                self.assertTrue(
                    "${POSTGRES_PASSWORD" in url or "$($env:POSTGRES_PASSWORD)" in url,
                    f"literal password in PostgreSQL URL in {path}",
                )


if __name__ == "__main__":
    unittest.main()
