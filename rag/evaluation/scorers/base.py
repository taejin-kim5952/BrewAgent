from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ScoreResult:
    scorer: str
    score: float  # 0.0 ~ 1.0
    passed: bool
    feedback: str = ""


class Scorer(ABC):

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    async def score(self, query: str, answer: str, context: str) -> ScoreResult:
        ...
