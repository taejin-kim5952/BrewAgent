from __future__ import annotations

from pathlib import Path

from .parsers.base import BaseParser, ParseResult
from .parsers.code_parser import CodeParser
from .parsers.docx_parser import DocxParser
from .parsers.excel_parser import ExcelParser
from .parsers.image_parser import ImageParser
from .parsers.pdf_parser import PDFParser
from .parsers.pptx_parser import PptxParser
from .parsers.text_parser import TextParser


class Dispatcher:
    """파일 확장자에 따라 적절한 파서로 라우팅합니다."""

    def __init__(self):
        self._parsers: list[BaseParser] = [
            PDFParser(),
            DocxParser(),
            PptxParser(),
            ExcelParser(),
            ImageParser(),
            CodeParser(),
            TextParser(),  # 가장 마지막: 폴백
        ]

    def parse(self, file_path: str) -> ParseResult:
        for parser in self._parsers:
            if parser.can_parse(file_path):
                return parser.parse(file_path)
        # 인식 불가 파일 → 텍스트로 시도
        return TextParser().parse(file_path)

    def supported_extensions(self) -> list[str]:
        exts = []
        for p in self._parsers:
            if hasattr(p, "_ext"):
                pass
        return exts
