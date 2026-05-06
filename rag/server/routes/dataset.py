from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..dependencies import AppContainer, get_container

router = APIRouter()


class RatingRequest(BaseModel):
    rating: int  # 1-5


class ExportRequest(BaseModel):
    namespace: str | None = None
    min_rating: int | None = None
    min_eval_score: float | None = None
    format: str = "openai"            # openai | alpaca | sharegpt
    include_interactions: bool = True  # Continue.dev 대화 기록 포함
    include_manual: bool = True        # 수동 입력 데이터 포함
    include_guide_qa: bool = True      # 승인된 가이드 Q&A 포함
    guide_id: str | None = None        # 특정 가이드만 (None이면 전체 승인된 Q&A)


class InteractionSummary(BaseModel):
    interaction_id: str
    namespace: str
    query: str
    response: str
    eval_score: float | None
    user_rating: int | None
    routing: str
    created_at: str


class InteractionListResponse(BaseModel):
    total: int
    items: list[InteractionSummary]


class ManualEntryRequest(BaseModel):
    instruction: str
    output: str


@router.get("/v1/dataset/interactions", response_model=InteractionListResponse)
async def list_interactions(
    namespace: str | None = None,
    min_rating: int | None = None,
    min_eval_score: float | None = None,
    limit: int = 50,
    offset: int = 0,
    container: AppContainer = Depends(get_container),
):
    records = await container.interaction_logger.query_interactions(
        namespace=namespace,
        min_rating=min_rating,
        min_eval_score=min_eval_score,
        limit=limit,
        offset=offset,
    )
    items = [
        InteractionSummary(
            interaction_id=r.interaction_id,
            namespace=r.namespace,
            query=r.query[:200],
            response=r.response[:300],
            eval_score=r.eval_score,
            user_rating=r.user_rating,
            routing=r.routing,
            created_at=r.created_at,
        )
        for r in records
    ]
    return InteractionListResponse(total=len(items), items=items)


@router.patch("/v1/dataset/interactions/{interaction_id}/rating")
async def rate_interaction(
    interaction_id: str,
    req: RatingRequest,
    container: AppContainer = Depends(get_container),
):
    if not (1 <= req.rating <= 5):
        raise HTTPException(status_code=400, detail="평점은 1~5 사이여야 합니다.")
    await container.interaction_logger.update_rating(interaction_id, req.rating)
    return {"interaction_id": interaction_id, "rating": req.rating}


@router.post("/v1/dataset/export")
async def export_dataset(
    req: ExportRequest,
    container: AppContainer = Depends(get_container),
):
    from ...dataset.interaction_logger import InteractionRecord

    records: list[InteractionRecord] = []
    source_counts = {"interactions": 0, "manual": 0, "guide_qa": 0}

    # 1) Continue.dev 인터랙션 (기존)
    if req.include_interactions:
        interactions = await container.interaction_logger.query_interactions(
            namespace=req.namespace,
            min_rating=req.min_rating,
            min_eval_score=req.min_eval_score,
            limit=10000,
        )
        records.extend(interactions)
        source_counts["interactions"] = len(interactions)

    # 2) 수동 입력 항목
    if req.include_manual:
        manual = await container.interaction_logger.list_manual(limit=10000)
        for m in manual:
            records.append(InteractionRecord(
                interaction_id=m.get("entry_id", ""),
                namespace="manual",
                query=m.get("instruction", ""),
                rewritten_query=m.get("instruction", ""),
                intent="manual",
                response=m.get("output", ""),
                model_used="manual",
                routing="manual",
                chunk_ids=[],
                created_at=m.get("created_at", ""),
            ))
        source_counts["manual"] = len(manual)

    # 3) 가이드에서 추출된 승인된 Q&A
    if req.include_guide_qa:
        if req.guide_id:
            qa_records = await container.guide_store.list_qa(
                guide_id=req.guide_id, status="approved",
            )
        else:
            qa_records = await container.guide_store.list_approved_qa()
        for q in qa_records:
            records.append(InteractionRecord(
                interaction_id=q.qa_id,
                namespace=f"guide:{q.guide_id[:8]}",
                query=q.instruction,
                rewritten_query=q.instruction,
                intent=q.qa_type,
                response=q.output,
                model_used="guide_synthesis",
                routing="guide_qa",
                chunk_ids=[q.rule_id],
                created_at=q.created_at,
            ))
        source_counts["guide_qa"] = len(qa_records)

    if not records:
        raise HTTPException(status_code=404, detail="내보낼 데이터가 없습니다.")

    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"finetune_{req.format}_{timestamp}.jsonl"
    output_path = container.settings.storage.exports_dir / filename

    if req.format == "alpaca":
        result = container.exporter.export_alpaca(records, output_path)
    elif req.format == "sharegpt":
        result = container.exporter.export_sharegpt(records, output_path)
    else:
        result = container.exporter.export_openai(records, output_path)

    return {
        "filename": filename,
        "record_count": result.record_count,
        "format": result.format,
        "sources": source_counts,
        "download_url": f"/v1/dataset/exports/{filename}",
    }


@router.post("/v1/dataset/manual")
async def add_manual_entry(
    req: ManualEntryRequest,
    container: AppContainer = Depends(get_container),
):
    if not req.instruction.strip() or not req.output.strip():
        raise HTTPException(status_code=400, detail="질문과 답변을 모두 입력해주세요.")
    entry_id = await container.interaction_logger.log_manual(req.instruction, req.output)
    return {"entry_id": entry_id, "status": "saved"}


@router.get("/v1/dataset/manual")
async def list_manual_entries(
    limit: int = 100,
    offset: int = 0,
    container: AppContainer = Depends(get_container),
):
    entries = await container.interaction_logger.list_manual(limit=limit, offset=offset)
    return {"total": len(entries), "items": entries}


@router.delete("/v1/dataset/manual/{entry_id}")
async def delete_manual_entry(
    entry_id: str,
    container: AppContainer = Depends(get_container),
):
    deleted = await container.interaction_logger.delete_manual(entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="항목을 찾을 수 없습니다.")
    return {"entry_id": entry_id, "status": "deleted"}


@router.get("/v1/dataset/exports/{filename}")
async def download_export(
    filename: str,
    container: AppContainer = Depends(get_container),
):
    file_path = container.settings.storage.exports_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")
