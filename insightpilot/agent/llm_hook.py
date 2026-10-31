from __future__ import annotations

from .llm import make_explainer


def resolve_explainer(settings, explainer):
    """'auto' -> use Gemini if a key is set; None -> templates only; or pass your own object."""
    return make_explainer(settings) if explainer == "auto" else explainer
