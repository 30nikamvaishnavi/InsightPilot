# Evaluation

Run the evaluation with:

```powershell
python -m insightpilot.eval.run_eval
```

The harness writes the metrics from that run to `results/eval_summary.json` and row-level agent cases to `results/agent_cases.csv`. The summary records the UTC run time, execution engine, answer mode, configured embedder, and agent metrics. Retrieval results include recall@k and MRR for every retrieval mode, grouped by embedder under `retrieval_by_embedder`. With the default embedder, that is the offline LSA run. When `IP_EMBEDDER=sbert` is selected, the harness evaluates both sentence-transformers and LSA.

## Audit comparison: calculation-to-formula expansion

The BM25 query-term map in `retrieval/hybrid.py` applies to every search query: when tokenization yields `calculat` or `calculation`, it adds `formula`. The embedding query is unchanged. This is a deliberately narrow synonym map, not a lookup for one exact benchmark string; it targets calculation/formula vocabulary and can affect BM25-only and hybrid ranking.

The two `python -m insightpilot.eval.run_eval` runs below used the same default offline configuration and 103 labelled queries on 2026-10-31. The second run temporarily used an empty synonym map. Values are the exact four-decimal metrics read from each generated summary:

| Mode | Expansion | Recall@1 | Recall@3 | Recall@5 | MRR |
|---|---|---:|---:|---:|---:|
| Hybrid | On | 0.6117 | 0.8835 | 0.9126 | 0.7382 |
| Hybrid | Off | 0.6019 | 0.8835 | 0.9126 | 0.7317 |
| BM25 | On | 0.5825 | 0.8155 | 0.8835 | 0.7037 |
| BM25 | Off | 0.5728 | 0.8155 | 0.8835 | 0.6989 |
| Embedding | On | 0.6019 | 0.8350 | 0.8738 | 0.7126 |
| Embedding | Off | 0.6019 | 0.8350 | 0.8738 | 0.7126 |

Across the labelled queries, the expansion changed the top-five lists for four queries in each of hybrid and BM25; reciprocal rank improved for one query (`how is revenue calculated`), worsened for none, and embedding rankings did not change. With expansion disabled, the agent evaluation also failed its `docs_formula` case; with it enabled, all 21 cases passed. This is a narrow, measured benefit, not evidence that the map improves general retrieval. The small synonym map and its focused retrieval test are retained. The metrics are run snapshots, not expected constants; `results/eval_summary.json` records the most recent enabled run and should be regenerated after changes.

## Retrieval benchmark

`data/eval/retrieval_queries.jsonl` maps each natural-language query to one or more stable chunk IDs from `data/docs/`. The set includes direct questions and hard paraphrases. The retrieval tests verify every expected ID exists and exercise hybrid, BM25-only, and embedding-only ranking.

The corpus was expanded with four topical documents (`analysis_playbook.md`, `data_quality.md`, `operations_reference.md`, and `support_workflows.md`) and labelled queries to cover their distinct guidance and the requested paraphrase cases. These documents add information that was not represented in the original corpus; however, the query labels were authored against the same known corpus rather than gathered from independent users. Results therefore characterize this curated benchmark and may favor its terminology and chunk boundaries. During the audit, a sentence added to `revenue_definition.md` solely to improve a retrieval test's wording match was removed; evaluation results were regenerated without that sentence.

Recall@k is the fraction of labelled queries with at least one expected chunk in the first k results. Mean reciprocal rank (MRR) averages the reciprocal rank of the first expected chunk; queries without a hit in the ranked results contribute zero. `evaluate_retrieval` reports recall at its configured cutoffs, MRR, and queries with no expected hit in the returned top-k.

The `relevant` flag in individual search results uses lexical evidence, not embedding similarity alone. The benchmark ranks by the requested mode, while relevance is a separate lexical check used by documentation answers. These are intentionally distinct measures.

## Agent cases

`insightpilot/eval/cases.py` covers aggregate and grouped SQL, multiple ingested formats, trends, correlation, documentation, off-topic questions, prompt injection, and write intent. Numeric ground truth is computed from the sample source files with pandas, independently of the agent. Cases report route correctness, answer correctness, numeric verification, response source, and latency. These checks do not prove all possible phrasings are handled correctly.

## Optional integration tests

The default test suite does not require PostgreSQL or an OTLP collector. PostgreSQL integration tests skip unless `DATABASE_URL` is a PostgreSQL URL; they issue a read-only query and inspect schema access. OpenTelemetry in-memory-exporter tests skip unless the optional SDK/exporter package is installed. Sentence-transformers is not downloaded by default; the default retrieval tests use offline LSA.

## Honest limitations

- The cases were written with the rule planner and document corpus. Passing them demonstrates those supported patterns, not broad analytical correctness.
- Synthetic data and a compact documentation set do not represent production volume, data quality, or domain language.
- Retrieval labels encode human judgments for this corpus. Paraphrase quality and label completeness can affect the measurements.
- Recall and MRR evaluate ranking against those labels; they do not establish that the assistant's generated prose is fully correct.
- Latency depends on the machine, database, model cache, and optional network services. Do not compare runs without controlling those conditions.
- A high numeric verification rate means answer numbers were grounded in available facts. The verifier does not validate the business meaning of the answer.
- LLM mode requires an API key and network access. The no-key template mode is the reproducible offline default.
- PostgreSQL, pgvector, sentence-transformers, and OTLP export are implemented and unit-tested with mocks; not verified against a live service in this environment.
