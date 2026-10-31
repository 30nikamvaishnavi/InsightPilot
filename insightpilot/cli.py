"""Command line interface: ask questions, search the docs, ingest files.

    python -m insightpilot.cli ask "total revenue by region"
    python -m insightpilot.cli search "refund for damaged items"
    python -m insightpilot.cli ingest path/to/file.csv
"""
from __future__ import annotations

import argparse
import json

from .service import Analyst


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="insightpilot")
    sub = parser.add_subparsers(dest="command", required=True)
    ask = sub.add_parser("ask", help="ask a question about the data")
    ask.add_argument("question")
    ask.add_argument("--trace", action="store_true", help="print the step trace")
    search = sub.add_parser("search", help="search the documentation")
    search.add_argument("query")
    search.add_argument("-k", type=int, default=3)
    search.add_argument("--mode", choices=["hybrid", "bm25", "embedding"], default="hybrid")
    ingest = sub.add_parser("ingest", help="load a CSV/TSV/JSON/JSONL/XLSX/Parquet/pipe-delimited TXT file")
    ingest.add_argument("path")
    ingest.add_argument("--report", action="store_true", help="print the full validation and profile report")
    args = parser.parse_args(argv)

    analyst = Analyst()
    if args.command == "ask":
        out = analyst.ask(args.question)
        print(out["answer"])
        if out.get("sql"):
            print(f"\nSQL: {out['sql']}")
        print(f"\n[route={out['route']} verified={out['verified']} source={out['response_source']} {out['latency_ms']} ms]")
        if args.trace:
            for span in out["trace"]:
                print(f"  {span['node']:<8} {span['status']:<5} {span['ms']:>7} ms  {json.dumps(span['summary'], default=str)}")
    elif args.command == "search":
        for hit in analyst.search(args.query, k=args.k, mode=args.mode):
            print(f"{hit['score']:.4f}  {hit['chunk_id']}\n        {hit['text'][:160]}")
    else:
        report = analyst.ingest(args.path)
        print(json.dumps(report if args.report else {k: v for k, v in report.items() if k != "columns"}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
