from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class QueryIntent(str, Enum):
    CODE_GENERATION = "code_gen"
    CODE_EXPLANATION = "code_explain"
    DOCUMENTATION = "doc_lookup"
    DEBUGGING = "debug"
    COMPARISON = "comparison"
    FACTUAL = "factual"
    CONVERSATIONAL = "conversational"


@dataclass
class MetadataFilter:
    language: str | None = None
    file_name: str | None = None
    doc_type: str | None = None


@dataclass
class QueryAnalysis:
    original: str
    intent: QueryIntent
    rewritten_queries: list[str]
    filters: MetadataFilter
    complexity_score: float  # 0.0 ~ 1.0
    requires_tools: bool = False


# 의도 분류용 키워드 맵
_INTENT_KEYWORDS: dict[QueryIntent, list[str]] = {
    QueryIntent.CODE_GENERATION: [
        "만들어", "작성해", "구현해", "generate", "create", "write", "implement", "코드 짜",
    ],
    QueryIntent.CODE_EXPLANATION: [
        "설명해", "어떻게", "무엇을", "explain", "what does", "how does", "이 코드",
    ],
    QueryIntent.DEBUGGING: [
        "오류", "에러", "버그", "error", "bug", "fix", "왜 안", "수정", "debug",
    ],
    QueryIntent.COMPARISON: [
        "차이", "비교", "vs", "difference", "compare", "어떤 게 더",
    ],
    QueryIntent.DOCUMENTATION: [
        "문서", "api", "documentation", "swagger", "spec", "명세", "README",
    ],
}

# 복잡도 키워드 (높을수록 복잡)
_HIGH_COMPLEXITY_KEYWORDS = [
    "전체", "모든", "아키텍처", "설계", "최적화", "분석", "리팩터", "보안",
    "architecture", "optimize", "analyze", "refactor", "entire", "all",
]


class QueryIntelligence:
    """질문 의도 분석, 복잡도 평가, 쿼리 재작성."""

    def analyze(self, query: str, history: list[dict] | None = None) -> QueryAnalysis:
        intent = self._classify_intent(query)
        complexity = self._score_complexity(query)
        rewritten = self._rewrite(query, intent)
        filters = self._extract_filters(query)
        requires_tools = self._needs_tools(query)

        return QueryAnalysis(
            original=query,
            intent=intent,
            rewritten_queries=rewritten,
            filters=filters,
            complexity_score=complexity,
            requires_tools=requires_tools,
        )

    def _classify_intent(self, query: str) -> QueryIntent:
        q_lower = query.lower()
        scores: dict[QueryIntent, int] = {intent: 0 for intent in QueryIntent}
        for intent, keywords in _INTENT_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in q_lower:
                    scores[intent] += 1
        best = max(scores, key=lambda k: scores[k])
        if scores[best] == 0:
            return QueryIntent.FACTUAL
        return best

    def _score_complexity(self, query: str) -> float:
        q_lower = query.lower()
        score = min(len(query) / 500.0, 0.5)  # 길이 기반 0~0.5
        for kw in _HIGH_COMPLEXITY_KEYWORDS:
            if kw in q_lower:
                score += 0.1
        # 다중 질문 감지
        if query.count("?") > 1 or ("그리고" in query) or ("and" in q_lower):
            score += 0.2
        return min(score, 1.0)

    def _rewrite(self, query: str, intent: QueryIntent) -> list[str]:
        """검색 커버리지 향상을 위해 쿼리 변형 생성."""
        rewrites = [query]

        # 핵심 명사 추출 후 짧은 버전 생성
        # 간단한 구현: 조사/어미 제거
        short = re.sub(r"(을|를|이|가|은|는|에|의|로|으로|해줘|해주세요|알려줘|설명해|어떻게)\s*", " ", query)
        short = short.strip()
        if short and short != query:
            rewrites.append(short)

        # 영어 키워드 추가
        if intent == QueryIntent.CODE_GENERATION:
            rewrites.append(f"{query} example code implementation")
        elif intent == QueryIntent.DEBUGGING:
            rewrites.append(f"{query} error solution fix")

        return list(dict.fromkeys(rewrites))[:3]  # 중복 제거, 최대 3개

    def _extract_filters(self, query: str) -> MetadataFilter:
        f = MetadataFilter()
        # 파일명 패턴: xxxService.java, xxx.sql 등
        file_match = re.search(r"\b(\w+\.(java|sql|py|js|ts|go))\b", query)
        if file_match:
            f.file_name = file_match.group(1)
            ext_to_lang = {"java": "java", "sql": "sql", "py": "python", "js": "javascript", "ts": "typescript"}
            f.language = ext_to_lang.get(file_match.group(2))
        return f

    def _needs_tools(self, query: str) -> bool:
        tool_keywords = ["실행", "조회", "DB", "데이터베이스", "API 호출", "run", "execute", "query"]
        return any(kw.lower() in query.lower() for kw in tool_keywords)
