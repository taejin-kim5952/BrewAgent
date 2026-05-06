from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException
from pydantic import BaseModel

from ..dependencies import AppContainer, get_container
from ...ingest.pipeline import _is_archive
from ...ingest.parsers.base import TextChunk
from ...llm_router.backends.base import GenerateParams

router = APIRouter()


SUMMARY_LENGTH_PROMPTS = {
    "short": "3~5줄 이내의 핵심 요약",
    "medium": "10줄 내외의 균형 잡힌 요약",
    "long": "섹션/주제별로 나누어 자세히 정리한 요약",
}

SUMMARY_LANG_LABELS = {
    "ko": "한국어",
    "en": "English",
}

MAP_REDUCE_THRESHOLD = 8000  # 글자 수 임계값
CHUNK_GROUP_SIZE = 6  # map 단계에서 한 번에 묶을 청크 수


class SummarizeResponse(BaseModel):
    filename: str
    doc_type: str
    char_count: int
    chunk_count: int
    summary: str
    model_used: str
    mode: str  # "single" | "map_reduce"
    errors: list[str] = []


class IngestResponse(BaseModel):
    doc_id: str
    source_path: str
    doc_type: str
    chunks_created: int
    errors: list[str]
    success: bool
    archive_file_count: int | None = None  # 압축 파일 처리 시 추출된 파일 수


class BatchIngestRequest(BaseModel):
    namespace: str = "default"
    directory: str  # 서버 측 경로


class BatchIngestResponse(BaseModel):
    total_files: int
    succeeded: int
    failed: int
    results: list[IngestResponse]


@router.post("/v1/ingest/file", response_model=IngestResponse)
async def ingest_file(
    namespace: str = Form("default"),
    file: UploadFile = File(...),
    container: AppContainer = Depends(get_container),
):
    """파일 업로드 후 인덱싱."""
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / file.filename
    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        result = await container.pipeline.ingest_file(str(tmp_path), namespace)
        # 압축 파일이면 errors 안에 _archive_results 마커가 들어있음
        archive_count = None
        clean_errors = []
        for e in result.errors:
            if e.startswith("_archive_results: "):
                try:
                    archive_count = int(e.split(":")[1].strip().split()[0])
                except Exception:
                    pass
            else:
                clean_errors.append(e)
        return IngestResponse(
            doc_id=result.doc_id,
            source_path=result.source_path,
            doc_type=result.doc_type,
            chunks_created=result.chunks_created,
            errors=clean_errors,
            success=result.success,
            archive_file_count=archive_count,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


@router.post("/v1/ingest/batch", response_model=BatchIngestResponse)
async def ingest_batch(
    req: BatchIngestRequest,
    container: AppContainer = Depends(get_container),
):
    """서버 측 디렉터리의 파일 일괄 인덱싱."""
    dir_path = Path(req.directory)
    if not dir_path.exists() or not dir_path.is_dir():
        raise HTTPException(status_code=400, detail=f"디렉터리를 찾을 수 없습니다: {req.directory}")

    files = [f for f in dir_path.rglob("*") if f.is_file()]
    results = []
    succeeded = 0
    failed = 0

    for file_path in files:
        result = await container.pipeline.ingest_file(str(file_path), req.namespace)
        results.append(IngestResponse(**result.__dict__))
        if result.success:
            succeeded += 1
        else:
            failed += 1

    return BatchIngestResponse(
        total_files=len(files),
        succeeded=succeeded,
        failed=failed,
        results=results,
    )


def _select_backend(container: AppContainer, model_choice: str):
    if model_choice == "full":
        return container.llm_router.full_backend
    return container.llm_router.fast_backend


def _build_summary_prompt(content: str, length: str, language: str) -> str:
    length_desc = SUMMARY_LENGTH_PROMPTS.get(length, SUMMARY_LENGTH_PROMPTS["medium"])
    lang_label = SUMMARY_LANG_LABELS.get(language, SUMMARY_LANG_LABELS["ko"])
    return (
        f"다음 문서를 {lang_label}로 요약해주세요. 분량: {length_desc}.\n"
        f"중요한 핵심 내용, 결론, 주요 데이터를 빠짐없이 포함하세요.\n"
        f"요약은 마크다운 형식으로 작성하세요.\n\n"
        f"[문서 내용]\n{content}\n\n"
        f"[요약]"
    )


def _build_reduce_prompt(partials: list[str], length: str, language: str) -> str:
    length_desc = SUMMARY_LENGTH_PROMPTS.get(length, SUMMARY_LENGTH_PROMPTS["medium"])
    lang_label = SUMMARY_LANG_LABELS.get(language, SUMMARY_LANG_LABELS["ko"])
    joined = "\n\n---\n\n".join(f"[부분 요약 {i+1}]\n{p}" for i, p in enumerate(partials))
    return (
        f"아래는 한 문서를 여러 부분으로 나눠 각각 요약한 결과입니다. "
        f"이를 통합하여 {lang_label}로 {length_desc} 분량의 최종 요약을 작성하세요.\n"
        f"중복은 제거하고 주제별로 정리하세요.\n\n"
        f"{joined}\n\n[최종 요약]"
    )


@router.post("/v1/ingest/summarize", response_model=SummarizeResponse)
async def summarize_document(
    file: UploadFile = File(...),
    length: str = Form("medium"),       # short | medium | long
    language: str = Form("ko"),         # ko | en
    model_choice: str = Form("fast"),   # fast | full
    container: AppContainer = Depends(get_container),
):
    """문서를 업로드하면 Ollama로 요약합니다 (인덱싱은 하지 않음)."""
    tmp_dir = Path(tempfile.mkdtemp())
    tmp_path = tmp_dir / file.filename
    errors: list[str] = []

    try:
        with open(tmp_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # 압축 파일이면 풀어서 내부 모든 파일을 파싱하여 청크로 합침
        all_chunks: list[TextChunk] = []
        archive_file_count = 0
        archive_inner_files: list[str] = []
        doc_type_label = ""

        if _is_archive(str(tmp_path)):
            extract_dir = Path(tempfile.mkdtemp(prefix="rag_sum_arc_"))
            try:
                container.pipeline._extract(str(tmp_path), extract_dir)
                for entry in extract_dir.rglob("*"):
                    if not entry.is_file():
                        continue
                    archive_file_count += 1
                    archive_inner_files.append(str(entry.relative_to(extract_dir)))
                    try:
                        pr = container.pipeline.dispatcher.parse(str(entry))
                        if pr.chunks:
                            header = TextChunk(
                                content=f"\n=== [{entry.relative_to(extract_dir)}] ===\n",
                            )
                            all_chunks.append(header)
                            all_chunks.extend(pr.chunks)
                        if pr.errors:
                            errors.extend(f"{entry.name}: {e}" for e in pr.errors)
                    except Exception as e:
                        errors.append(f"{entry.name} 파싱 실패: {e}")
            finally:
                shutil.rmtree(extract_dir, ignore_errors=True)

            if not all_chunks:
                raise HTTPException(
                    status_code=400,
                    detail=f"압축 파일 안에서 텍스트를 추출하지 못했습니다. (파일 {archive_file_count}개)",
                )
            doc_type_label = f"archive ({archive_file_count}개 파일)"
        else:
            parse_result = container.pipeline.dispatcher.parse(str(tmp_path))
            if not parse_result.chunks:
                raise HTTPException(
                    status_code=400,
                    detail=f"문서에서 텍스트를 추출하지 못했습니다: {parse_result.errors or '내용 없음'}",
                )
            all_chunks = parse_result.chunks
            doc_type_label = parse_result.doc_type
            if parse_result.errors:
                errors.extend(parse_result.errors)

        full_text = "\n\n".join(c.content for c in all_chunks)
        char_count = len(full_text)
        backend = _select_backend(container, model_choice)
        params = GenerateParams(temperature=0.3, max_tokens=1500)

        if char_count <= MAP_REDUCE_THRESHOLD:
            mode = "single"
            prompt = _build_summary_prompt(full_text, length, language)
            summary = await backend.generate(prompt, params)
        else:
            mode = "map_reduce"
            partials: list[str] = []
            for i in range(0, len(all_chunks), CHUNK_GROUP_SIZE):
                group_text = "\n\n".join(c.content for c in all_chunks[i:i + CHUNK_GROUP_SIZE])
                p_prompt = _build_summary_prompt(group_text, "short", language)
                try:
                    partials.append(await backend.generate(p_prompt, params))
                except Exception as e:
                    errors.append(f"부분 요약 실패 (그룹 {i // CHUNK_GROUP_SIZE + 1}): {e}")
            if not partials:
                raise HTTPException(status_code=500, detail="모든 부분 요약이 실패했습니다.")
            reduce_prompt = _build_reduce_prompt(partials, length, language)
            summary = await backend.generate(reduce_prompt, params)

        return SummarizeResponse(
            filename=file.filename,
            doc_type=doc_type_label,
            char_count=char_count,
            chunk_count=len(all_chunks),
            summary=summary.strip(),
            model_used=backend.model_name,
            mode=mode,
            errors=errors,
        )
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
