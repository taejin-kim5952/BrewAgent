from __future__ import annotations

from .base import Scorer, ScoreResult


class FaithfulnessScorer(Scorer):
    """답변이 컨텍스트에 근거하고 있는지 단어 중복도로 측정합니다."""

    @property
    def name(self) -> str:
        return "faithfulness"

    async def score(self, query: str, answer: str, context: str) -> ScoreResult:
        if not context.strip():
            return ScoreResult(
                scorer=self.name, score=0.5, passed=True,
                feedback="컨텍스트 없음 (일반 응답)"
            )

        a_words = set(answer.lower().split())
        c_words = set(context.lower().split())
        if not a_words:
            return ScoreResult(scorer=self.name, score=0.0, passed=False, feedback="빈 응답")

        grounded = len(a_words & c_words) / len(a_words)
        passed = grounded >= 0.2
        return ScoreResult(
            scorer=self.name,
            score=min(grounded * 2, 1.0),
            passed=passed,
            feedback=f"컨텍스트 단어 {grounded:.0%} 활용",
        )
