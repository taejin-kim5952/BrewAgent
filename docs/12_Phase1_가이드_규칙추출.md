# 12. Phase 1 — 가이드 규칙 추출

← [← README로 돌아가기](../README.md)

---

## 목적

회사 보안/품질/네이밍 가이드 PDF/Word 문서를 업로드하면 AI가 **개별 규칙 단위로 자동 분할**하고, 사용자가 **검수/편집/병합/분할** 할 수 있게 한다.

이렇게 정리된 규칙이 Phase 2의 Q&A 생성 입력으로 사용된다.

---

## 처리 파이프라인

```
[가이드 PDF/Word 업로드]
        │
        ▼
[1. Dispatcher.parse()] — 파일 확장자별 파서로 텍스트 추출
        │
        ▼
[2. 청크 그룹핑] — LLM 컨텍스트(약 4000자) 단위로 묶음
        │
        ▼
[3. LLM 호출] — 각 그룹에서 규칙 JSON 추출
   ├ rule_extraction 프롬프트 사용
   ├ JSON 파싱 실패 시 1회 재시도
   └ 정규화: 카테고리/심각도 표준화
        │
        ▼
[4. rules 테이블 저장] — guide_id, section_label, title, body, ...
        │
        ▼
[5. 사용자 검수 UI]
   ├ 편집 (제목/본문/카테고리/심각도/코드 예시)
   ├ 분할 (1개 → N개)
   ├ 병합 (N개 → 1개)
   ├ 삭제 (소프트)
   └ 수동 추가
        │
        ▼
[6. 구조 확정]
   └ Phase 2(Q&A 생성)으로 이어짐
```

---

## DB 테이블

[5. DB 스키마 — guides](05_DB_스키마.md#guides-phase-1) / [rules](05_DB_스키마.md#rules-phase-1) 참고.

---

## API 엔드포인트

### 가이드 관리
- `POST /v1/guide/upload` — 파일 업로드 + 백그라운드 추출 시작
- `GET /v1/guide/list` — 모든 가이드 목록 + 진행 상태
- `GET /v1/guide/{guide_id}` — 가이드 상세
- `DELETE /v1/guide/{guide_id}` — 가이드 + 모든 규칙 삭제

### 규칙 관리
- `GET /v1/guide/{guide_id}/rules` — 규칙 목록 (filter: category, severity)
- `POST /v1/guide/{guide_id}/rules` — 수동 규칙 추가
- `PATCH /v1/guide/rules/{rule_id}` — 규칙 편집
- `DELETE /v1/guide/rules/{rule_id}` — 규칙 소프트 삭제
- `POST /v1/guide/rules/{rule_id}/split` — 규칙 분할
- `POST /v1/guide/rules/merge` — 규칙 병합

### 마무리
- `POST /v1/guide/{guide_id}/finalize` — 검수 완료 표시

---

## LLM 프롬프트 설계

`rag/llm_router/prompts/rule_extraction.py`

### 시스템 프롬프트
```
당신은 사내 개발 가이드 문서를 분석하여 규칙을 구조화하는 전문가입니다.
주어진 문서 일부에서 개발자가 따라야 할 규칙(rule)들을 식별하고 JSON 형식으로 출력합니다.
반드시 JSON 배열만 출력하고, 그 외의 설명 텍스트는 절대 포함하지 마세요.
```

### 사용자 프롬프트 (요약)
```
[추출 규칙]
1. 절번호(§3.2.1 등)가 명시되어 있으면 그대로 section_label에 사용. 없으면 빈 문자열.
2. 각 규칙은 독립적으로 적용 가능한 단위.
3. severity 분류:
   - "must": MUST/필수/반드시/금지/하지 말 것
   - "should": SHOULD/권장/해야 한다
   - "may": MAY/선택/가능하면
   - "unknown": 판단 어려우면
4. category: 보안/품질/네이밍/테스트/로깅/트랜잭션/API/성능/예외처리/기타
5. 코드 예제 있으면 code_bad, code_good에 발췌
6. 단순 설명/목차/일반론은 제외 (반드시 따라야 할 행동지침만)

[출력 — JSON 배열만]
[
  {
    "section_label": "§3.2.1",
    "title": "...",
    "body": "...",
    "category": "보안",
    "severity": "must",
    "code_bad": "...",
    "code_good": "..."
  }
]
```

### JSON 파싱 폴백
LLM이 마크다운 코드 펜스를 섞어내면 정규식으로 추출:
1. `json.loads(text)` 직접 시도
2. ```` ```json ... ``` ```` 펜스 안 추출
3. 첫 `[` 부터 마지막 `]` 까지 추출

3단계 모두 실패 시 빈 리스트 반환 → 다음 그룹으로 진행.

---

## 백그라운드 처리

`rag/server/routes/guide.py: _extract_rules_background()`

```python
asyncio.create_task(
    _extract_rules_background(container, guide_id, persist_path, persist_dir)
)
```

진행 단계:
1. **파싱 시작** (status='parsing', progress=0)
2. `Dispatcher.parse()` 호출 → 청크 추출
3. 페이지 수 추정 후 (status='extracting', progress=5)
4. 청크들을 6개씩 그룹화 (약 4000자 이내)
5. 그룹별 LLM 호출 + 규칙 저장
6. progress 갱신 (5% → 95%)
7. **완료** (status='done', progress=100)

실패 시: status='failed' + error_msg 저장.

### 진행 로그 예시
```
[guide 53b73aa4] 파싱 시작: AI_Dev_Agent_Rules_v1.0.docx
[guide 53b73aa4] 파싱 완료: 12 청크, 4 페이지 (0.3s)
[guide 53b73aa4] 추출 시작: 3 그룹, 모델=gemma3:1b
[guide 53b73aa4] 그룹 1/3 처리 중 (페이지 1-2, 3850자)
[guide 53b73aa4] 그룹 1/3 완료: 5/5 규칙 저장 (8.2s)
[guide 53b73aa4] 그룹 2/3 처리 중 ...
[guide 53b73aa4] ✓ 추출 완료: 11 규칙, 3 그룹, 24.5s
```

---

## UI 구조 (`가이드 → 훈련 데이터` 탭)

### 영역 A: 가이드 업로드 + 목록
```
[가이드 업로드]
   파일 선택 (.pdf/.docx/.doc) | 별칭 입력 | [업로드]

[업로드된 가이드 (N)]
  • rule1 [완료]   AI_Dev_Agent_Rules_v1.0.docx · 30페이지 · 규칙 12개   [열기] [🗑]
  • rule2 [extracting 67%] (자동 갱신)
  • rule3 [실패] ⚠ python-docx 미설치
```
- 3초마다 자동 폴링 (extracting 상태인 가이드만)

### 영역 B: 규칙 검수 (선택된 가이드)
[열기] 클릭 시 펼침:
```
[rule1 — 12개 규칙]
  카테고리▼  심각도▼  검수상태▼

  ☐ §2.1 SQL Injection 방지 [must][보안]
    동적 SQL 쿼리를 생성할 때 사용자 입력값을 직접 문자열 연결하여...
    📄 페이지 12-13
    ▶ 코드 예시 보기
        ❌ String sql = "SELECT * FROM users WHERE id = '" + id + "'";
        ✅ PreparedStatement ps = ...
    [편집] [✗ 검수해제] [🗑]

  ☐ AUTO-001 변수 명명 규칙 [should][품질]
    ...

  [+ 규칙 추가] [선택 병합] [구조 확정] [Q&A 생성 →]
```

### 편집 모달
- 절번호 / 제목 / 본문 / 카테고리 / 심각도 / 잘못된 코드 / 모범 코드 모두 인라인 편집

---

## 사용 흐름

```
1. [가이드 → 훈련 데이터] 탭 클릭
2. PDF/Word 파일 + 별칭 입력 → [업로드]
3. parsing → extracting → done 진행 자동 갱신
4. [열기] 클릭 → 추출된 규칙 검수
5. 잘못된 규칙: [편집] / [🗑] / [분할] / [병합]
6. 검수 완료된 규칙: [✓ 검수완료] 마킹
7. 누락된 규칙: [+ 규칙 추가] 로 수동 추가
8. 모두 끝나면 [구조 확정] 클릭 → Phase 2로 진행
```

---

## 문제 해결

### 가이드가 [파싱 실패] 로 끝남
원인 후보:
- python-docx / python-pptx 미설치 → `pip install python-docx python-pptx`
- 손상된 PDF → 다른 도구로 재저장
- 암호 걸린 파일 → 풀어서 업로드

### Progress가 5%에서 멈춤
원인: LLM 호출이 진행 중이지만 매우 느림 (CPU 폴백 등).
확인: 서버 콘솔에 그룹별 로그가 찍히는지, `curl http://localhost:11434/api/ps` 로 활성 모델 + VRAM 사용량 체크.

### 추출된 규칙이 너무 적음
원인: gemma3:1b 같은 작은 모델은 규칙 누락 가능.
해결:
1. 더 큰 모델로 변경 (qwen3.5:4b, kitad-v20260408_1124 등)
2. 가이드 삭제 후 재업로드
3. 또는 [+ 규칙 추가] 로 수동 보완

### 추출된 규칙이 너무 많거나 중복
[병합] 으로 비슷한 규칙들을 합치거나 [🗑] 로 불필요한 것 삭제.

---

## 다음 단계

규칙 검수가 끝나면 **[Q&A 생성 →]** 버튼으로 [Phase 2](13_Phase2_QA_생성.md) 진행.

---

## 다음 읽을 문서

- 🤖 [Phase 2: Q&A 자동 생성](13_Phase2_QA_생성.md) — 규칙 → 학습 데이터
- 💾 [DB 스키마 — guides/rules](05_DB_스키마.md)
- 🌐 [API 엔드포인트 — Phase 1](03_API_엔드포인트.md#가이드-phase-1-규칙-추출)
