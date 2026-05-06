from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass
class DocumentRecord:
    doc_id: str
    namespace: str
    source_path: str
    doc_type: str  # pdf | image | excel | code | text
    title: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChunkRecord:
    chunk_id: str
    doc_id: str
    namespace: str
    content: str
    chunk_index: int = 0
    page_or_line: int | None = None
    language: str | None = None
    token_count: int = 0
    embedding_model: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class SearchResult:
    chunk_id: str
    score: float
    content: str = ""
    source_path: str = ""
    page_or_line: int | None = None
    doc_type: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class IndexStats:
    namespace: str
    total_vectors: int
    dimension: int
    index_file: str
