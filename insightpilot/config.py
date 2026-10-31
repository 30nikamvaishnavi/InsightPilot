"""Central settings. Everything can be overridden with environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Limits:
    """Hard limits that keep the agent bounded and safe."""

    max_steps: int = 6
    max_rows: int = 200
    max_question_chars: int = 500
    sql_timeout_s: float = 5.0


@dataclass(frozen=True)
class Settings:
    db_path: Path
    database_url: str | None
    docs_dir: Path
    sample_dir: Path
    eval_dir: Path
    trace_dir: Path
    results_dir: Path
    upload_dir: Path
    embedding_cache_dir: Path
    gemini_api_key: str | None
    gemini_model: str
    embedder: str
    limits: Limits


def get_settings() -> Settings:
    env = os.environ.get
    database_url = env("DATABASE_URL") or None
    if database_url and not database_url.lower().startswith(("postgresql://", "postgres://")):
        raise ValueError("DATABASE_URL must use postgresql:// or postgres://")
    embedder = (env("IP_EMBEDDER") or "lsa").lower()
    if embedder not in {"lsa", "sbert"}:
        raise ValueError("IP_EMBEDDER must be 'lsa' or 'sbert'")

    def path(name: str, default: Path) -> Path:
        return Path(env(name) or default)

    return Settings(
        db_path=path("IP_DB_PATH", ROOT / "data" / "insightpilot.db"),
        database_url=database_url,
        docs_dir=path("IP_DOCS_DIR", ROOT / "data" / "docs"),
        sample_dir=path("IP_SAMPLE_DIR", ROOT / "data" / "sample"),
        eval_dir=path("IP_EVAL_DIR", ROOT / "data" / "eval"),
        trace_dir=path("IP_TRACE_DIR", ROOT / "traces"),
        results_dir=path("IP_RESULTS_DIR", ROOT / "results"),
        upload_dir=path("IP_UPLOAD_DIR", ROOT / "data" / "uploads"),
        embedding_cache_dir=path("IP_EMBEDDING_CACHE_DIR", ROOT / "data" / "embedding-cache"),
        gemini_api_key=env("GEMINI_API_KEY") or None,
        gemini_model=env("GEMINI_MODEL") or "gemini-2.5-flash",
        embedder=embedder,
        limits=Limits(),
    )
