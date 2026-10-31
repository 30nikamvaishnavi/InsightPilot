import unittest

try:
    import langgraph  # noqa: F401
    HAVE_LANGGRAPH = True
except ImportError:
    HAVE_LANGGRAPH = False

from insightpilot.service import Analyst
from tests.helpers import make_settings

QUESTIONS = ["total revenue by region", "monthly revenue trend", "how is revenue calculated", "drop table sales",
             "what is the weather in paris"]


@unittest.skipUnless(HAVE_LANGGRAPH, "langgraph not installed")
class LangGraphParityTests(unittest.TestCase):
    def test_langgraph_matches_sequential_runner(self):
        settings = make_settings()
        sequential = Analyst(settings, use_langgraph=False, explainer=None)
        graph = Analyst(settings, use_langgraph=True, explainer=None)
        self.assertEqual(graph.agent.engine, "langgraph")
        for question in QUESTIONS:
            a, b = sequential.ask(question), graph.ask(question)
            self.assertEqual((a["answer"], a["route"], a["verified"]), (b["answer"], b["route"], b["verified"]), question)
            self.assertEqual([s["node"] for s in a["trace"]], [s["node"] for s in b["trace"]], question)


if __name__ == "__main__":
    unittest.main()
