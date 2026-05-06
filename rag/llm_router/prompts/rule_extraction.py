"""사내 가이드 문서에서 규칙(rule)을 추출하는 LLM 프롬프트 템플릿."""
from __future__ import annotations

import json
import re

RULE_EXTRACTION_SYSTEM = (
    "당신은 사내 개발 가이드 문서를 분석하여 규칙을 구조화하는 전문가입니다. "
    "주어진 문서 일부에서 개발자가 따라야 할 규칙(rule)들을 식별하고 JSON 형식으로 출력합니다. "
    "반드시 JSON 배열만 출력하고, 그 외의 설명 텍스트는 절대 포함하지 마세요."
)


def build_user_prompt(chunk_group_text: str, page_range: str = "") -> str:
    """청크 그룹 텍스트를 받아 규칙 추출 사용자 프롬프트를 생성합니다."""
    page_hint = f"\n[참고: 이 텍스트는 페이지 {page_range} 에서 추출됨]\n" if page_range else ""
    return f"""다음 가이드 문서 일부를 읽고, 개발자가 따라야 할 규칙들을 추출하세요.{page_hint}

[추출 규칙]
1. 절번호(예: §3.2.1, 3.2.1, 1.1, 가-나-다)가 명시되어 있으면 그대로 section_label에 사용. 없으면 빈 문자열로.
2. 각 규칙은 독립적으로 적용 가능한 단위여야 함. 너무 큰 규칙은 분할.
3. severity 분류:
   - "must": MUST/필수/반드시/금지/하지 말 것
   - "should": SHOULD/권장/해야 한다/지향
   - "may": MAY/선택/가능하면/할 수 있다
   - "unknown": 판단이 어려우면
4. category 분류 (다음 중 하나만 사용):
   - "보안" / "품질" / "네이밍" / "테스트" / "로깅" / "트랜잭션" / "API" / "성능" / "예외처리" / "기타"
5. 코드 예제가 있으면 code_bad (잘못된 예), code_good (모범 예)에 발췌.
6. 단순 설명, 목차, 챕터 제목, 일반론은 추출하지 말 것 (반드시 따라야 할 행동지침만).
7. title 은 한 줄(50자 이내) 요약, body 는 2~5문장 본문.

[출력 형식 — JSON 배열만 출력하고 다른 텍스트는 출력하지 마세요]
[
  {{
    "section_label": "§3.2.1",
    "title": "SQL 인젝션 방지를 위한 PreparedStatement 사용",
    "body": "사용자 입력을 포함한 동적 쿼리는 반드시 PreparedStatement 또는 ORM 의 파라미터 바인딩을 사용해야 한다. 문자열 연결(+) 사용을 금지한다.",
    "category": "보안",
    "severity": "must",
    "code_bad": "String sql = \\"SELECT * FROM users WHERE id = '\\" + id + \\"'\\";",
    "code_good": "PreparedStatement ps = conn.prepareStatement(\\"SELECT * FROM users WHERE id = ?\\");\\nps.setString(1, id);"
  }}
]

규칙이 없으면 빈 배열 [] 만 출력하세요.

[가이드 문서 일부]
{chunk_group_text}

[추출 결과 JSON 배열]
"""


_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")


def parse_llm_response(response_text: str) -> list[dict]:
    """LLM 응답에서 JSON 배열을 추출하여 list[dict]로 반환합니다.

    실패 시 빈 리스트 반환 (호출 측에서 errors에 누적).
    """
    if not response_text:
        return []

    # 1) 그대로 파싱 시도
    text = response_text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return [d for d in data if isinstance(d, dict)]
    except json.JSONDecodeError:
        pass

    # 2) 마크다운 코드블록 제거 후 시도
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        try:
            data = json.loads(fence.group(1).strip())
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    # 3) 첫 [부터 마지막 ]까지 추출하여 시도
    match = _JSON_ARRAY_RE.search(text)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, list):
                return [d for d in data if isinstance(d, dict)]
        except json.JSONDecodeError:
            pass

    return []
