from __future__ import annotations

import numpy as np


class Embedder:
    """sentence-transformers 기반 배치 임베딩."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", device: str = "cpu"):
        self.model_name = model_name
        self.device = device
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def encode_texts(self, texts: list[str], batch_size: int = 32) -> np.ndarray:
        if not texts:
            return np.array([])
        model = self._get_model()
        embeddings = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        return np.array(embeddings, dtype="float32")

    def encode_query(self, query: str) -> np.ndarray:
        return self.encode_texts([query])[0]

    @property
    def dimension(self) -> int:
        return self._get_model().get_sentence_embedding_dimension()
