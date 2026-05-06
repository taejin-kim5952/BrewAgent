from __future__ import annotations

from .base import BaseParser, ParseResult, TextChunk

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp"}


class ImageParser(BaseParser):

    def can_parse(self, file_path: str) -> bool:
        return self._ext(file_path) in IMAGE_EXTENSIONS

    def parse(self, file_path: str) -> ParseResult:
        text = self._ocr(file_path)
        if text:
            chunk = TextChunk(content=text, chunk_index=0)
            return ParseResult(
                source_path=file_path,
                doc_type="image",
                chunks=[chunk],
                metadata={"ocr": True},
            )
        return ParseResult(
            source_path=file_path,
            doc_type="image",
            chunks=[],
            metadata={"ocr": False},
            errors=["텍스트를 추출할 수 없습니다. Tesseract가 설치되었는지 확인하세요."],
        )

    def _ocr(self, file_path: str) -> str:
        try:
            from PIL import Image
            import pytesseract

            img = Image.open(file_path)
            text = pytesseract.image_to_string(img, lang="kor+eng")
            return text.strip()
        except Exception:
            return ""
