"""The public Agent: runs the graph, shapes the response and writes the trace."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

from ..config import Settings
from ..db import dialect_for
from ..retrieval.hybrid import HybridRetriever
from .graph import build_graph
from .llm_hook import resolve_explainer
from .nodes import AgentContext, make_nodes
from .planner import RulePlanner
from .tracing import write_trace


class Agent:
    def __init__(self, settings: Settings, retriever: HybridRetriever, explainer="auto",
                 use_langgraph: bool = True, planner=None, write_traces: bool = True) -> None:
        self.settings = settings
        self.write_traces = write_traces
        database = settings.database_url or settings.db_path
        self.context = AgentContext(
            settings, retriever, planner or RulePlanner(dialect_for(database)), resolve_explainer(settings, explainer)
        )
        from .tracing import configure_otel

        configure_otel()
        self.graph = build_graph(make_nodes(self.context), use_langgraph=use_langgraph)

    @property
    def engine(self) -> str:
        return self.graph.engine

    @property
    def mode(self) -> str:
        return "llm" if self.context.explainer is not None else "template"

    def ask(self, question: str) -> dict:
        started = time.perf_counter()
        state = self.graph.invoke({"question": question, "trace": [], "steps": 0})
        result = state.get("result") or {}
        plan = state.get("plan_data") or {}
        output = {
            "id": uuid.uuid4().hex[:12],
            "question": question,
            "answer": state.get("answer", ""),
            "route": state.get("route"),
            "blocked": bool(state.get("blocked")),
            "block_reason": state.get("block_reason"),
            "verified": bool(state.get("verified")),
            "verification": state.get("verification"),
            "response_source": state.get("response_source"),
            "label": plan.get("label"),
            "sql": result.get("sql") or (None if state.get("blocked") else plan.get("sql")),
            "columns": result.get("columns"),
            "rows": (result.get("rows") or [])[:50],
            "computed": state.get("computed"),
            "sources": [{"chunk_id": d["chunk_id"], "doc": d["doc"], "heading": d["heading"], "score": d["score"]}
                        for d in (state.get("docs") or [])],
            "trace": state.get("trace", []),
            "engine": self.engine,
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
        }
        if self.write_traces:
            trace_record = {**output, "ts": datetime.now(timezone.utc).isoformat()}
            if (
                os.environ.get("PUBLIC_DEMO", "").strip() == "1"
                and os.environ.get("PUBLIC_DEMO_TRACE_QUESTIONS", "").strip() != "1"
            ):
                trace_record.pop("question", None)
            write_trace(self.settings.trace_dir, trace_record)
        return output
