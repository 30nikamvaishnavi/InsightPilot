"""FastAPI service. A thin layer over ``Analyst``: no analysis logic lives here.

Run:  uvicorn insightpilot.api:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import base64
import binascii
import json
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import __version__
from .agent.tracing import read_traces
from .config import ROOT
from .ingestion import LOADERS
from .service import Analyst

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_UPLOAD_BASE64_CHARS = 4 * ((MAX_UPLOAD_BYTES + 2) // 3)

app = FastAPI(title="InsightPilot", version=__version__,
              description="A small, verifiable AI data analyst: hybrid RAG + read-only SQL + a traced agent.")
_state: dict = {}


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
    return {**get_analyst().health(), "version": __version__}


@app.post("/api/ask")
def ask(request: AskRequest) -> dict:
    return get_analyst().ask(request.question)


@app.get("/api/search")
def search(q: str = Query(..., min_length=1, max_length=500), k: int = Query(5, ge=1, le=20),
           mode: Literal["hybrid", "bm25", "embedding"] = "hybrid") -> dict:
    return {"query": q, "mode": mode, "results": get_analyst().search(q, k=k, mode=mode)}


@app.get("/api/schema")
def schema() -> dict:
    return get_analyst().schema()


@app.post("/api/ingest")
def ingest(request: IngestRequest) -> dict:
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
