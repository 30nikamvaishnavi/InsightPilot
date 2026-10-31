"""Service layer used by the CLI, the API and the evaluation harness."""
from __future__ import annotations

import json
from pathlib import Path

from .agent.runner import Agent
from .config import Settings, get_settings
from .db import is_postgres
from .ingestion import LOADERS, get_schema, ingest_directory, ingest_file
from .retrieval import HybridRetriever, load_chunks
from .retrieval.embeddings import make_embedder
from .retrieval.vector_store import make_vector_store


class Analyst:
    def __init__(self, settings: Settings | None = None, use_langgraph: bool = True, explainer="auto") -> None:
        self.settings = settings or get_settings()
        database = self.settings.database_url or self.settings.db_path
        database_empty = not get_schema(database) if is_postgres(database) else not Path(database).exists()
        if database_empty and Path(self.settings.sample_dir).exists():
            for report in ingest_directory(self.settings.sample_dir, database):
                self._save_ingest_report(report)
        embedder = make_embedder(self.settings.embedder)
        self.retriever = HybridRetriever(
            load_chunks(self.settings.docs_dir),
            embedder=embedder,
            cache_dir=self.settings.embedding_cache_dir,
            vector_store=make_vector_store(self.settings.database_url, embedder.name),
        )
        self.agent = Agent(self.settings, self.retriever, explainer=explainer, use_langgraph=use_langgraph)

    def ask(self, question: str) -> dict:
        return self.agent.ask(question)

    def search(self, query: str, k: int = 5, mode: str = "hybrid") -> list[dict]:
        return self.retriever.search(query, k=k, mode=mode)

    def schema(self) -> dict:
        return get_schema(self.settings.database_url or self.settings.db_path)

    def ingest(self, path: str | Path) -> dict:
        report = ingest_file(path, self.settings.database_url or self.settings.db_path)
        self._save_ingest_report(report)
        return report

    def _save_ingest_report(self, report: dict) -> None:
        report_dir = self.settings.upload_dir / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        (report_dir / f"{report['table']}.json").write_text(json.dumps(report, default=str, indent=2), encoding="utf-8")

    def ingest_report(self, table: str) -> dict | None:
        if table not in self.schema():
            return None
        path = self.settings.upload_dir / "reports" / f"{table}.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def health(self) -> dict:
        return {
            "status": "ok",
            "engine": self.agent.engine,
            "mode": self.agent.mode,
            "llm_configured": self.settings.gemini_api_key is not None,
            "embedder": self.retriever.embedder.name,
            "tables": list(self.schema()),
            "supported_formats": sorted(LOADERS),
        }
