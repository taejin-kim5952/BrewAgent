from __future__ import annotations

from enum import Enum

from ..query.intelligence import QueryAnalysis
from .backends.base import LLMBackend, GenerateParams
from .backends.ollama_backend import OllamaBackend


class RoutingDecision(str, Enum):
    LOCAL_FAST = "local_fast"    # 경량 모델 (gemma3:4b)
    LOCAL_FULL = "local_full"    # 풀 모델 (gemma3:12b)
    EXTERNAL = "external"        # 외부 API


class LLMRouter:
    """쿼리 복잡도에 따라 적절한 LLM 백엔드를 선택합니다."""

    def __init__(
        self,
        fast_backend: LLMBackend,
        full_backend: LLMBackend,
        external_backend: LLMBackend | None = None,
        threshold_fast: float = 0.3,
        threshold_full: float = 0.7,
        force_local: bool = True,
    ):
        self.fast_backend = fast_backend
        self.full_backend = full_backend
        self.external_backend = external_backend
        self.threshold_fast = threshold_fast
        self.threshold_full = threshold_full
        self.force_local = force_local

    def route(self, analysis: QueryAnalysis) -> tuple[RoutingDecision, LLMBackend]:
        score = analysis.complexity_score

        if self.force_local or self.external_backend is None or not self.external_backend.is_available():
            if score < self.threshold_fast:
                return RoutingDecision.LOCAL_FAST, self.fast_backend
            return RoutingDecision.LOCAL_FULL, self.full_backend

        if score < self.threshold_fast:
            return RoutingDecision.LOCAL_FAST, self.fast_backend
        if score < self.threshold_full:
            return RoutingDecision.LOCAL_FULL, self.full_backend
        return RoutingDecision.EXTERNAL, self.external_backend
