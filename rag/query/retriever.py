from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from ..ingest.embedder import Embedder
from ..vector_db import FAISSStore, MetadataStore, SearchResult
from .intelligence import QueryAnalysis


@dataclass
class RetrievedChunk:
    chunk_id: str
    score: float
    content: str = ""
    source_path: str = ""
    page_or_line: int | None = None
    doc_type: str = ""
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class HybridRetriever:
    """FAISS 벡터 검색 + SQLite FTS5 BM25 검색을 RRF로 결합합니다."""

    def __init__(
        self,
        faiss_store: FAISSStore,
        metadata_store: MetadataStore,
        embedder: Embedder,
        top_k: int = 10,
        vector_weight: float = 0.7,
    ):
        self.faiss_store = faiss_store
        self.metadata_store = metadata_store
        self.embedder = embedder
        self.top_k = top_k
        self.vector_weight = vector_weight

    async def retrieve(
        self,
        analysis: QueryAnalysis,
        namespace: str,
    ) -> list[RetrievedChunk]:
        all_results: dict[str, float] = {}

        # 재작성된 쿼리 각각에 대해 벡터 검색
        for q in analysis.rewritten_queries:
            qvec = self.embedder.encode_query(q)
            vector_hits = self.faiss_store.search(qvec, top_k=self.top_k)
            for hit in vector_hits:
                prev = all_results.get(hit.chunk_id, 0.0)
                all_results[hit.chunk_id] = max(prev, hit.score * self.vector_weight)

        # FTS 검색 (원본 쿼리)
        fts_hits = await self.metadata_store.fts_search(
            analysis.original, namespace, top_k=self.top_k
        )
        bm25_weight = 1.0 - self.vector_weight
        for hit in fts_hits:
            prev = all_results.get(hit.chunk_id, 0.0)
            all_results[hit.chunk_id] = prev + hit.score * bm25_weight

        # 점수 내림차순 정렬
        sorted_ids = sorted(all_results, key=lambda k: all_results[k], reverse=True)
        top_ids = sorted_ids[: self.top_k]

        # 메타데이터 보강
        chunk_records = await self.metadata_store.get_chunks_by_ids(top_ids)
        id_to_record = {cr.chunk_id: cr for cr in chunk_records}

        results = []
        for chunk_id in top_ids:
            score = all_results[chunk_id]
            cr = id_to_record.get(chunk_id)
            if cr is None:
                continue

            # 소스 경로 조회
            detail = await self.metadata_store.get_chunk_with_source(chunk_id)
            source_path = detail["source_path"] if detail else ""
            doc_type = detail["doc_type"] if detail else ""

            results.append(
                RetrievedChunk(
                    chunk_id=chunk_id,
                    score=score,
                    content=cr.content,
                    source_path=source_path,
                    page_or_line=cr.page_or_line,
                    doc_type=doc_type,
                    language=cr.language,
                    metadata=cr.metadata,
                )
            )

        return results
