from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class GenerateParams:
    temperature: float = 0.2
    max_tokens: int = 2048
    top_p: float = 0.95
    stop_sequences: list[str] = field(default_factory=list)
    system_prompt: str | None = None


class LLMBackend(ABC):

    @abstractmethod
    async def generate(self, prompt: str, params: GenerateParams) -> str:
        ...

    @abstractmethod
    async def stream(self, prompt: str, params: GenerateParams) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def is_available(self) -> bool:
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        ...
