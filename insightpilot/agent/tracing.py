"""Step tracing: every node records a span; every run is appended to a JSONL file."""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

_OTEL_LOCK = threading.Lock()
_OTEL_CONFIGURED = False


def configure_otel() -> None:
    """Configure OTLP export only when the standard exporter env opts in."""
    global _OTEL_CONFIGURED
    exporter = os.environ.get("OTEL_TRACES_EXPORTER", "").strip().lower()
    if exporter != "otlp" or os.environ.get("OTEL_SDK_DISABLED", "").lower() == "true":
        return
    with _OTEL_LOCK:
        if _OTEL_CONFIGURED:
            return
        try:
            from opentelemetry import trace
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:
            raise RuntimeError("OTLP tracing requires requirements-otel.txt.") from exc
        protocol = os.environ.get("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc").strip().lower()
        if protocol not in {"grpc", "http/protobuf"}:
            raise ValueError("OTEL_EXPORTER_OTLP_PROTOCOL must be 'grpc' or 'http/protobuf'")
        try:
            if protocol == "grpc":
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            else:
                from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        except ImportError as exc:
            raise RuntimeError("The configured OTLP protocol exporter is missing; install requirements-otel.txt.") from exc
        provider = TracerProvider(
            resource=Resource.create({"service.name": os.environ.get("OTEL_SERVICE_NAME", "insightpilot")})
        )
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        trace.set_tracer_provider(provider)
        _OTEL_CONFIGURED = True


def write_trace(trace_dir: str | Path, record: dict) -> Path:
    trace_dir = Path(trace_dir)
    trace_dir.mkdir(parents=True, exist_ok=True)
    path = trace_dir / f"traces-{datetime.now(timezone.utc):%Y%m%d}.jsonl"
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, default=str) + "\n")
    return path


def read_traces(trace_dir: str | Path, limit: int = 20) -> list[dict]:
    trace_dir = Path(trace_dir)
    if not trace_dir.exists():
        return []
    records: list[dict] = []
    for path in sorted(trace_dir.glob("traces-*.jsonl")):
        with open(path, encoding="utf-8") as handle:
            records.extend(json.loads(line) for line in handle if line.strip())
    return records[-limit:][::-1]
