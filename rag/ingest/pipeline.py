from __future__ import annotations

import shutil
import tarfile
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .chunker import Chunker, ChunkConfig, ChunkStrategy
from .dispatcher import Dispatcher
from .embedder import Embedder
from ..vector_db import FAISSStore, NamespaceManager, MetadataStore, ChunkRecord, DocumentRecord


ARCHIVE_EXTS = {".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2"}
MAX_ARCHIVE_FILES = 1000
MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024  # 1GB


def _is_archive(file_path: str) -> bool:
    p = file_path.lower()
    return any(p.endswith(ext) for ext in ARCHIVE_EXTS)


@dataclass
class IngestResult:
    doc_id: str
    source_path: str
    doc_type: str
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)
    success: bool = True


class IngestPipeline:
    """parse → chunk → embed → store 오케스트레이션."""

    def __init__(
        self,
        dispatcher: Dispatcher,
        chunker: Chunker,
        embedder: Embedder,
        ns_manager: NamespaceManager,
        metadata_store: MetadataStore,
        embedding_model_name: str = "",
    ):
        self.dispatcher = dispatcher
        self.chunker = chunker
        self.embedder = embedder
        self.ns_manager = ns_manager
        self.metadata_store = metadata_store
        self.embedding_model_name = embedding_model_name
        self._stores: dict[str, FAISSStore] = {}

    def _get_store(self, namespace: str) -> FAISSStore:
        if namespace not in self._stores:
            self._stores[namespace] = FAISSStore(
                namespace=namespace,
                ns_manager=self.ns_manager,
                dim=self.embedder.dimension,
            )
        return self._stores[namespace]

    async def ingest_file(self, file_path: str, namespace: str) -> IngestResult:
        # 압축 파일 감지: 단일 결과 인터페이스 유지를 위해 집계 결과 반환
        if _is_archive(file_path):
            results = await self.ingest_archive(file_path, namespace)
            total_chunks = sum(r.chunks_created for r in results)
            all_errors = []
            for r in results:
                all_errors.extend(r.errors)
            return IngestResult(
                doc_id=str(uuid.uuid4()),
                source_path=file_path,
                doc_type="archive",
                chunks_created=total_chunks,
                errors=all_errors + [f"_archive_results: {len(results)} files"],
                success=any(r.success for r in results),
            )

        doc_id = str(uuid.uuid4())

        # 1. 파싱
        parse_result = self.dispatcher.parse(file_path)
        if parse_result.errors and not parse_result.chunks:
            return IngestResult(
                doc_id=doc_id,
                source_path=file_path,
                doc_type=parse_result.doc_type,
                errors=parse_result.errors,
                success=False,
            )

        # 2. 청킹 전략 결정
        strategy = self._select_strategy(parse_result.doc_type)
        chunk_config = ChunkConfig(strategy=strategy)
        chunks = self.chunker.chunk(parse_result.chunks, chunk_config)

        if not chunks:
            return IngestResult(
                doc_id=doc_id, source_path=file_path,
                doc_type=parse_result.doc_type,
                errors=["청크가 생성되지 않았습니다."],
                success=False,
            )

        # 3. 임베딩
        texts = [c.content for c in chunks]
        embeddings = self.embedder.encode_texts(texts)

        # 4. 저장 — 문서 메타데이터
        from pathlib import Path as _Path
        doc = DocumentRecord(
            doc_id=doc_id,
            namespace=namespace,
            source_path=file_path,
            doc_type=parse_result.doc_type,
            title=_Path(file_path).name,
            created_at=datetime.utcnow(),
            metadata=parse_result.metadata,
        )
        await self.metadata_store.upsert_document(doc)

        # 5. 저장 — 청크 + 벡터
        chunk_ids = []
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
            chunk_id = f"{doc_id}_{i}"
            chunk_ids.append(chunk_id)
            cr = ChunkRecord(
                chunk_id=chunk_id,
                doc_id=doc_id,
                namespace=namespace,
                content=chunk.content,
                chunk_index=i,
                page_or_line=chunk.page_or_line,
                language=chunk.language,
                token_count=len(chunk.content.split()),
                embedding_model=self.embedding_model_name,
                created_at=datetime.utcnow(),
                metadata=chunk.metadata,
            )
            await self.metadata_store.upsert_chunk(cr)

        store = self._get_store(namespace)
        import numpy as np
        store.add(np.array(embeddings, dtype="float32"), chunk_ids)

        return IngestResult(
            doc_id=doc_id,
            source_path=file_path,
            doc_type=parse_result.doc_type,
            chunks_created=len(chunks),
            errors=parse_result.errors,
            success=True,
        )

    def _select_strategy(self, doc_type: str) -> ChunkStrategy:
        if doc_type in ("code", "excel", "pptx"):
            return ChunkStrategy.AS_IS
        return ChunkStrategy.SLIDING_WINDOW

    async def ingest_archive(self, file_path: str, namespace: str) -> list[IngestResult]:
        """압축 파일을 임시 디렉터리에 풀어 내부 파일을 모두 인제스트합니다."""
        results: list[IngestResult] = []
        temp_dir = Path(tempfile.mkdtemp(prefix="rag_arc_"))

        try:
            self._extract(file_path, temp_dir)

            count = 0
            for entry in temp_dir.rglob("*"):
                if not entry.is_file():
                    continue
                count += 1
                if count > MAX_ARCHIVE_FILES:
                    results.append(IngestResult(
                        doc_id="", source_path=str(entry), doc_type="archive",
                        errors=[f"파일 수 제한({MAX_ARCHIVE_FILES}) 초과"],
                        success=False,
                    ))
                    break
                try:
                    res = await self.ingest_file(str(entry), namespace)
                    res.source_path = f"{Path(file_path).name}::{entry.relative_to(temp_dir)}"
                    results.append(res)
                except Exception as e:
                    results.append(IngestResult(
                        doc_id="", source_path=str(entry), doc_type="unknown",
                        errors=[f"인제스트 실패: {e}"],
                        success=False,
                    ))
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        if not results:
            results.append(IngestResult(
                doc_id="", source_path=file_path, doc_type="archive",
                errors=["압축 파일 안에 처리 가능한 파일이 없습니다."],
                success=False,
            ))
        return results

    def _extract(self, file_path: str, temp_dir: Path) -> None:
        """Zip-slip 방어 + 크기 제한을 적용한 압축 해제."""
        path_lower = file_path.lower()
        total_size = 0

        if path_lower.endswith(".zip"):
            with zipfile.ZipFile(file_path) as zf:
                for member in zf.infolist():
                    if member.is_dir():
                        continue
                    target = (temp_dir / member.filename).resolve()
                    if not str(target).startswith(str(temp_dir.resolve())):
                        raise ValueError(f"잘못된 압축 경로: {member.filename}")
                    total_size += member.file_size
                    if total_size > MAX_ARCHIVE_SIZE:
                        raise ValueError(f"압축 해제 크기가 {MAX_ARCHIVE_SIZE} 초과")
                zf.extractall(temp_dir)
        elif any(path_lower.endswith(e) for e in (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")):
            with tarfile.open(file_path) as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    target = (temp_dir / member.name).resolve()
                    if not str(target).startswith(str(temp_dir.resolve())):
                        raise ValueError(f"잘못된 압축 경로: {member.name}")
                    total_size += member.size
                    if total_size > MAX_ARCHIVE_SIZE:
                        raise ValueError(f"압축 해제 크기가 {MAX_ARCHIVE_SIZE} 초과")
                tf.extractall(temp_dir)
        else:
            raise ValueError(f"지원하지 않는 압축 형식: {file_path}")
