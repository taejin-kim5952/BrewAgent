from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from ..configs import get_settings, Settings
from ..ingest import Dispatcher, Chunker, Embedder, IngestPipeline
from ..vector_db import NamespaceManager, MetadataStore, FAISSStore
from ..query import QueryIntelligence, ContextOptimizer
from ..llm_router import LLMRouter, PromptBuilder, OllamaBackend, OpenAIBackend
from ..evaluation import EvaluationEngine
from ..memory import KnowledgeStore, ResponseCache
from ..dataset import InteractionLogger, JSONLExporter
from ..tools import default_registry, ToolExecutor


class AppContainer:
    """애플리케이션 전역 의존성 컨테이너."""

    def __init__(self, settings: Settings):
        self.settings = settings
        settings.ensure_storage_dirs()

        # 임베딩
        self.embedder = Embedder(
            model_name=settings.embedding.model_name,
            device=settings.embedding.device,
        )

        # 벡터 DB
        self.ns_manager = NamespaceManager(settings.storage.indices_dir)
        self.metadata_store = MetadataStore(settings.storage.metadata_db)

        # 인제스트
        self.pipeline = IngestPipeline(
            dispatcher=Dispatcher(),
            chunker=Chunker(),
            embedder=self.embedder,
            ns_manager=self.ns_manager,
            metadata_store=self.metadata_store,
            embedding_model_name=settings.embedding.model_name,
        )

        # Query
        self.intelligence = QueryIntelligence()
        self.context_optimizer = ContextOptimizer()

        # LLM Router
        fast_backend = OllamaBackend(
            base_url=settings.ollama.base_url,
            model=settings.ollama.model_fast,
            timeout=settings.ollama.timeout_seconds,
        )
        full_backend = OllamaBackend(
            base_url=settings.ollama.base_url,
            model=settings.ollama.model_full,
            timeout=settings.ollama.timeout_seconds,
        )
        self.llm_router = LLMRouter(
            fast_backend=fast_backend,
            full_backend=full_backend,
            threshold_fast=settings.routing.complexity_threshold_fast,
            threshold_full=settings.routing.complexity_threshold_full,
            force_local=settings.routing.force_local,
        )
        self.prompt_builder = PromptBuilder()

        # Evaluation + Memory + Dataset
        self.eval_engine = EvaluationEngine()
        self.knowledge_store = KnowledgeStore(settings.storage.path / "knowledge")
        self.response_cache = ResponseCache(ttl_seconds=300)
        self.interaction_logger = InteractionLogger(settings.storage.interactions_db)
        self.exporter = JSONLExporter()

        # Tools
        self.tool_executor = ToolExecutor(default_registry())

        # FAISS 스토어 캐시 (네임스페이스별)
        self._faiss_stores: dict[str, FAISSStore] = {}

    def get_faiss_store(self, namespace: str) -> FAISSStore:
        if namespace not in self._faiss_stores:
            self._faiss_stores[namespace] = FAISSStore(
                namespace=namespace,
                ns_manager=self.ns_manager,
                dim=self.embedder.dimension,
            )
        return self._faiss_stores[namespace]

    async def startup(self) -> None:
        await self.metadata_store.init()
        await self.interaction_logger.init()

    async def shutdown(self) -> None:
        for store in self._faiss_stores.values():
            store.persist()


_container: AppContainer | None = None


def get_container() -> AppContainer:
    global _container
    if _container is None:
        _container = AppContainer(get_settings())
    return _container
