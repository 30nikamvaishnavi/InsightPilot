# Approach and design decisions

## Principle: code computes, the verifier checks, the model explains

The analyst follows a guarded path: validate the question, create a schema-aware plan, execute a read-only query or retrieve documentation, compute derived statistics in Python, draft an answer, and check its numbers with `agent/verifier.py`. The LLM is optional and receives already-computed context for explanation only. An unsupported model-generated number causes the deterministic template to be used instead.

## Database layer

With `DATABASE_URL` unset, InsightPilot uses SQLite at `IP_DB_PATH` (or `data/insightpilot.db`) as before. A `postgresql://` or `postgres://` URL selects PostgreSQL through psycopg 3. The shared store functions expose the same schema, distinct-value, ingestion, and query operations to the planner and agent.

PostgreSQL analytical SQL runs in a read-only transaction. `statement_timeout` bounds server execution, and a server-side cursor fetches no more than the configured row cap plus one row to determine truncation. Ingestion uses a write connection. PostgreSQL date expressions use `to_char`, `date_trunc`, and `extract`; the SQLite planner expressions remain unchanged.

The Compose PostgreSQL override uses the pgvector image and waits for its health check before starting the API. Base `docker-compose.yml` does not start PostgreSQL. Install the optional driver and vector adapter with `requirements-postgres.txt`.

## SQL safety

1. The rule planner draws table and column identifiers from the database schema. Categorical and date filter values are selected from loaded values or recognized date tokens, not interpolated from arbitrary question text.
2. `validate_sql` accepts one `SELECT` or `WITH` statement, and rejects comments, extra statements, and write/admin keywords.
3. SQLite opens the database with `mode=ro`; PostgreSQL marks each analytical transaction read-only.
4. The execution layer applies the row cap and timeout. These defenses constrain execution; they do not prove that the interpretation of a natural-language request is correct.

## Hybrid retrieval and cached vectors

BM25 is effective for matching terms that appear in a document. Dense embeddings can recover paraphrases. Reciprocal Rank Fusion (RRF) combines rank order rather than adding unrelated score scales. Embedding similarity ranks candidates; a result is marked relevant only when BM25 provides lexical evidence.

LSA character n-gram vectors are the zero-network default. `IP_EMBEDDER=sbert` selects sentence-transformers, whose model files use the library cache. Document vectors are cached under `IP_EMBEDDING_CACHE_DIR` (default `data/embedding-cache`) and keyed by embedder identity and corpus text. The vector-store interface has an in-memory NumPy implementation and a pgvector implementation selected with PostgreSQL. BM25 and RRF remain active in either configuration.

## Ingestion reports

Loaders are registered by extension. The supported built-ins include delimited text, JSON, Excel, and Parquet. Cleaning normalizes headers, trims text, parses date-like fields when possible, and removes empty and fully duplicated rows. The validation report gives inferred types, null percentages, repeated-value counts, and row-level cleaning notes. These checks describe the input; they do not certify its business meaning.

## Agent, LangGraph, and traces

Each node is a plain state-in/state-update-out function wrapped by the same trace and step-limit logic. LangGraph routes from guard to plan or response, then from plan to execute or response, followed by response and verification. The sequential runner follows the same routing and functions when LangGraph is unavailable or explicitly disabled.

Local JSONL run traces are enabled by default and may include question text. Optional OpenTelemetry creates one span per node when OTLP export is configured with `OTEL_TRACES_EXPORTER=otlp`. Span attributes include only the node, route, returned row count, verification state, and response source. Question text, SQL, row values, and secrets are never attached as attributes. Standard OTLP endpoint, protocol, and header environment variables configure export.

## Known limitations

- The rule planner covers common aggregates, groupings, date filters, trends, top/bottom rows, and correlation. It is not a general natural-language-to-SQL system.
- Number grounding does not check whether a factual sentence is logically correct or whether the planner chose the right metric.
- The example data and labelled retrieval benchmark are synthetic and small; their measured performance does not generalize to other corpora.
- Dense embedding relevance is deliberately not treated as sufficient evidence by itself.
- PostgreSQL/pgvector requires an available PostgreSQL service, the optional Python dependencies, and a role allowed to create the vector extension/table for initial vector-store setup.
- Sentence-transformers may need network access the first time its model is absent from the local cache.
- OpenTelemetry export requires an OTLP collector and optional exporter packages. The default JSONL trace files need local access controls.
- Verification status: PostgreSQL, pgvector, sentence-transformers, and OTLP export are implemented and unit-tested with mocks; not verified against a live service. Docker and a live PostgreSQL server were unavailable during this audit.
- LLM explanations require an external service and send the question plus bounded result context to that service.
