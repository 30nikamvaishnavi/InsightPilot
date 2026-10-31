# InsightPilot

InsightPilot is a small, verifiable AI data analyst. SQL and Python compute the numbers; `insightpilot/agent/verifier.py` checks the response before it is shown. A language model is optional and can only explain computed results. The default setup uses SQLite, offline LSA embeddings, template answers, and local JSONL traces; it needs no API key or database service.

## Features

| Capability | Implementation |
|---|---|
| Ingestion and profiling | CSV, TSV, JSON, JSONL, Excel, Parquet, and pipe-delimited TXT loaders in `insightpilot/ingestion/` |
| Retrieval | BM25 plus vector similarity, fused with Reciprocal Rank Fusion |
| Embeddings | Offline LSA by default; optional cached sentence-transformers vectors |
| Agent | Guard, schema-aware plan, execute, respond, verify; LangGraph with a sequential fallback |
| SQL safety | Schema-derived identifiers and values, `validate_sql`, read-only execution, row cap, and timeout |
| Databases | SQLite by default; optional PostgreSQL selected by `DATABASE_URL` |
| Traces | Local JSONL by default; optional OpenTelemetry OTLP spans |
| Interfaces | CLI, FastAPI service, and responsive browser UI |
| Evaluation | Re-runnable agent and retrieval reports written to `results/` |

## Install

Use Python 3.12 for the project environment:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-dev.txt
```

Run lint and tests:

```powershell
ruff check .
python -m pytest -q
```

Run a CLI question, search, or ingest:

```powershell
python -m insightpilot.cli ask "total revenue by region" --trace
python -m insightpilot.cli search "refund for a damaged product"
python -m insightpilot.cli ingest path\to\file.parquet --report
```

The ingestion report includes inferred types, null percentages, repeated-value counts, and cleaning notes. Supported input formats are also available through `register_loader` in `insightpilot/ingestion/loaders.py`.

## Run the API and web UI

```powershell
uvicorn insightpilot.api:app --reload
```

Open `http://localhost:8000` for Chat, Data, Evaluation, and Traces. API documentation is at `http://localhost:8000/docs`. If the service is unreachable, the UI explicitly reports that the backend is offline; it does not fabricate answers or metrics.

## Docker

The default Compose setup starts the API without PostgreSQL:

```powershell
docker compose up --build
```

To start the optional PostgreSQL/pgvector service and API, use the override:

```powershell
$env:POSTGRES_PASSWORD = Read-Host "Choose a local PostgreSQL password"
docker compose -f docker-compose.yml -f docker-compose.postgres.yml up --build
```

The override waits for the PostgreSQL health check and configures the API to use the service. Use managed secrets outside local development. With PostgreSQL selected, install its driver and vector extension support. For a CLI process running on the host while the Compose database is up:

```powershell
python -m pip install -r requirements-postgres.txt
$env:DATABASE_URL = "postgresql://insightpilot:$($env:POSTGRES_PASSWORD)@localhost:5432/insightpilot"
python -m insightpilot.cli ask "monthly revenue trend"
```

PostgreSQL analytical queries run in a read-only transaction and receive a statement timeout and the same result row cap. Ingestion uses the configured database connection to write the destination table. The PostgreSQL image in the override includes pgvector for vector retrieval.

## Optional sentence-transformer embeddings

The default embedder uses scikit-learn and is fully offline. To use the optional neural embedder:

```powershell
python -m pip install -r requirements-embeddings.txt
$env:IP_EMBEDDER = "sbert"
python -m insightpilot.cli search "a policy paraphrase"
```

The first model use may need network access to download the model. Sentence-transformers uses its model cache, and document vectors are cached under `data/embedding-cache` (override with `IP_EMBEDDING_CACHE_DIR`). The normal default install never imports or downloads sentence-transformers.

## Optional OpenTelemetry

Install the SDK and OTLP exporters:

```powershell
python -m pip install -r requirements-otel.txt
$env:OTEL_TRACES_EXPORTER = "otlp"
$env:OTEL_EXPORTER_OTLP_ENDPOINT = "http://localhost:4317"
$env:OTEL_EXPORTER_OTLP_PROTOCOL = "grpc"
uvicorn insightpilot.api:app --reload
```

The exporter also honors standard OTLP headers and endpoint variables. Each agent node creates a span with node, route, row-count, verification, and response-source attributes. Question text, SQL, row data, and secrets are never added as span attributes. Local JSONL traces remain enabled by default; they can contain question text, so protect the trace directory.

## Optional LLM explanations

Set `GEMINI_API_KEY` to enable Gemini explanations. Without it, InsightPilot uses deterministic templates. The model does not plan or execute SQL and does not compute numbers. The verifier rejects an explanation containing unsupported numbers and falls back to the template. The project is still usable without a key.

## Evaluation

```powershell
python -m insightpilot.eval.run_eval
```

The command writes `results/eval_summary.json` and `results/agent_cases.csv`. Read the metrics from the generated summary after each run; this README does not embed evaluation results. The summary records the run date, engine, answer mode, configured embedder, agent metrics, and retrieval recall@k/MRR per retrieval mode. When `IP_EMBEDDER=sbert`, evaluation also includes the offline LSA embedder.

## Safety and limitations

- The rule planner supports common aggregate, grouping, top/bottom, date, trend, and correlation questions. Unsupported or ambiguous questions should result in clarification rather than a guessed query.
- The planner uses actual schema identifiers and values from the loaded data. Generated SQL must pass `validate_sql`; execution is read-only, time-limited, and row-capped.
- Numeric grounding checks confirm that answer numbers occur in computed facts. They do not prove that the prose interpretation or chosen question intent is correct.
- Correlation is descriptive and does not establish causation. Trend periods absent from the source are not automatically filled in.
- The included data is synthetic and small. Benchmark results measure this labelled corpus and query set, not general retrieval quality.
- PostgreSQL/pgvector, sentence-transformers, and OTLP export require their optional dependencies and services. They are not required for the default offline workflow.
- Verification status: PostgreSQL, pgvector, sentence-transformers, and OTLP export are implemented and unit-tested with mocks; not verified against a live service. Docker and a live PostgreSQL server were unavailable during this audit.
- LLM explanations require an external API and send the question and bounded result context to that provider. Do not send sensitive data unless your policies permit it.

Regenerate the synthetic example files with `python scripts/make_sample_data.py`.
