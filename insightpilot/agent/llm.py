"""Optional LLM that only *explains* results. It never computes or chooses numbers.

Without GEMINI_API_KEY the agent uses deterministic templates. Any LLM text is
rejected by the verifier if it contains a number that the code did not produce.
"""
from __future__ import annotations

import json

import requests


class GeminiExplainer:
    def __init__(self, api_key: str, model: str, timeout: float = 20.0) -> None:
        self._api_key = api_key  # never logged or returned
        self.model = model
        self.timeout = timeout

    def explain(self, payload: dict) -> str | None:
        prompt = (
            "You are a careful data analyst. Explain the result below in at most three short sentences. "
            "Use ONLY numbers that appear in DATA. Do not add, estimate or round to new numbers. "
            "If the data does not answer the question, say so.\n\nDATA:\n"
            + json.dumps(payload, default=str)[:6000]
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        try:
            response = requests.post(
                url,
                headers={"x-goog-api-key": self._api_key, "Content-Type": "application/json"},
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=self.timeout,
            )
            response.raise_for_status()
            text = response.json()["candidates"][0]["content"]["parts"][0]["text"]
            return text.strip() or None
        except Exception:  # network, quota, parsing: fall back to the template
            return None


def make_explainer(settings):
    if settings.gemini_api_key:
        return GeminiExplainer(settings.gemini_api_key, settings.gemini_model)
    return None
