"""Graph nodes. Each node is a plain function: state in, partial state update out."""
from __future__ import annotations

import os
import re
import time
from contextlib import nullcontext
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings
from ..retrieval.hybrid import HybridRetriever
from ..tools.sql_guard import SqlError, run_sql
from .planner import RulePlanner, SchemaContext
from .responder import compute, render_template
from .verifier import check_numbers, collect_facts

INJECTION = re.compile(
    r"(ignore (all |any |the )?(previous|prior|above) (instructions|rules)|system prompt|reveal your (prompt|instructions)|"
    r"developer message|jailbreak|act as (an? )?(unrestricted|dan)\b)",
    re.IGNORECASE,
)
WRITE_INTENT = re.compile(
    r"\b(drop|delete|truncate|alter)\s+(table|from|database|all)\b|\binsert\s+into\b|\bupdate\s+\w+\s+set\b|\bdelete all\b",
    re.IGNORECASE,
)
COUNTED = {"guard", "plan", "execute"}  # nodes that count against max_steps
SAFE_FAILURE = "I couldn't verify the numbers in the answer, so I'm not showing it. Please rephrase or check the SQL in the trace."


@dataclass
class AgentContext:
    settings: Settings
    retriever: HybridRetriever
    planner: RulePlanner
    explainer: Any = None


def _summarise(name: str, state: dict, update: dict) -> dict:
    merged = {**state, **update}
    if name == "guard":
        return {"blocked": bool(update.get("blocked")), "reason": update.get("block_reason")}
    if name == "plan":
        plan = merged.get("plan_data") or {}
        return {"route": plan.get("route"), "table": plan.get("table"), "sql": plan.get("sql")}
    if name == "execute":
        result = merged.get("result") or {}
        return {"rows": len(result.get("rows", [])), "docs": len(merged.get("docs") or []), "route": merged.get("route")}
    if name == "respond":
        return {"source": update.get("response_source")}
    if name == "verify":
        return {**(merged.get("verification") or {}), "verified": merged.get("verified")}
    return {}


def traced(name: str, fn: Callable[[dict], dict], ctx: AgentContext) -> Callable[[dict], dict]:
    def wrapper(state: dict) -> dict:
        started = time.perf_counter()
        steps = state.get("steps", 0)
        status = "ok"
        span_context = nullcontext()
        trace = None
        if os.environ.get("OTEL_TRACES_EXPORTER", "").strip().lower() == "otlp":
            from opentelemetry import trace as otel_trace

            trace = otel_trace
            span_context = trace.get_tracer("insightpilot.agent").start_as_current_span(f"agent.{name}")
        with span_context as span:
            if name in COUNTED and steps >= ctx.settings.limits.max_steps and not state.get("blocked"):
                update = {"blocked": True, "route": "limit",
                          "block_reason": f"step limit reached ({ctx.settings.limits.max_steps} steps)"}
                status = "limit"
            else:
                try:
                    update = fn(state) or {}
                except Exception as exc:  # keep the agent alive; surface a safe message
                    update = {"blocked": True, "route": "blocked",
                              "block_reason": f"internal error ({type(exc).__name__})"}
                    status = "error"
            if span is not None:
                merged = {**state, **update}
                span.set_attribute("agent.node", name)
                span.set_attribute("agent.route", str(merged.get("route", "unknown")))
                result = merged.get("result") or {}
                span.set_attribute("agent.row_count", len(result.get("rows", [])))
                span.set_attribute("agent.verified", bool(merged.get("verified", False)))
                span.set_attribute("agent.response_source", str(merged.get("response_source", "not_set")))
                if status == "error":
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
        span = {"node": name, "status": status, "ms": round((time.perf_counter() - started) * 1000, 2),
                "summary": _summarise(name, state, update)}
        out = dict(update)
        out["trace"] = [*state.get("trace", []), span]
        if name in COUNTED:
            out["steps"] = steps + 1
        return out

    return wrapper


def make_nodes(ctx: AgentContext) -> dict[str, Callable[[dict], dict]]:
    limits = ctx.settings.limits

    def guard(state: dict) -> dict:
        question = (state.get("question") or "").strip()
        if not question:
            return {"blocked": True, "route": "blocked", "block_reason": "please type a question"}
        if len(question) > limits.max_question_chars:
            return {"blocked": True, "route": "blocked",
                    "block_reason": f"the question is longer than {limits.max_question_chars} characters"}
        if INJECTION.search(question):
            return {"blocked": True, "route": "blocked", "block_reason": "this looks like an attempt to override my instructions"}
        if WRITE_INTENT.search(question):
            return {"blocked": True, "route": "blocked", "block_reason": "this is a request to change or delete data"}
        return {}

    def plan(state: dict) -> dict:
        database = ctx.settings.database_url or ctx.settings.db_path
        schema = SchemaContext.from_db(database)
        chosen = ctx.planner.plan(state["question"], schema, default_limit=50)
        return {"route": chosen.route, "plan_data": chosen.to_dict(), "schema_summary": schema.summary()}

    def execute(state: dict) -> dict:
        data = state["plan_data"]
        route = data["route"]
        if route in ("sql", "trend", "correlation"):
            try:
                database = ctx.settings.database_url or ctx.settings.db_path
                result = run_sql(database, data["sql"], limits.max_rows, limits.sql_timeout_s)
            except SqlError as exc:
                return {"blocked": True, "route": "blocked", "block_reason": f"the query was rejected ({exc})"}
            return {"result": result, "computed": compute(data, result)}
        if route == "docs":
            hits = [h for h in ctx.retriever.search(state["question"], k=3) if h["relevant"]]
            if not hits:
                return {"route": "unknown", "docs": [],
                        "plan_data": {**data, "note": "I couldn't find that in the data or the documentation."}}
            return {"docs": hits}
        return {}

    def respond(state: dict) -> dict:
        template = render_template(state)
        update = {"fallback": template, "draft": template, "response_source": "template"}
        if ctx.explainer is not None and not state.get("blocked") and state.get("route") in ("sql", "trend", "correlation", "docs"):
            result = state.get("result") or {}
            text = ctx.explainer.explain({
                "question": state["question"],
                "label": (state.get("plan_data") or {}).get("label"),
                "columns": result.get("columns"),
                "rows": (result.get("rows") or [])[:25],
                "computed": state.get("computed"),
                "documentation": [d["text"] for d in (state.get("docs") or [])],
            })
            if text:
                update.update(draft=text, response_source="llm")
        return update

    def verify(state: dict) -> dict:
        facts = collect_facts(state.get("question"), state.get("plan_data"), state.get("result"), state.get("computed"),
                              state.get("docs"), state.get("block_reason"), state.get("schema_summary"))
        draft = check_numbers(state["draft"], facts)
        if draft["ok"]:
            return {"answer": state["draft"], "verified": True,
                    "verification": {"checked": draft["checked"], "unsupported": [], "llm_rejected": False}}
        rejected = state.get("response_source") == "llm"
        fallback = check_numbers(state["fallback"], facts)
        if fallback["ok"]:
            return {"answer": state["fallback"], "response_source": "template", "verified": True,
                    "verification": {"checked": fallback["checked"], "unsupported": [], "llm_rejected": rejected,
                                     "rejected_numbers": draft["unsupported"]}}
        return {"answer": SAFE_FAILURE, "response_source": "template", "verified": False,
                "verification": {"checked": fallback["checked"], "unsupported": fallback["unsupported"], "llm_rejected": rejected}}

    return {name: traced(name, fn, ctx) for name, fn in
            {"guard": guard, "plan": plan, "execute": execute, "respond": respond, "verify": verify}.items()}
