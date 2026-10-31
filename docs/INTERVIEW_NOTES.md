# How to talk about this project

Be ready to explain every part in your own words. Suggested walk-through (2 minutes):

1. **Problem**: LLMs invent numbers, so a data analyst must compute them with code and check them.
2. **Pipeline**: ingest files, clean and validate, store in SQLite; split docs into chunks.
3. **Retrieval**: BM25 + embeddings fused with RRF; measured with recall@k and MRR.
4. **Agent**: guard, plan, execute, respond, verify as a LangGraph graph with step limits and traces.
5. **Safety**: read-only SQL, validation, row cap and timeout, prompt-injection and write-intent blocking.
6. **Evaluation**: pandas ground truth, per-category results, and what the cases do not prove.

Questions you may get, and where to look:
- Why RRF instead of adding scores? (`retrieval/hybrid.py`, scores are on different scales)
- What happens if the LLM invents a number? (`agent/verifier.py`, `tests/test_agent.py::LlmGuardTests`)
- How would you add PostgreSQL or a new file type? (`docs/APPROACH.md`)
- What are the weaknesses? (`README.md` Limits, `docs/EVALUATION.md` Honest limits)

Say plainly what you ran and what you did not (for example, run it yourself before the interview and be ready to demo `python -m insightpilot.cli ask ... --trace`).
