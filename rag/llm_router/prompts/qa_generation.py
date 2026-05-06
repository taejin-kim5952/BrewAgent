"""규칙 → 파인튜닝용 Q&A 자동 생성 프롬프트 템플릿."""
from __future__ import annotations

import json
import re

QA_GENERATION_SYSTEM = (
    "당신은 사내 개발 가이드를 파인튜닝 학습 데이터로 변환하는 전문가입니다. "
    "주어진 규칙을 바탕으로 다양한 형태의 Q&A 쌍을 생성하여 JSON 배열로만 출력합니다. "
    "다른 설명 텍스트는 절대 포함하지 마세요."
)


# qa_type별 생성 비율 (코드 리뷰 1순위, 코드 생성 2순위, 개념 3순위, 거절 마지막)
QA_DISTRIBUTION = {
    "code_review": 0.50,   # 잘못된 코드 합성 → 진단 → 개선
    "code_gen": 0.30,      # 규칙 적용한 모범 코드 작성
    "concept": 0.15,       # 왜? 어떻게? 언제?
    "refusal": 0.05,       # 위반 사례 거절 + 근거
}


def compute_per_type_counts(total: int) -> dict[str, int]:
    """총 개수를 qa_type별로 분배. 합이 total이 되도록 보정."""
    counts = {t: max(1, round(total * r)) for t, r in QA_DISTRIBUTION.items()}
    diff = total - sum(counts.values())
    # 차이는 code_review 에서 가감
    counts["code_review"] = max(1, counts["code_review"] + diff)
    return counts


def build_user_prompt(rule: dict, count: int = 5) -> str:
    """규칙 1개 → Q&A 여러 개 생성 프롬프트."""
    counts = compute_per_type_counts(count)

    section = rule.get("section_label", "")
    severity_label = {
        "must": "MUST (필수)", "should": "SHOULD (권장)",
        "may": "MAY (선택)", "unknown": "참고",
    }.get(rule.get("severity", "unknown"), "참고")

    code_bad = rule.get("code_bad", "")
    code_good = rule.get("code_good", "")
    code_section = ""
    if code_bad:
        code_section += f"\n[가이드의 잘못된 예]\n```\n{code_bad}\n```\n"
    if code_good:
        code_section += f"\n[가이드의 모범 예]\n```\n{code_good}\n```\n"

    return f"""다음 사내 개발 규칙을 바탕으로 파인튜닝용 Q&A 쌍 {count}개를 생성하세요.
응답하는 AI(파인튜닝 대상)가 학습할 데이터입니다.

[규칙 정보]
출처: {section}
심각도: {severity_label}
카테고리: {rule.get("category", "기타")}
제목: {rule.get("title", "")}

[규칙 본문]
{rule.get("body", "")}
{code_section}

[생성 비율]
- code_review : {counts["code_review"]}개  (잘못된 Java 코드를 합성 → 위반 진단 → 모범 코드 제시)
- code_gen    : {counts["code_gen"]}개  (규칙을 적용한 모범 Java 코드 작성)
- concept     : {counts["concept"]}개  (왜/언제/어떻게 같은 개념 질문)
- refusal     : {counts["refusal"]}개  (규칙 위반 요청을 받았을 때 거절 + 대안 제시)

[작성 규칙]
1. instruction(질문): 실제 개발자가 물어볼 만한 자연스러운 한국어 문장.
2. output(답변): 다음 형식을 일관되게 따를 것
   - 진단(✅/❌) → 근거({section} 또는 카테고리) → 모범 코드(```java ... ```) → 간단 설명
3. 코드는 반드시 컴파일 가능한 Java로 작성.
4. 같은 규칙이라도 instruction은 5개가 모두 표현이 다르도록 작성.
5. code_review의 잘못된 코드는 다양한 패턴으로 합성:
   - 가장 흔한 실수
   - 미묘한 위반 (회피한 척)
   - 부분적 위반
6. concept 답변에는 "왜 중요한가" + "지키지 않으면 무슨 문제가 생기는가" 포함.
7. refusal은 단호하지만 정중하게 거절하고 올바른 방향 제시.

[출력 형식 — JSON 배열만, 다른 텍스트 절대 금지]
[
  {{
    "qa_type": "code_review",
    "instruction": "다음 Java 코드 검토해줘:\\n```java\\n...\\n```",
    "output": "❌ {section} 위반: ...\\n\\n근거: ...\\n\\n```java\\n// 모범 코드\\n```\\n\\n설명: ..."
  }},
  ...
]

총 {count}개 Q&A를 위 비율대로 출력하세요.

[Q&A JSON 배열]
"""


_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def parse_qa_response(response_text: str) -> list[dict]:
    """LLM 응답에서 JSON 배열을 추출하여 list[dict]로 반환."""
    if not response_text:
        return []
    text = response_text.strip()

    # 1) 그대로 파싱
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass

    # 2) 코드 펜스 제거
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            data = json.loads(fence.group(1).strip())
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    # 3) 첫 [부터 마지막 ]까지
    match = _JSON_ARRAY_RE.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    return []


_VALID_QA_TYPES = {"code_review", "code_gen", "concept", "refusal"}


def normalize_qa_type(value) -> str:
    if not value or not isinstance(value, str):
        return "code_review"
    v = value.strip().lower().replace("-", "_")
    return v if v in _VALID_QA_TYPES else "code_review"
