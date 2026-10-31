# Operations Reference

## Access boundaries
InsightPilot runs analytical SQL as a read-only transaction. In PostgreSQL, the connection is also marked transaction-read-only before a query starts.

## Batch imports
An ingestion run cleans a supported file, normalizes its headers and replaces the destination table with the cleaned rows. Keep a source copy if the original needs to be preserved.

## Browser uploads
The API accepts CSV, TSV, JSON, JSONL, Excel, Parquet and pipe-delimited TXT files up to its configured upload limit. Uploaded files are stored under the configured upload directory.

## Unsupported file formats
Files without a registered loader are rejected before ingestion. Add a loader through register_loader rather than guessing how to parse an unfamiliar format.

## Table naming
The destination table name is derived from the source file stem and normalized to a safe snake_case identifier. Uploading another file with that name replaces the prior table.

## Validation reports
The report includes the cleaned row count, inferred column types, null percentages, unique counts, repeated values and cleaning notes. It is a profiling aid, not a guarantee of business correctness.

## SQL query limits
SQL passes single-statement SELECT validation and runs with a row cap and a database-side time limit where supported. These limits reduce accidental cost but do not validate the business meaning of a query.

## Local trace files
JSONL run traces are written locally by default. They may include the user's question and answer, so protect the trace directory if inputs are sensitive.

## Optional telemetry
OpenTelemetry export is opt-in through OTEL_TRACES_EXPORTER=otlp. Span attributes contain operational metadata only; question text, SQL, row data and secrets are never attached.

## Service recovery
If the backend is offline, the browser reports that state rather than rendering sample answers. Start the API and check its health endpoint before retrying an analysis.
