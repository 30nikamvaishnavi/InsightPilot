"""Run the retrieval benchmark and the agent evaluation, then write results/.

    python -m insightpilot.eval.run_eval

Outputs (all numbers come from this run, none are hand-written):
    results/eval_summary.json
    results/agent_cases.csv
"""
from __future__ import annotations

import csv
import json
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from ..agent.verifier import extract_numbers
from ..config import get_settings
from ..retrieval import evaluate_retrieval, load_queries
from ..retrieval.chunking import load_chunks
from ..retrieval.embeddings import make_embedder
from ..retrieval.hybrid import HybridRetriever
from ..retrieval.vector_store import make_vector_store
from ..service import Analyst
from .cases import CASES, load_truth_frames

DEFAULT_TOLERANCE = 0.0051


def _numbers_present(answer: str, expected: list[float], tolerance: float) -> bool:
    found = extract_numbers(answer)
    return all(any(abs(f - float(e)) <= tolerance for f in found) for e in expected)


def run(write: bool = True) -> dict:
    settings = get_settings()
    with tempfile.TemporaryDirectory() as tmp:
        eval_settings = replace(settings, db_path=Path(tmp) / "eval.db", trace_dir=Path(tmp) / "traces")
        analyst = Analyst(eval_settings)
        frames = load_truth_frames()

        queries = load_queries(settings.eval_dir / "retrieval_queries.jsonl")
        retrieval = evaluate_retrieval(analyst.retriever, queries)
        retrieval_by_embedder = {analyst.retriever.embedder.name: retrieval}
        if settings.embedder == "sbert":
            lsa_embedder = make_embedder("lsa")
            lsa = HybridRetriever(
                load_chunks(settings.docs_dir), embedder=lsa_embedder,
                cache_dir=settings.embedding_cache_dir,
                vector_store=make_vector_store(settings.database_url, lsa_embedder.name),
            )
            retrieval_by_embedder[lsa.embedder.name] = evaluate_retrieval(lsa, queries)

        rows = []
        for case in CASES:
            out = analyst.ask(case["question"])
            route_ok = out["route"] == case["route"]
            if "numbers" in case:
                answer_ok = _numbers_present(out["answer"], case["numbers"](frames), case.get("tolerance", DEFAULT_TOLERANCE))
            elif "text" in case:
                answer_ok = case["text"].lower() in out["answer"].lower()
            else:
                answer_ok = out["blocked"] == case.get("blocked", False)
            rows.append({
                "id": case["id"], "category": case["category"], "question": case["question"],
                "expected_route": case["route"], "actual_route": out["route"],
                "route_ok": route_ok, "answer_ok": answer_ok, "verified": out["verified"],
                "response_source": out["response_source"], "latency_ms": out["latency_ms"],
                "answer": out["answer"].replace("\n", " | "),
            })

        total = len(rows)
        by_category: dict[str, dict] = {}
        for row in rows:
            bucket = by_category.setdefault(row["category"], {"cases": 0, "passed": 0})
            bucket["cases"] += 1
            bucket["passed"] += int(row["route_ok"] and row["answer_ok"])

        summary = {
            "metadata": {
                "run_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "engine": analyst.agent.engine,
                "mode": analyst.agent.mode,
                "llm_model": settings.gemini_model if analyst.agent.mode == "llm" else None,
                "embedder": analyst.retriever.embedder.name,
            },
            "agent": {
                "cases": total,
                "route_accuracy": round(sum(r["route_ok"] for r in rows) / total, 4),
                "answer_accuracy": round(sum(r["answer_ok"] for r in rows) / total, 4),
                "verified_rate": round(sum(r["verified"] for r in rows) / total, 4),
                "avg_latency_ms": round(sum(r["latency_ms"] for r in rows) / total, 2),
                "by_category": by_category,
                "failed_cases": [r["id"] for r in rows if not (r["route_ok"] and r["answer_ok"])],
            },
            "retrieval": retrieval,
            "retrieval_by_embedder": retrieval_by_embedder,
        }

    if write:
        settings.results_dir.mkdir(parents=True, exist_ok=True)
        (settings.results_dir / "eval_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        with open(settings.results_dir / "agent_cases.csv", "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return summary


def main() -> int:
    summary = run()
    agent, meta = summary["agent"], summary["metadata"]
    print(f"Run {meta['run_at']} | engine={meta['engine']} | mode={meta['mode']} | embedder={meta['embedder']}")
    print(f"Agent: {agent['cases']} cases | route accuracy {agent['route_accuracy']:.1%} | "
          f"answer accuracy {agent['answer_accuracy']:.1%} | verified {agent['verified_rate']:.1%}")
    for name, stats in agent["by_category"].items():
        print(f"  {name:<13} {stats['passed']}/{stats['cases']}")
    if agent["failed_cases"]:
        print("  Failed:", ", ".join(agent["failed_cases"]))
    for mode, stats in summary["retrieval"]["modes"].items():
        print(f"Retrieval {mode:<9} recall@1 {stats['recall@1']:.2f} | recall@3 {stats['recall@3']:.2f} | "
              f"recall@5 {stats['recall@5']:.2f} | MRR {stats['mrr']:.2f}")
    print("Wrote results/eval_summary.json and results/agent_cases.csv")
    return 0 if not agent["failed_cases"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
