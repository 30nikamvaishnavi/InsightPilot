from __future__ import annotations

import tempfile
from dataclasses import replace
from pathlib import Path

from insightpilot.config import ROOT, get_settings
from insightpilot.ingestion import clean, load_file
from insightpilot.service import Analyst

_cache: dict = {}


def make_settings(**overrides):
    tmp = Path(tempfile.mkdtemp())
    base = replace(get_settings(), db_path=tmp / "test.db", trace_dir=tmp / "traces", upload_dir=tmp / "uploads",
                   gemini_api_key=None)
    return replace(base, **overrides)


def analyst() -> Analyst:
    if "analyst" not in _cache:
        _cache["analyst"] = Analyst(make_settings(), use_langgraph=False, explainer=None)
    return _cache["analyst"]


def sales_df():
    return clean(load_file(ROOT / "data" / "sample" / "sales.csv"))[0]
