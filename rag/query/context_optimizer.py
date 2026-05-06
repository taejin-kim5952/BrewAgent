from __future__ import annotations

from .retriever import RetrievedChunk


class ContextOptimizer:
    """검색 결과를 중복 제거하고 토큰 예산에 맞게 정렬합니다."""

    def optimize(
        self,
        chunks: list[RetrievedChunk],
        query: str,
        max_tokens: int = 4096,
    ) -> list[RetrievedChunk]:
        # 1. 중복 제거 (내용이 거의 동일한 청크)
        deduped = self._deduplicate(chunks, threshold=0.9)

        # 2. 점수 내림차순 정렬
        deduped.sort(key=lambda c: c.score, reverse=True)

        # 3. 토큰 예산 제한
        selected = self._apply_token_budget(deduped, max_tokens)

        return selected

    def _deduplicate(
        self, chunks: list[RetrievedChunk], threshold: float = 0.9
    ) -> list[RetrievedChunk]:
        seen_texts: list[str] = []
        result: list[RetrievedChunk] = []
        for chunk in chunks:
            text = chunk.content.strip()
            is_dup = False
            for seen in seen_texts:
                if self._jaccard_similarity(text, seen) >= threshold:
                    is_dup = True
                    break
            if not is_dup:
                result.append(chunk)
                seen_texts.append(text)
        return result

    def _jaccard_similarity(self, a: str, b: str) -> float:
        set_a = set(a.split())
        set_b = set(b.split())
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)

    def _apply_token_budget(
        self, chunks: list[RetrievedChunk], max_tokens: int
    ) -> list[RetrievedChunk]:
        result = []
        total = 0
        for chunk in chunks:
            # 대략적인 토큰 수 (단어 수 × 1.3)
            estimated = int(len(chunk.content.split()) * 1.3)
            if total + estimated > max_tokens:
                break
            result.append(chunk)
            total += estimated
        return result
