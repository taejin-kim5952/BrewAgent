from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import aiosqlite

from .schemas import ChunkRecord, DocumentRecord, SearchResult


class MetadataStore:
    """SQLite 기반 청크 메타데이터 저장소 (FTS5 전문 검색 포함)."""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def init(self) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.executescript("""
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id      TEXT PRIMARY KEY,
                    namespace   TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    doc_type    TEXT NOT NULL,
                    title       TEXT DEFAULT '',
                    created_at  TEXT,
                    metadata    TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS chunks (
                    chunk_id        TEXT PRIMARY KEY,
                    doc_id          TEXT REFERENCES documents(doc_id),
                    namespace       TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    chunk_index     INTEGER DEFAULT 0,
                    page_or_line    INTEGER,
                    language        TEXT,
                    token_count     INTEGER DEFAULT 0,
                    embedding_model TEXT DEFAULT '',
                    created_at      TEXT,
                    metadata        TEXT DEFAULT '{}'
                );

                CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
                    content,
                    chunk_id UNINDEXED,
                    namespace UNINDEXED,
                    tokenize='unicode61'
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_namespace
                    ON chunks(namespace);
                CREATE INDEX IF NOT EXISTS idx_chunks_doc_id
                    ON chunks(doc_id);
            """)
            await db.commit()

    async def upsert_document(self, doc: DocumentRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO documents
                   (doc_id, namespace, source_path, doc_type, title, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc.doc_id, doc.namespace, doc.source_path,
                    doc.doc_type, doc.title,
                    doc.created_at.isoformat(),
                    json.dumps(doc.metadata, ensure_ascii=False),
                ),
            )
            await db.commit()

    async def upsert_chunk(self, chunk: ChunkRecord) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO chunks
                   (chunk_id, doc_id, namespace, content, chunk_index,
                    page_or_line, language, token_count, embedding_model, created_at, metadata)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    chunk.chunk_id, chunk.doc_id, chunk.namespace, chunk.content,
                    chunk.chunk_index, chunk.page_or_line, chunk.language,
                    chunk.token_count, chunk.embedding_model,
                    chunk.created_at.isoformat(),
                    json.dumps(chunk.metadata, ensure_ascii=False),
                ),
            )
            # FTS 인덱스 업데이트
            await db.execute(
                "DELETE FROM chunks_fts WHERE chunk_id = ?", (chunk.chunk_id,)
            )
            await db.execute(
                "INSERT INTO chunks_fts(content, chunk_id, namespace) VALUES (?, ?, ?)",
                (chunk.content, chunk.chunk_id, chunk.namespace),
            )
            await db.commit()

    async def get_chunks_by_ids(self, chunk_ids: list[str]) -> list[ChunkRecord]:
        if not chunk_ids:
            return []
        placeholders = ",".join("?" * len(chunk_ids))
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                f"SELECT * FROM chunks WHERE chunk_id IN ({placeholders})", chunk_ids
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_chunk(r) for r in rows]

    async def fts_search(self, query: str, namespace: str, top_k: int = 10) -> list[SearchResult]:
        """FTS5 전문 검색."""
        safe_query = query.replace('"', '""')
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT cf.chunk_id, cf.content,
                          bm25(chunks_fts) AS score
                   FROM chunks_fts cf
                   WHERE chunks_fts MATCH ? AND cf.namespace = ?
                   ORDER BY score
                   LIMIT ?""",
                (f'"{safe_query}"', namespace, top_k),
            ) as cursor:
                rows = await cursor.fetchall()
        return [
            SearchResult(
                chunk_id=row["chunk_id"],
                score=float(abs(row["score"])),  # BM25 점수는 음수
                content=row["content"],
            )
            for row in rows
        ]

    async def get_chunk_with_source(self, chunk_id: str) -> dict[str, Any] | None:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT c.*, d.source_path, d.doc_type
                   FROM chunks c JOIN documents d ON c.doc_id = d.doc_id
                   WHERE c.chunk_id = ?""",
                (chunk_id,),
            ) as cursor:
                row = await cursor.fetchone()
        return dict(row) if row else None

    async def delete_document(self, doc_id: str) -> list[str]:
        """문서와 청크를 삭제하고 삭제된 chunk_id 목록 반환."""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT chunk_id FROM chunks WHERE doc_id = ?", (doc_id,)
            ) as cursor:
                rows = await cursor.fetchall()
            chunk_ids = [r[0] for r in rows]

            for cid in chunk_ids:
                await db.execute("DELETE FROM chunks_fts WHERE chunk_id = ?", (cid,))
            await db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
            await db.execute("DELETE FROM documents WHERE doc_id = ?", (doc_id,))
            await db.commit()
        return chunk_ids

    async def list_documents(self, namespace: str) -> list[DocumentRecord]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM documents WHERE namespace = ? ORDER BY created_at DESC",
                (namespace,),
            ) as cursor:
                rows = await cursor.fetchall()
        return [self._row_to_doc(r) for r in rows]

    async def count_chunks(self, namespace: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM chunks WHERE namespace = ?", (namespace,)
            ) as cursor:
                row = await cursor.fetchone()
        return row[0] if row else 0

    # ------------------------------------------------------------------
    # 내부 변환
    # ------------------------------------------------------------------

    def _row_to_chunk(self, row) -> ChunkRecord:
        from datetime import datetime
        return ChunkRecord(
            chunk_id=row["chunk_id"],
            doc_id=row["doc_id"],
            namespace=row["namespace"],
            content=row["content"],
            chunk_index=row["chunk_index"] or 0,
            page_or_line=row["page_or_line"],
            language=row["language"],
            token_count=row["token_count"] or 0,
            embedding_model=row["embedding_model"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            metadata=json.loads(row["metadata"] or "{}"),
        )

    def _row_to_doc(self, row) -> DocumentRecord:
        from datetime import datetime
        return DocumentRecord(
            doc_id=row["doc_id"],
            namespace=row["namespace"],
            source_path=row["source_path"],
            doc_type=row["doc_type"],
            title=row["title"] or "",
            created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else datetime.utcnow(),
            metadata=json.loads(row["metadata"] or "{}"),
        )
