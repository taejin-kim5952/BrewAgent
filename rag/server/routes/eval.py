from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..dependencies import AppContainer, get_container

router = APIRouter()


class EvalRequest(BaseModel):
    interaction_id: str


@router.post("/v1/eval/run")
async def run_eval(
    req: EvalRequest,
    container: AppContainer = Depends(get_container),
):
    records = await container.interaction_logger.query_interactions(limit=1)
    target = None
    for r in await container.interaction_logger.query_interactions(limit=10000):
        if r.interaction_id == req.interaction_id:
            target = r
            break

    if not target:
        raise HTTPException(status_code=404, detail="인터랙션을 찾을 수 없습니다.")

    result = await container.eval_engine.evaluate(
        interaction_id=target.interaction_id,
        query=target.query,
        answer=target.response,
        context=target.context_text,
    )

    await container.interaction_logger.update_eval_score(
        target.interaction_id, result.overall_score, result.scores
    )

    return {
        "interaction_id": result.interaction_id,
        "overall_score": result.overall_score,
        "scores": result.scores,
        "passed": result.passed,
        "feedback": result.feedback,
    }
