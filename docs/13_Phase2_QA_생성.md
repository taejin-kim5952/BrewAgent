# 13. Phase 2 — Q&A 자동 생성

← [← README로 돌아가기](../README.md)

---

## 목적

[Phase 1](12_Phase1_가이드_규칙추출.md)에서 정리한 규칙들을 **파인튜닝용 Q&A 학습 데이터로 자동 변환**.

규칙 1개 → Q&A 5개(기본). 5개는 4종으로 분배:
- 코드 리뷰 50% (잘못된 코드 → 진단 → 모범 코드)
- 코드 생성 30% (규칙 적용한 모범 Java 코드 작성)
- 개념 설명 15% (왜? 언제? 어떻게?)
- 거절 5% (위반 요청 거절 + 대안 제시)

이 4종을 골고루 학습해야 모델이 "규칙 따르는 개발자"처럼 동작합니다.

---

## 4종 Q&A 의 학습 효과

| 유형 | 학습 효과 | 예시 instruction |
|---|---|---|
| **🔍 code_review** | 잘못된 코드를 자동 진단 | "다음 Java 코드 검토해줘: [bad code]" |
| **✍️ code_gen** | 처음부터 규칙 지키는 코드 작성 | "회사 가이드 따라 사용자 ID 조회 코드 짜줘" |
| **💡 concept** | 왜 그래야 하는지 설명 | "왜 PreparedStatement를 써야 해?" |
| **🛑 refusal** | 위반 요청 거절 + 대안 | "그냥 + 연산자로 빠르게 짜줄래?" |

---

## 처리 파이프라인

```
[Phase 1 규칙 12개] (검수 완료)
        │ 사용자가 [Q&A 생성 →] 클릭
        ▼
[옵션 모달]
   ├ 규칙당 생성 개수 (3~10)
   ├ 검수 완료된 규칙만? (체크박스)
   └ 기존 Q&A 덮어쓰기? (체크박스)
        │ [생성 시작]
        ▼
[asyncio.create_task → 백그라운드]
   for 각 규칙:
      ├ qa_generation 프롬프트 조립 (50/30/15/5 비율)
      ├ LLM 호출 (full_backend)
      ├ JSON 응답 파싱 + 정규화
      └ generated_qa 테이블에 status='pending' 저장
        │
        ▼
[5초 폴링으로 UI 자동 갱신]
        │
        ▼
[Q&A 검수 카드]
   ├ 유형/상태/규칙 필터
   ├ 개별 [✓ 승인] / [✗ 거절] / [편집] / [🗑]
   └ 일괄 [선택 승인] / [선택 거절] / [선택 삭제]
        │
        ▼
[승인된 Q&A만] → [내보내기] 시 자동 포함
```

---

## DB 테이블

[5. DB 스키마 — generated_qa](05_DB_스키마.md#generated_qa-phase-2) 참고.

---

## API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/guide/{guide_id}/generate_qa` | Q&A 자동 생성 시작 (백그라운드) |
| `GET` | `/v1/guide/{guide_id}/qa` | Q&A 목록 + 상태별 카운트 |
| `PATCH` | `/v1/guide/qa/{qa_id}` | 개별 편집 / 승인 / 거절 |
| `DELETE` | `/v1/guide/qa/{qa_id}` | 개별 삭제 |
| `POST` | `/v1/guide/qa/bulk` | 일괄 승인 / 거절 / 삭제 |
| `POST` | `/v1/guide/rules/{rule_id}/regenerate_qa` | 한 규칙만 재생성 |

### 생성 요청 예시
```json
POST /v1/guide/{guide_id}/generate_qa
{
  "count_per_rule": 5,
  "only_reviewed": true,
  "overwrite": false
}
```

### 응답 (즉시 반환, 실제 생성은 백그라운드)
```json
{
  "guide_id": "...",
  "rule_count": 12,
  "count_per_rule": 5,
  "estimated_total": 60,
  "status": "generating",
  "message": "12개 규칙 × 5개 = 약 60개 Q&A 생성 시작"
}
```

### Q&A 목록 응답
```json
{
  "guide_id": "...",
  "total": 60,
  "pending": 60,
  "approved": 0,
  "rejected": 0,
  "items": [
    {
      "qa_id": "...",
      "rule_id": "...",
      "qa_type": "code_review",
      "instruction": "다음 Java 코드 검토해줘: ...",
      "output": "❌ §2.1 위반...",
      "status": "pending",
      "rule_section_label": "§2.1",
      "rule_title": "SQL Injection 방지...",
      "rule_category": "보안"
    },
    ...
  ]
}
```

---

## LLM 프롬프트 설계

`rag/llm_router/prompts/qa_generation.py`

### 비율 분배 로직
```python
QA_DISTRIBUTION = {
    "code_review": 0.50,
    "code_gen":    0.30,
    "concept":     0.15,
    "refusal":     0.05,
}

def compute_per_type_counts(total: int) -> dict[str, int]:
    counts = {t: max(1, round(total * r)) for t, r in QA_DISTRIBUTION.items()}
    diff = total - sum(counts.values())
    counts["code_review"] = max(1, counts["code_review"] + diff)
    return counts
```

5개 → `{code_review: 3, code_gen: 1, concept: 1, refusal: 0(→1)}`
10개 → `{code_review: 5, code_gen: 3, concept: 2, refusal: 1}`

### 시스템 프롬프트
```
당신은 사내 개발 가이드를 파인튜닝 학습 데이터로 변환하는 전문가입니다.
주어진 규칙을 바탕으로 다양한 형태의 Q&A 쌍을 생성하여 JSON 배열로만 출력합니다.
다른 설명 텍스트는 절대 포함하지 마세요.
```

### 사용자 프롬프트 (요약)
```
[규칙 정보]
출처: §2.1
심각도: MUST
카테고리: 보안
제목: SQL Injection 방지
본문: ...
[가이드의 잘못된 예]
String sql = "SELECT ..." + id;
[가이드의 모범 예]
ps.setString(1, id);

[생성 비율]
- code_review: 3개
- code_gen: 1개
- concept: 1개
- refusal: 0개

[작성 규칙]
1. instruction: 자연스러운 한국어 질문
2. output 형식: 진단(✅/❌) → 근거(§출처) → 모범 코드 → 설명
3. 코드는 컴파일 가능한 Java
4. 5개의 instruction 표현이 모두 다르도록
5. code_review의 잘못된 코드는 다양한 패턴 (흔한 실수, 미묘한 위반, 부분 위반)
6. concept 답변에 "왜 중요한가" + "지키지 않으면 무슨 문제가 생기는가" 포함
7. refusal은 단호하지만 정중하게 거절 + 올바른 방향 제시

[출력 — JSON 배열만]
[{"qa_type": "code_review", "instruction": "...", "output": "..."}, ...]
```

---

## UI 구조

[Phase 1 화면 아래쪽]에 자동으로 펼쳐짐.

### Q&A 생성 옵션 모달
```
┌─ Q&A 자동 생성 ──────────────────────────┐
│ 생성 비율: 코드 리뷰 50% / 코드 생성 30%  │
│           / 개념 설명 15% / 거절 5%       │
│                                            │
│ 규칙당 생성 개수: [5개 (권장) ▼]          │
│ ☐ 검수 완료된 규칙만 사용                 │
│ ☐ 기존 Q&A 모두 삭제 후 재생성           │
│                                            │
│ 대상 규칙: 12개 → 예상 Q&A 60개           │
│ 예상 소요: 약 6~18분                      │
│                                            │
│        [취소]  [생성 시작]                 │
└──────────────────────────────────────────┘
```

### Q&A 검수 카드
```
[생성된 Q&A (60개)]                대기 60 · 승인 0 · 거절 0
  유형▼  상태▼  규칙▼   [새로고침]

  [선택 승인] [선택 거절] [선택 삭제]   선택된 항목: 0

  ☐ 🔍 코드 리뷰  pending  §2.1
    Q: 다음 Java 코드 검토해줘: ...
    ▶ 답변 보기 (385자)
                              [✓ 승인][✗ 거절][편집][🗑]

  ☐ ✍️ 코드 생성  pending  §2.1
    Q: 사용자 ID로 DB 조회 코드 작성해줘.
    ▶ 답변 보기 (411자)
                              [✓ 승인][✗ 거절][편집][🗑]
  ...
```

상태별 색상:
- pending: 회색 배경
- approved: 녹색 배경
- rejected: 빨간 배경

### 자동 폴링
5초마다 pending Q&A 개수 변화 체크 → 변화 있으면 목록 새로고침. 5회 연속 변화 없으면 정지.

---

## 검수 효율 전략

### 1. 모든 규칙 다 다루지 마세요
가이드 200개 규칙 중 핵심 30~50개만 [검수 완료] → `only_reviewed=true` 로 생성.

### 2. 개수를 줄이세요
규칙당 5개 → 3개로 변경 시 검수 시간 60% 절약.

### 3. 샘플링 검수
처음 10세트(50개)만 꼼꼼히 → 품질 일관되면 나머지 [선택 승인] 일괄.

### 4. 점진적 학습
1차: 50개 규칙 → 200개 Q&A → Colab 학습 → 결과 확인 → 2차 추가.

### 5. 30초 룰
각 Q&A를 30초 안에 결정:
- 질문 한 줄 (5초)
- 답변 첫 3줄 (10초)
- 코드 예시 훑기 (10초)
- 결정 (5초)

---

## 권장 작업량

| 목표 | 규칙 수 | Q&A 개수 | 검수 시간 | 효과 |
|---|---|---|---|---|
| **PoC** | 30 | 90~150 | 1~2시간 | 톤·스타일 학습 |
| **추천** | 80 | 300~400 | 4~6시간 | 회사 패턴 명확 |
| **이상** | 200 | 800~1000 | 10~15시간 | 거의 전문가 |

> 80~100개 규칙으로도 충분히 좋은 효과. 5,000개는 과도.

---

## 내보내기 (JSONL)

`POST /v1/dataset/export` 가 자동으로 통합:
- Continue.dev 인터랙션
- 수동 입력
- **승인된 가이드 Q&A** ← Phase 2 결과

```json
{
  "format": "alpaca",
  "include_interactions": true,
  "include_manual": true,
  "include_guide_qa": true,
  "guide_id": null   // null이면 모든 가이드의 승인된 Q&A
}
```

응답:
```json
{
  "filename": "finetune_alpaca_20260506_223510.jsonl",
  "record_count": 327,
  "sources": {"interactions": 87, "manual": 15, "guide_qa": 225},
  "download_url": "/v1/dataset/exports/..."
}
```

---

## 문제 해결

### Q&A 0개 생성됨
원인 후보:
1. 서버가 옛 모델 들고 있음 → 재시작
2. LLM 호출 timeout → `local.yaml`의 `timeout_seconds` 확인
3. JSON 파싱 실패 → 다른 모델 사용 (json 출력 잘하는 모델)

확인:
```bash
# 서버 콘솔에서 다음 로그 확인
[qa-gen xxx] 시작: ... 모델=...
[qa-gen xxx] 규칙 1/N 처리 중 ...
[qa-gen xxx] 규칙 1/N 완료: x/y Q&A 저장
```

### 답변 품질 낮음
- gemma3:1b 같은 작은 모델은 한국어/코드 일관성 떨어질 수 있음
- 더 큰 모델 (qwen3.5:4b, kitad-v20260408_1124, exaone-deep:7.8b)로 재생성

### JSON 파싱 자주 실패
LLM이 JSON 형식을 잘 못 따르면:
1. 더 큰/똑똑한 모델 사용
2. `qa_generation.py` 의 시스템 프롬프트 강화
3. temperature 낮추기 (현재 0.5 → 0.3)

---

## Phase 2 이후 (Phase 3 후보)

- LLM-as-Judge 자동 1차 검증 (다른 LLM이 채점)
- 코드 자동 컴파일 검증 (javac)
- 중복 instruction 자동 탐지
- 카테고리별 다양성 점수
- 카테고리별 통계 시각화

---

## 다음 읽을 문서

- 🎓 [Phase 1: 가이드 규칙 추출](12_Phase1_가이드_규칙추출.md) — 입력 데이터
- 🌐 [API 엔드포인트 — Phase 2](03_API_엔드포인트.md#qa-phase-2-학습-데이터-생성)
- 💾 [DB 스키마 — generated_qa](05_DB_스키마.md#generated_qa-phase-2)
