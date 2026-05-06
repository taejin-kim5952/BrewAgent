from __future__ import annotations

from .base import BaseParser, ParseResult, TextChunk


class PDFParser(BaseParser):

    def can_parse(self, file_path: str) -> bool:
        return self._ext(file_path) == ".pdf"

    def parse(self, file_path: str) -> ParseResult:
        try:
            import fitz  # PyMuPDF
        except ImportError:
            return ParseResult(
                source_path=file_path, doc_type="pdf",
                errors=["pymupdf가 설치되지 않았습니다."]
            )

        chunks: list[TextChunk] = []
        errors: list[str] = []
        metadata: dict = {}

        try:
            doc = fitz.open(file_path)
            metadata["page_count"] = len(doc)
            metadata["title"] = doc.metadata.get("title", "")

            for page_num, page in enumerate(doc, start=1):
                text = page.get_text("text").strip()
                if text:
                    chunks.append(
                        TextChunk(
                            content=text,
                            chunk_index=page_num - 1,
                            page_or_line=page_num,
                        )
                    )
            doc.close()
        except Exception as e:
            errors.append(str(e))

        return ParseResult(
            source_path=file_path,
            doc_type="pdf",
            chunks=chunks,
            metadata=metadata,
            errors=errors,
        )
