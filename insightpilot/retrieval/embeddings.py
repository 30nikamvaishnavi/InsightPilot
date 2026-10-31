"""Text embedders.

``LSAEmbedder`` (default) runs fully offline: character n-gram TF-IDF followed by
truncated SVD (latent semantic analysis). It is a lightweight stand-in for neural
embeddings. Set ``IP_EMBEDDER=sbert`` to use sentence-transformers instead.
"""
from __future__ import annotations

import numpy as np
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer


def _normalise(matrix: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


class LSAEmbedder:
    name = "lsa-char-ngram"

    def __init__(self, n_components: int = 32) -> None:
        self.n_components = n_components

    def fit(self, texts: list[str]) -> "LSAEmbedder":
        self.vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), sublinear_tf=True)
        matrix = self.vectorizer.fit_transform(texts)
        k = max(2, min(self.n_components, matrix.shape[0] - 1, matrix.shape[1] - 1))
        self.svd = TruncatedSVD(n_components=k, random_state=0).fit(matrix)
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        return _normalise(self.svd.transform(self.vectorizer.transform(texts)))


class SentenceTransformerEmbedder:
    """Optional neural embeddings (``pip install sentence-transformers``)."""

    def __init__(self, model: str = "sentence-transformers/all-MiniLM-L6-v2") -> None:
        self.name = model
        self.model_name = model

    def fit(self, texts: list[str]) -> "SentenceTransformerEmbedder":
        from sentence_transformers import SentenceTransformer  # lazy import

        self.model = SentenceTransformer(self.model_name)
        return self

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True))


def make_embedder(name: str = "lsa"):
    if name == "sbert":
        return SentenceTransformerEmbedder()
    if name == "lsa":
        return LSAEmbedder()
    raise ValueError("embedder must be 'lsa' or 'sbert'")
