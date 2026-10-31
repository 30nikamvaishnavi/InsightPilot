import os
import unittest
from unittest.mock import patch

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    HAVE_OTEL = True
except ImportError:
    HAVE_OTEL = False

from insightpilot.agent.nodes import AgentContext, traced
from insightpilot.agent.planner import RulePlanner
from tests.helpers import analyst, make_settings


@unittest.skipUnless(HAVE_OTEL, "install requirements-otel.txt")
class OpenTelemetryTests(unittest.TestCase):
    def test_agent_node_emits_only_safe_span_attributes(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        context = AgentContext(make_settings(), analyst().retriever, RulePlanner())
        node = traced("verify", lambda _state: {"verified": True, "response_source": "template"}, context)
        unsafe_values = ["private question", "SELECT revenue FROM sales WHERE region = 'secret'", "secret-row-value"]
        state = {
            "question": unsafe_values[0],
            "route": "sql",
            "plan_data": {"sql": unsafe_values[1]},
            "result": {"rows": [[unsafe_values[2]]]},
        }
        with patch.object(trace, "get_tracer", provider.get_tracer), patch.dict(os.environ, {"OTEL_TRACES_EXPORTER": "otlp"}):
            node(state)
        spans = exporter.get_finished_spans()
        self.assertEqual(len(spans), 1)
        attrs = spans[0].attributes
        self.assertEqual(attrs["agent.node"], "verify")
        self.assertEqual(attrs["agent.route"], "sql")
        self.assertEqual(attrs["agent.row_count"], 1)
        self.assertTrue(attrs["agent.verified"])
        self.assertEqual(attrs["agent.response_source"], "template")
        self.assertEqual(set(attrs), {
            "agent.node", "agent.route", "agent.row_count", "agent.verified", "agent.response_source"
        })
        self.assertFalse(any(value in str(attrs) for value in unsafe_values))

    def test_text_environment_flag_never_adds_question_to_span(self):
        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        context = AgentContext(make_settings(), analyst().retriever, RulePlanner())
        node = traced("guard", lambda _state: {}, context)
        env = {"OTEL_TRACES_EXPORTER": "otlp", "TRACE_INCLUDE_TEXT": "1"}
        with patch.object(trace, "get_tracer", provider.get_tracer), patch.dict(os.environ, env):
            node({"question": "private question"})
        self.assertNotIn("agent.question", exporter.get_finished_spans()[0].attributes)


if __name__ == "__main__":
    unittest.main()
