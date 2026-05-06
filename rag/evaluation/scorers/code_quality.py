from __future__ import annotations

import ast

from .base import Scorer, ScoreResult


class CodeQualityScorer(Scorer):
    """코드 블록이 있으면 Python 파싱 가능 여부를 확인합니다."""

    @property
    def name(self) -> str:
        return "code_quality"

    async def score(self, query: str, answer: str, context: str) -> ScoreResult:
        # 코드 블록 추출
        import re
        code_blocks = re.findall(r"```(?:python)?\n?(.*?)```", answer, re.DOTALL)
        if not code_blocks:
            return ScoreResult(
                scorer=self.name, score=0.8, passed=True,
                feedback="코드 블록 없음"
            )

        parse_errors = []
        for block in code_blocks:
            try:
                ast.parse(block)
            except SyntaxError as e:
                parse_errors.append(str(e))

        if parse_errors:
            return ScoreResult(
                scorer=self.name,
                score=max(0.0, 1.0 - 0.3 * len(parse_errors)),
                passed=False,
                feedback=f"구문 오류 {len(parse_errors)}건: {parse_errors[0]}",
            )
        return ScoreResult(
            scorer=self.name, score=1.0, passed=True,
            feedback=f"코드 블록 {len(code_blocks)}개 파싱 성공"
        )
