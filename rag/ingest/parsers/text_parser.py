from __future__ import annotations

from .base import BaseParser, ParseResult, TextChunk

TEXT_EXTENSIONS = {".txt", ".md", ".rst", ".csv", ".log", ".json", ".yaml", ".yml", ".xml", ".html"}


class TextParser(BaseParser):

    def can_parse(self, file_path: str) -> bool:
        return self._ext(file_path) in TEXT_EXTENSIONS

    def parse(self, file_path: str) -> ParseResult:
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                text = f.read()
        except Exception as e:
            return ParseResult(source_path=file_path, doc_type="text", errors=[str(e)])

        chunk = TextChunk(content=text, chunk_index=0)
        return ParseResult(
            source_path=file_path,
            doc_type="text",
            chunks=[chunk],
            metadata={"char_count": len(text)},
        )
