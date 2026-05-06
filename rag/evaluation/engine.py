from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .scorers.base import Scorer, ScoreResult
from .scorers.relevance import RelevanceScorer
from .scorers.faithfulness import FaithfulnessScorer
from .scorers.code_quality import CodeQualityScorer


@dataclass
class EvalResult:
    interaction_id: str
    overall_score: float
    scores: dict[str, float] = field(default_factory=dict)
    passed: bool = True
    feedback: str = ""


class EvaluationEngine:
    """비동기 백그라운드 품질 평가 엔진."""

    def __init__(self, scorers: list[Scorer] | None = None):
        self.scorers: list[Scorer] = scorers or [
            RelevanceScorer(),
            FaithfulnessScorer(),
            CodeQualityScorer(),
        ]

    async def evaluate(
        self,
        interaction_id: str,
        query: str,
        answer: str,
        context: str = "",
    ) -> EvalResult:
        tasks = [s.score(query, answer, context) for s in self.scorers]
        results: list[ScoreResult] = await asyncio.gather(*tasks)

        score_map = {r.scorer: r.score for r in results}
        overall = sum(score_map.values()) / len(score_map) if score_map else 0.0
        passed = all(r.passed for r in results)
        feedback = "; ".join(r.feedback for r in results if r.feedback)

        return EvalResult(
            interaction_id=interaction_id,
            overall_score=round(overall, 3),
            scores=score_map,
            passed=passed,
            feedback=feedback,
        )
