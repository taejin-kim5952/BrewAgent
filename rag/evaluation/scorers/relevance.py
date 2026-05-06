from __future__ import annotations

from .base import Scorer, ScoreResult


class RelevanceScorer(Scorer):
    """쿼리와 답변의 단어 중복도로 관련성을 측정합니다."""

    @property
    def name(self) -> str:
        return "relevance"

    async def score(self, query: str, answer: str, context: str) -> ScoreResult:
        q_words = set(query.lower().split())
        a_words = set(answer.lower().split())
        if not q_words:
            return ScoreResult(scorer=self.name, score=0.0, passed=False, feedback="쿼리가 비어있습니다.")

        overlap = len(q_words & a_words) / len(q_words)
        passed = overlap >= 0.1
        return ScoreResult(
            scorer=self.name,
            score=min(overlap * 2, 1.0),
            passed=passed,
            feedback=f"쿼리 단어 {overlap:.0%} 포함",
        )
