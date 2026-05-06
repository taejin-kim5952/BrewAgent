from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextChunk:
    content: str
    chunk_index: int = 0
    page_or_line: int | None = None
    language: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseResult:
    source_path: str
    doc_type: str  # pdf | image | excel | code | text
    chunks: list[TextChunk] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


class BaseParser(ABC):

    @abstractmethod
    def can_parse(self, file_path: str) -> bool:
        """이 파서가 해당 파일을 처리할 수 있는지 확인합니다."""
        ...

    @abstractmethod
    def parse(self, file_path: str) -> ParseResult:
        """파일을 파싱하여 ParseResult를 반환합니다."""
        ...

    def _ext(self, file_path: str) -> str:
        from pathlib import Path
        return Path(file_path).suffix.lower()
