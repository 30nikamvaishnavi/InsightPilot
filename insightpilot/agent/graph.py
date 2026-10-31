"""Wire the nodes into a LangGraph StateGraph (or an equivalent sequential runner).

Both runners call exactly the same node functions and use the same routing, so the
behaviour is identical; LangGraph is used automatically when it is installed.
"""
from __future__ import annotations

from typing import Callable

from .state import AgentState


def route_after_guard(state: dict) -> str:
    return "respond" if state.get("blocked") else "plan"


def route_after_plan(state: dict) -> str:
    return "respond" if state.get("blocked") or state.get("route") == "unknown" else "execute"


class SequentialRunner:
    engine = "sequential"

    def __init__(self, nodes: dict[str, Callable[[dict], dict]]) -> None:
        self.nodes = nodes

    def invoke(self, state: dict) -> dict:
        state = dict(state)

        def run(name: str) -> None:
            state.update(self.nodes[name](state))

        run("guard")
        if route_after_guard(state) == "plan":
            run("plan")
            if route_after_plan(state) == "execute":
                run("execute")
        run("respond")
        run("verify")
        return state


class LangGraphRunner:
    engine = "langgraph"

    def __init__(self, app) -> None:
        self.app = app

    def invoke(self, state: dict) -> dict:
        return self.app.invoke(state)


def build_graph(nodes: dict[str, Callable[[dict], dict]], use_langgraph: bool = True):
    if use_langgraph:
        try:
            from langgraph.graph import END, StateGraph
        except ImportError:
            return SequentialRunner(nodes)
        graph = StateGraph(AgentState)
        for name, fn in nodes.items():
            graph.add_node(name, fn)
        graph.set_entry_point("guard")
        graph.add_conditional_edges("guard", route_after_guard, {"plan": "plan", "respond": "respond"})
        graph.add_conditional_edges("plan", route_after_plan, {"execute": "execute", "respond": "respond"})
        graph.add_edge("execute", "respond")
        graph.add_edge("respond", "verify")
        graph.add_edge("verify", END)
        return LangGraphRunner(graph.compile())
    return SequentialRunner(nodes)
