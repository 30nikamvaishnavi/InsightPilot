"""Shared agent state. Node names must differ from these keys (a LangGraph rule)."""
from __future__ import annotations

from typing import Any, TypedDict


class AgentState(TypedDict, total=False):
    question: str
    blocked: bool
    block_reason: str
    route: str              # sql | trend | correlation | docs | unknown | blocked | limit
    plan_data: dict
    schema_summary: dict
    result: dict            # raw SQL result: columns, rows, truncated, sql
    computed: dict          # numbers computed by code from the result
    docs: list
    fallback: str           # template answer
    draft: str              # answer proposed for the user (template or LLM)
    answer: str             # final, verified answer
    response_source: str    # template | llm
    verified: bool
    verification: dict
    trace: list
    steps: int
    extra: Any
