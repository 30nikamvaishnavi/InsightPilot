"""FastAPI service. A thin layer over ``Analyst``: no analysis logic lives here.

Run:  uvicorn insightpilot.api:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__
from .agent.tracing import read_traces
from .config import ROOT
from .ingestion import LOADERS
from .service import Analyst

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BASE64_CHARS = 4 * ((MAX_UPLOAD_BYTES + 2) // 3)
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "30"))
RATE_LIMIT_WINDOW_SECONDS = 60
if RATE_LIMIT_PER_MINUTE < 1:
    raise ValueError("RATE_LIMIT_PER_MINUTE must be a positive integer")

app = FastAPI(title="InsightPilot", version=__version__,
              description="A small, verifiable AI data analyst: hybrid RAG + read-only SQL + a traced agent.")
_state: dict = {}
_rate_limit_buckets: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_rate_limit_lock = threading.Lock()


def public_demo_enabled() -> bool:
    return os.environ.get("PUBLIC_DEMO", "").strip() == "1"


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
    if forwarded_for:
        return forwarded_for
    return request.client.host if request.client else "unknown"


def enforce_rate_limit(request: Request, endpoint: str) -> None:
    now = time.monotonic()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    key = (_client_ip(request), endpoint)
    with _rate_limit_lock:
        requests = _rate_limit_buckets[key]
        while requests and requests[0] <= cutoff:
            requests.popleft()
        if len(requests) >= RATE_LIMIT_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded: maximum {RATE_LIMIT_PER_MINUTE} requests per minute.",
            )
        requests.append(now)
        if len(_rate_limit_buckets) > 1024:
            expired_keys = [
                bucket for bucket, timestamps in _rate_limit_buckets.items()
                if not timestamps or timestamps[0] <= cutoff
            ]
            for bucket in expired_keys:
                _rate_limit_buckets.pop(bucket, None)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'self'; "
        "form-action 'self'; frame-ancestors 'none'"
    )
    return response


def get_analyst() -> Analyst:
    if "analyst" not in _state:
        _state["analyst"] = Analyst()
    return _state["analyst"]


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class IngestRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_base64: str = Field(min_length=1)


@app.get("/api/health")
def health() -> dict:
    return {**get_analyst().health(), "version": __version__, "public_demo": public_demo_enabled()}


@app.post("/api/ask")
def ask(request: AskRequest, http_request: Request) -> dict:
    enforce_rate_limit(http_request, "ask")
    return get_analyst().ask(request.question)


@app.get("/api/search")
def search(request: Request, q: str = Query(..., min_length=1, max_length=500), k: int = Query(5, ge=1, le=20),
           mode: Literal["hybrid", "bm25", "embedding"] = "hybrid") -> dict:
    enforce_rate_limit(request, "search")
    return {"query": q, "mode": mode, "results": get_analyst().search(q, k=k, mode=mode)}


@app.get("/api/schema")
def schema() -> dict:
    return get_analyst().schema()


@app.post("/api/ingest")
def ingest(request: IngestRequest) -> dict:
    if public_demo_enabled():
        raise HTTPException(status_code=403, detail="Uploads are disabled in the public demo.")
    name = request.filename.replace("\\", "/").rsplit("/", maxsplit=1)[-1]
    if not name or name in {".", ".."}:
        raise HTTPException(400, "filename must include a file name")
    if Path(name).suffix.lower() not in LOADERS:
        raise HTTPException(400, f"Unsupported file type. Supported: {', '.join(sorted(LOADERS))}")
    if len(request.content_base64) > MAX_UPLOAD_BASE64_CHARS:
        raise HTTPException(413, "File is larger than 5 MB")
    try:
        data = base64.b64decode(request.content_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(400, "content_base64 is not valid base64")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than 5 MB")
    analyst = get_analyst()
    analyst.settings.upload_dir.mkdir(parents=True, exist_ok=True)
    target = analyst.settings.upload_dir / name
    target.write_bytes(data)
    try:
        report = analyst.ingest(target)
    except Exception as exc:
        raise HTTPException(422, f"Could not read the file: {type(exc).__name__}: {exc}")
    return {k: v for k, v in report.items()}


@app.get("/api/ingest/report/{table}")
def ingest_report(table: str) -> dict:
    report = get_analyst().ingest_report(table)
    if report is None:
        raise HTTPException(404, f"No validation report is available for table '{table}'")
    return report


@app.get("/api/traces")
def traces(limit: int = Query(20, ge=1, le=200)) -> dict:
    if public_demo_enabled():
        raise HTTPException(status_code=403, detail="Trace access is disabled in the public demo.")
    return {"traces": read_traces(get_analyst().settings.trace_dir, limit)}


@app.get("/api/eval/summary")
def eval_summary() -> dict:
    path = get_analyst().settings.results_dir / "eval_summary.json"
    if not path.exists():
        raise HTTPException(404, "No evaluation has been run yet. Run: python -m insightpilot.eval.run_eval")
    return json.loads(path.read_text(encoding="utf-8"))


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html")
