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
    format: str = "openai"  # openai | alpaca | sharegpt


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
    records = await container.interaction_logger.query_interactions(
        namespace=req.namespace,
        min_rating=req.min_rating,
        min_eval_score=req.min_eval_score,
        limit=10000,
    )
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
        "download_url": f"/v1/dataset/exports/{filename}",
    }


@router.get("/v1/dataset/exports/{filename}")
async def download_export(
    filename: str,
    container: AppContainer = Depends(get_container),
):
    file_path = container.settings.storage.exports_dir / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다.")
    return FileResponse(path=str(file_path), filename=filename, media_type="application/octet-stream")
