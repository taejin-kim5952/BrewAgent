from __future__ import annotations

import pickle
from pathlib import Path
from typing import List

import numpy as np

from .namespace import NamespaceManager
from .schemas import IndexStats, SearchResult


class FAISSStore:
    """FAISS 기반 벡터 인덱스 — 네임스페이스별로 파일 분리."""

    def __init__(self, namespace: str, ns_manager: NamespaceManager, dim: int = 384):
        self.namespace = namespace
        self.ns_manager = ns_manager
        self.dim = dim
        self._index = None
        self._id_map: list[str] = []  # faiss 내부 인덱스 → chunk_id 매핑

        if ns_manager.exists(namespace):
            self._load()
        else:
            self._create()

    # ------------------------------------------------------------------
    # 내부 초기화
    # ------------------------------------------------------------------

    def _create(self) -> None:
        import faiss

        self._index = faiss.IndexFlatL2(self.dim)
        self._id_map = []

    def _load(self) -> None:
        import faiss

        self._index = faiss.read_index(str(self.ns_manager.index_path(self.namespace)))
        meta_path = self.ns_manager.meta_path(self.namespace)
        if meta_path.exists():
            with open(meta_path, "rb") as f:
                self._id_map = pickle.load(f)
        else:
            self._id_map = []

    # ------------------------------------------------------------------
    # 공개 API
    # ------------------------------------------------------------------

    def add(self, embeddings: np.ndarray, chunk_ids: list[str]) -> None:
        """임베딩 벡터와 chunk_id 목록을 인덱스에 추가합니다."""
        vecs = embeddings.astype("float32")
        self._index.add(vecs)
        self._id_map.extend(chunk_ids)
        self.persist()

    def search(self, query_vec: np.ndarray, top_k: int = 10) -> list[SearchResult]:
        """쿼리 벡터와 가장 유사한 청크 ID 목록을 반환합니다."""
        if self._index.ntotal == 0:
            return []

        k = min(top_k, self._index.ntotal)
        distances, indices = self._index.search(
            query_vec.astype("float32").reshape(1, -1), k
        )

        results = []
        for dist, idx in zip(distances[0], indices[0]):
            if idx < 0 or idx >= len(self._id_map):
                continue
            score = float(1.0 / (1.0 + dist))  # L2 거리 → 유사도 점수 변환
            results.append(SearchResult(chunk_id=self._id_map[idx], score=score))
        return results

    def persist(self) -> None:
        """인덱스와 ID 맵을 파일에 저장합니다."""
        import faiss

        ns_dir = self.ns_manager.namespace_dir(self.namespace)
        faiss.write_index(self._index, str(ns_dir / "index.faiss"))
        with open(ns_dir / "id_map.pkl", "wb") as f:
            pickle.dump(self._id_map, f)

    def delete_chunks(self, chunk_ids: set[str]) -> None:
        """특정 chunk_id 삭제 (전체 재구축 방식)."""
        import faiss

        keep_indices = [
            i for i, cid in enumerate(self._id_map) if cid not in chunk_ids
        ]
        if len(keep_indices) == len(self._id_map):
            return

        old_vecs = self._index.reconstruct_n(0, self._index.ntotal)
        new_vecs = old_vecs[keep_indices].astype("float32")
        new_ids = [self._id_map[i] for i in keep_indices]

        self._index = faiss.IndexFlatL2(self.dim)
        if len(new_vecs) > 0:
            self._index.add(new_vecs)
        self._id_map = new_ids
        self.persist()

    def get_stats(self) -> IndexStats:
        return IndexStats(
            namespace=self.namespace,
            total_vectors=self._index.ntotal if self._index else 0,
            dimension=self.dim,
            index_file=str(self.ns_manager.index_path(self.namespace)),
        )
