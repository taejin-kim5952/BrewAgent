from __future__ import annotations

import asyncio
import time
import uuid
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..dependencies import AppContainer, get_container
from ...dataset.interaction_logger import InteractionRecord
from ...query.retriever import HybridRetriever
from ...llm_router.backends.base import GenerateParams

router = APIRouter()


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    model: str = "rag-local"
    messages: list[Message]
    stream: bool = False
    temperature: float = 0.2
    max_tokens: int = 2048
    namespace: str = "default"
    enable_rag: bool = True
    top_k_chunks: int = 10


class ChatResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[dict]
    usage: dict
    rag_sources: list[dict] | None = None


@router.post("/v1/chat/completions")
async def chat_completions(
    req: ChatRequest,
    container: AppContainer = Depends(get_container),
):
    start_time = time.time()
    interaction_id = str(uuid.uuid4())

    # 마지막 사용자 메시지 추출
    user_query = ""
    for msg in reversed(req.messages):
        if msg.role == "user":
            user_query = msg.content
            break

    history = [{"role": m.role, "content": m.content} for m in req.messages[:-1]]

    # 쿼리 분석
    analysis = container.intelligence.analyze(user_query, history)

    # RAG 검색
    retrieved_chunks = []
    context_text = ""
    if req.enable_rag:
        faiss_store = container.get_faiss_store(req.namespace)
        retriever = HybridRetriever(
            faiss_store=faiss_store,
            metadata_store=container.metadata_store,
            embedder=container.embedder,
            top_k=req.top_k_chunks,
        )
        retrieved_chunks = await retriever.retrieve(analysis, req.namespace)
        retrieved_chunks = container.context_optimizer.optimize(
            retrieved_chunks, user_query,
            max_tokens=container.settings.retrieval.max_context_tokens,
        )
        context_text = "\n\n".join(c.content for c in retrieved_chunks)

    # 프롬프트 생성
    built_prompt = container.prompt_builder.build(
        query=user_query,
        chunks=retrieved_chunks,
        intent=analysis.intent,
        history=history,
    )

    # LLM 라우팅
    routing_decision, backend = container.llm_router.route(analysis)
    params = GenerateParams(
        temperature=req.temperature,
        max_tokens=req.max_tokens,
        system_prompt=built_prompt.system,
    )

    rag_sources = [
        {
            "chunk_id": c.chunk_id,
            "source_file": c.source_path.split("/")[-1] if c.source_path else "",
            "page_or_line": c.page_or_line,
            "score": round(c.score, 3),
            "snippet": c.content[:200],
        }
        for c in retrieved_chunks[:5]
    ]

    if req.stream:
        async def generate_stream() -> AsyncIterator[str]:
            full_response = ""
            async for token in backend.stream(built_prompt.user, params):
                full_response += token
                chunk_data = {
                    "id": interaction_id,
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": req.model,
                    "choices": [{"delta": {"content": token}, "index": 0, "finish_reason": None}],
                }
                import json
                yield f"data: {json.dumps(chunk_data, ensure_ascii=False)}\n\n"

            yield 'data: [DONE]\n\n'

            # 백그라운드: 평가 + 로깅
            latency = int((time.time() - start_time) * 1000)
            asyncio.create_task(
                _log_and_eval(
                    container, interaction_id, req, analysis, full_response,
                    retrieved_chunks, routing_decision.value, backend.model_name,
                    context_text, latency,
                )
            )

        return StreamingResponse(generate_stream(), media_type="text/event-stream")

    # 논-스트리밍
    full_response = await backend.generate(built_prompt.user, params)
    latency = int((time.time() - start_time) * 1000)

    asyncio.create_task(
        _log_and_eval(
            container, interaction_id, req, analysis, full_response,
            retrieved_chunks, routing_decision.value, backend.model_name,
            context_text, latency,
        )
    )

    return ChatResponse(
        id=interaction_id,
        created=int(time.time()),
        model=req.model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": full_response},
                "finish_reason": "stop",
            }
        ],
        usage={
            "prompt_tokens": built_prompt.estimated_tokens,
            "completion_tokens": len(full_response.split()),
            "total_tokens": built_prompt.estimated_tokens + len(full_response.split()),
        },
        rag_sources=rag_sources if rag_sources else None,
    )


async def _log_and_eval(
    container, interaction_id, req, analysis, full_response,
    retrieved_chunks, routing, model_name, context_text, latency,
):
    """백그라운드 평가 + 로깅."""
    try:
        eval_result = await container.eval_engine.evaluate(
            interaction_id=interaction_id,
            query=req.messages[-1].content if req.messages else "",
            answer=full_response,
            context=context_text,
        )

        record = InteractionRecord(
            interaction_id=interaction_id,
            namespace=req.namespace,
            query=req.messages[-1].content if req.messages else "",
            rewritten_query=analysis.rewritten_queries[0] if analysis.rewritten_queries else "",
            intent=analysis.intent.value,
            response=full_response,
            model_used=model_name,
            routing=routing,
            chunk_ids=[c.chunk_id for c in retrieved_chunks],
            eval_score=eval_result.overall_score,
            latency_ms=latency,
            context_text=context_text[:2000],
        )
        await container.interaction_logger.log(record)
        await container.interaction_logger.update_eval_score(
            interaction_id, eval_result.overall_score, eval_result.scores
        )
    except Exception:
        pass  # 로깅 실패가 응답에 영향 주지 않도록
