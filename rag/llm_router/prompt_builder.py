from __future__ import annotations

from dataclasses import dataclass

from ..query.intelligence import QueryIntent
from ..query.retriever import RetrievedChunk


@dataclass
class BuiltPrompt:
    system: str
    user: str
    estimated_tokens: int
    context_sources: list[str]


_SYSTEM_PROMPTS: dict[QueryIntent, str] = {
    QueryIntent.CODE_GENERATION: (
        "당신은 숙련된 소프트웨어 개발자입니다. "
        "제공된 코드베이스 컨텍스트를 참고하여 정확하고 실행 가능한 코드를 작성해주세요. "
        "코드는 기존 스타일과 패턴을 따라야 합니다."
    ),
    QueryIntent.CODE_EXPLANATION: (
        "당신은 코드 리뷰어입니다. "
        "제공된 코드를 분석하여 명확하고 이해하기 쉽게 설명해주세요. "
        "목적, 동작 방식, 주요 로직을 포함하세요."
    ),
    QueryIntent.DEBUGGING: (
        "당신은 디버깅 전문가입니다. "
        "제공된 코드와 오류 정보를 분석하여 문제의 원인을 파악하고 해결책을 제시해주세요."
    ),
    QueryIntent.DOCUMENTATION: (
        "당신은 기술 문서 작성자입니다. "
        "제공된 정보를 바탕으로 명확하고 구조화된 문서를 작성해주세요."
    ),
    QueryIntent.COMPARISON: (
        "당신은 기술 분석가입니다. "
        "제공된 정보를 바탕으로 객관적인 비교 분석을 제공해주세요."
    ),
    QueryIntent.FACTUAL: (
        "당신은 도움이 되는 AI 어시스턴트입니다. "
        "제공된 컨텍스트를 바탕으로 정확하고 유용한 답변을 제공해주세요."
    ),
    QueryIntent.CONVERSATIONAL: (
        "당신은 도움이 되는 AI 어시스턴트입니다. 친절하고 명확하게 답변해주세요."
    ),
}

_DEFAULT_SYSTEM = "당신은 도움이 되는 AI 어시스턴트입니다."


class PromptBuilder:
    """검색된 컨텍스트 + 쿼리 + 히스토리를 조합하여 최종 프롬프트를 생성합니다."""

    def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        intent: QueryIntent,
        history: list[dict] | None = None,
    ) -> BuiltPrompt:
        system = _SYSTEM_PROMPTS.get(intent, _DEFAULT_SYSTEM)
        context_parts = []
        sources = []

        for chunk in chunks:
            source_label = self._format_source(chunk)
            if chunk.language:
                context_parts.append(
                    f"```{chunk.language}\n# 출처: {source_label}\n{chunk.content}\n```"
                )
            else:
                context_parts.append(f"[출처: {source_label}]\n{chunk.content}")
            sources.append(source_label)

        context_str = "\n\n".join(context_parts)
        history_str = self._format_history(history or [])

        if context_str:
            user_prompt = (
                f"{history_str}"
                f"## 참고 자료\n{context_str}\n\n"
                f"## 질문\n{query}"
            )
        else:
            user_prompt = f"{history_str}## 질문\n{query}"

        estimated_tokens = int(
            (len(system) + len(user_prompt)) / 4
        )  # 대략 4자 = 1토큰

        return BuiltPrompt(
            system=system,
            user=user_prompt,
            estimated_tokens=estimated_tokens,
            context_sources=list(dict.fromkeys(sources)),  # 중복 제거
        )

    def _format_source(self, chunk: RetrievedChunk) -> str:
        from pathlib import Path
        name = Path(chunk.source_path).name if chunk.source_path else "unknown"
        if chunk.page_or_line:
            return f"{name}:{chunk.page_or_line}"
        return name

    def _format_history(self, history: list[dict], max_turns: int = 3) -> str:
        if not history:
            return ""
        recent = history[-max_turns * 2:]
        parts = []
        for msg in recent:
            role = "사용자" if msg.get("role") == "user" else "AI"
            parts.append(f"{role}: {msg.get('content', '')}")
        return "## 대화 기록\n" + "\n".join(parts) + "\n\n"
