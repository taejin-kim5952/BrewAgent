from __future__ import annotations

import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from .access_log_middleware import AccessLogMiddleware
from .dependencies import get_container
from .routes import (
    chat_router,
    ingest_router,
    collections_router,
    dataset_router,
    eval_router,
    guide_router,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 훅."""
    logger.info("RAG Platform 서버 시작 중...")
    container = get_container()
    await container.startup()
    logger.info(f"임베딩 모델: {container.settings.embedding.model_name}")
    logger.info(f"Ollama URL: {container.settings.ollama.base_url}")
    logger.info(f"스토리지: {container.settings.storage.path}")
    logger.info("서버 준비 완료.")
    yield
    logger.info("서버 종료 중...")
    await container.shutdown()


app = FastAPI(
    title="RAG Platform API",
    description="Multimodal RAG Platform with Fine-tuning Intelligence",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS (Continue.dev 로컬 요청 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 라우터 등록
app.include_router(chat_router)
app.include_router(ingest_router)
app.include_router(collections_router)
app.include_router(dataset_router)
app.include_router(eval_router)
app.include_router(guide_router)

_STATIC_DIR = Path(__file__).resolve().parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=str(_STATIC_DIR), html=True), name="ui")
else:
    logger.warning(f"Admin UI static dir missing: {_STATIC_DIR}")


@app.get("/")
async def root_redirect():
    """훈련 데이터 관리 웹 UI로 이동."""
    return RedirectResponse(url="/ui/index.html")


@app.get("/health")
async def health_check():
    container = get_container()
    ollama_ok = container.llm_router.fast_backend.is_available()
    return {
        "status": "healthy",
        "timestamp": int(time.time()),
        "components": {
            "ollama": "ok" if ollama_ok else "unavailable",
            "vector_db": "ok",
            "metadata_db": "ok",
        },
        "storage": str(container.settings.storage.path),
    }


@app.get("/v1/models")
async def list_models():
    container = get_container()
    return {
        "object": "list",
        "data": [
            {"id": "rag-local", "object": "model", "owned_by": "rag-platform"},
            {"id": container.settings.ollama.model_fast, "object": "model", "owned_by": "ollama"},
            {"id": container.settings.ollama.model_full, "object": "model", "owned_by": "ollama"},
        ],
    }


# 가장 바깥에서 요청 단위 로깅 (CORS 이후 등록 = 요청 시 먼저 실행)
app.add_middleware(AccessLogMiddleware)
