from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from .parsers.base import TextChunk


class ChunkStrategy(str, Enum):
    FIXED_SIZE = "fixed_size"
    SLIDING_WINDOW = "sliding_window"
    AS_IS = "as_is"  # 파서가 이미 분할한 경우 그대로 사용


@dataclass
class ChunkConfig:
    strategy: ChunkStrategy = ChunkStrategy.SLIDING_WINDOW
    chunk_size: int = 512
    chunk_overlap: int = 64


class Chunker:
    """텍스트 청크를 전략에 따라 추가 분할합니다."""

    def chunk(
        self, raw_chunks: list[TextChunk], config: ChunkConfig
    ) -> list[TextChunk]:
        if config.strategy == ChunkStrategy.AS_IS:
            return raw_chunks

        result: list[TextChunk] = []
        for rc in raw_chunks:
            sub_chunks = self._split_text(rc.content, config)
            for i, text in enumerate(sub_chunks):
                result.append(
                    TextChunk(
                        content=text,
                        chunk_index=len(result),
                        page_or_line=rc.page_or_line,
                        language=rc.language,
                        metadata=dict(rc.metadata),
                    )
                )
        return result

    def _split_text(self, text: str, config: ChunkConfig) -> list[str]:
        if len(text) <= config.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0
        step = config.chunk_size - config.chunk_overlap

        while start < len(text):
            end = start + config.chunk_size
            chunk = text[start:end]
            if chunk.strip():
                chunks.append(chunk)
            start += step

        return chunks or [text]
