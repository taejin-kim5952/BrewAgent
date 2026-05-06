from __future__ import annotations

import re

from .base import BaseParser, ParseResult, TextChunk

CODE_EXTENSIONS = {
    ".java": "java",
    ".sql": "sql",
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".go": "go",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".rs": "rust",
    ".sh": "bash",
    ".xml": "xml",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
}


class CodeParser(BaseParser):

    def can_parse(self, file_path: str) -> bool:
        return self._ext(file_path) in CODE_EXTENSIONS

    def parse(self, file_path: str) -> ParseResult:
        lang = CODE_EXTENSIONS.get(self._ext(file_path), "text")
        try:
            with open(file_path, encoding="utf-8", errors="replace") as f:
                source = f.read()
        except Exception as e:
            return ParseResult(source_path=file_path, doc_type="code", errors=[str(e)])

        chunks = self._split_by_blocks(source, lang, file_path)
        return ParseResult(
            source_path=file_path,
            doc_type="code",
            chunks=chunks,
            metadata={"language": lang, "total_lines": source.count("\n") + 1},
        )

    def _split_by_blocks(self, source: str, lang: str, file_path: str) -> list[TextChunk]:
        """언어별 코드 블록 분할 (메서드/함수/클래스 단위)."""
        from pathlib import Path
        file_name = Path(file_path).name

        if lang == "java":
            return self._split_java(source, file_name)
        elif lang == "sql":
            return self._split_sql(source, file_name)
        else:
            return self._split_by_lines(source, file_name, lang)

    def _split_java(self, source: str, file_name: str) -> list[TextChunk]:
        """Java: 클래스/메서드 단위 분할."""
        # 간단한 중괄호 기반 분할
        pattern = re.compile(
            r"((?:(?:public|private|protected|static|final|abstract|synchronized)\s+)*"
            r"(?:class|interface|enum|@interface)\s+\w+[^{]*\{)",
            re.MULTILINE,
        )
        chunks = []
        parts = pattern.split(source)
        # 헤더(import, package 등) 별도 저장
        if parts:
            header = parts[0].strip()
            if header:
                chunks.append(TextChunk(content=f"// {file_name} - 헤더\n{header}", chunk_index=0, language="java"))
        return chunks if chunks else [TextChunk(content=source, chunk_index=0, language="java")]

    def _split_sql(self, source: str, file_name: str) -> list[TextChunk]:
        """SQL: 세미콜론으로 구문 분할."""
        statements = [s.strip() for s in source.split(";") if s.strip()]
        return [
            TextChunk(content=stmt + ";", chunk_index=i, language="sql")
            for i, stmt in enumerate(statements)
        ]

    def _split_by_lines(self, source: str, file_name: str, lang: str, chunk_lines: int = 80) -> list[TextChunk]:
        """기본: N줄 단위 분할."""
        lines = source.split("\n")
        chunks = []
        for i in range(0, len(lines), chunk_lines):
            block = "\n".join(lines[i:i + chunk_lines])
            if block.strip():
                chunks.append(
                    TextChunk(
                        content=block,
                        chunk_index=len(chunks),
                        page_or_line=i + 1,
                        language=lang,
                    )
                )
        return chunks or [TextChunk(content=source, chunk_index=0, language=lang)]
