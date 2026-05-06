# 3. API 엔드포인트 전체 목록

← [← README로 돌아가기](../README.md)

---

## 시스템

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/` | → `/ui/index.html` 리다이렉트 |
| `GET` | `/health` | 서버 상태 (Ollama 연결 확인 포함) |
| `GET` | `/v1/models` | 사용 가능 모델 목록 |
| `GET` | `/ui/index.html` | 훈련 데이터 관리 웹 UI |
| `GET` | `/docs` | Swagger UI (자동 생성된 API 문서) |

## 채팅 (Continue.dev 연동)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/chat/completions` | OpenAI 호환 RAG 채팅 (스트리밍 지원) |

## 인제스트 (파일 인덱싱 / 요약)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/ingest/file` | 파일 업로드 + 인덱싱 (압축 자동 처리) |
| `POST` | `/v1/ingest/batch` | 서버 측 디렉토리 일괄 인덱싱 |
| `POST` | `/v1/ingest/summarize` | 문서 자동 요약 (Ollama, ZIP 지원) |

## 컬렉션 (네임스페이스)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/v1/collections` | 네임스페이스 목록 |
| `POST` | `/v1/collections/{namespace}` | 네임스페이스 생성 |
| `DELETE` | `/v1/collections/{namespace}` | 네임스페이스 삭제 |

## 데이터셋 (인터랙션 + 수동 입력 + 내보내기)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `GET` | `/v1/dataset/interactions` | Q&A 기록 조회 (filter: namespace, min_rating, min_eval_score) |
| `PATCH` | `/v1/dataset/interactions/{id}/rating` | 사용자 평점 저장 (1~5) |
| `POST` | `/v1/dataset/manual` | 수동 Q&A 추가 |
| `GET` | `/v1/dataset/manual` | 수동 입력 목록 |
| `DELETE` | `/v1/dataset/manual/{entry_id}` | 수동 입력 삭제 |
| `POST` | `/v1/dataset/export` | JSONL 내보내기 (인터랙션 + 수동 + 가이드 Q&A 통합) |
| `GET` | `/v1/dataset/exports/{filename}` | 내보낸 파일 다운로드 |

## 평가

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/eval/run` | 특정 인터랙션 품질 평가 재실행 |

## 가이드 (Phase 1: 규칙 추출)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/guide/upload` | 가이드 업로드 → 백그라운드 규칙 추출 시작 |
| `GET` | `/v1/guide/list` | 업로드된 가이드 목록 + 진행 상태 |
| `GET` | `/v1/guide/{guide_id}` | 가이드 상세 |
| `DELETE` | `/v1/guide/{guide_id}` | 가이드 + 모든 규칙 삭제 |
| `GET` | `/v1/guide/{guide_id}/rules` | 추출된 규칙 목록 (filter: category, severity) |
| `POST` | `/v1/guide/{guide_id}/rules` | 수동 규칙 추가 |
| `PATCH` | `/v1/guide/rules/{rule_id}` | 규칙 편집 |
| `DELETE` | `/v1/guide/rules/{rule_id}` | 규칙 소프트 삭제 |
| `POST` | `/v1/guide/rules/{rule_id}/split` | 규칙 분할 (1개 → N개) |
| `POST` | `/v1/guide/rules/merge` | 규칙 병합 (N개 → 1개) |
| `POST` | `/v1/guide/{guide_id}/finalize` | 검수 완료 표시 |

## Q&A (Phase 2: 학습 데이터 생성)

| 메서드 | 경로 | 설명 |
|---|---|---|
| `POST` | `/v1/guide/{guide_id}/generate_qa` | 가이드 규칙 → Q&A 자동 생성 (백그라운드) |
| `GET` | `/v1/guide/{guide_id}/qa` | Q&A 목록 (filter: status, qa_type, rule_id) |
| `PATCH` | `/v1/guide/qa/{qa_id}` | Q&A 편집 / 승인 / 거절 |
| `DELETE` | `/v1/guide/qa/{qa_id}` | Q&A 삭제 |
| `POST` | `/v1/guide/qa/bulk` | 일괄 승인 / 거절 / 삭제 |
| `POST` | `/v1/guide/rules/{rule_id}/regenerate_qa` | 특정 규칙만 Q&A 재생성 |

---

## 요청 예시

### 채팅 (Continue.dev 호환)
```json
POST /v1/chat/completions
{
  "model": "rag-local",
  "messages": [
    {"role": "user", "content": "UserService.java 설명해줘"}
  ],
  "stream": false,
  "namespace": "my-project",
  "enable_rag": true,
  "top_k_chunks": 10
}
```

### 가이드 업로드
```bash
curl -X POST http://localhost:8000/v1/guide/upload \
  -F "name=우리회사 보안 가이드 v3" \
  -F "file=@security_guide.pdf"
```

### Q&A 생성 시작
```json
POST /v1/guide/{guide_id}/generate_qa
{
  "count_per_rule": 5,
  "only_reviewed": true,
  "overwrite": false
}
```

### 내보내기 (모든 소스 통합)
```json
POST /v1/dataset/export
{
  "format": "alpaca",
  "include_interactions": true,
  "include_manual": true,
  "include_guide_qa": true,
  "guide_id": null
}
```

응답:
```json
{
  "filename": "finetune_alpaca_20260506_223510.jsonl",
  "record_count": 327,
  "format": "alpaca",
  "sources": {
    "interactions": 87,
    "manual": 15,
    "guide_qa": 225
  },
  "download_url": "/v1/dataset/exports/finetune_alpaca_20260506_223510.jsonl"
}
```

---

## Swagger UI 활용

서버 실행 후 `http://localhost:8000/docs` 접속하면 모든 엔드포인트를 브라우저에서 직접 호출/테스트할 수 있습니다.

---

## 다음 읽을 문서

- 🔧 [핵심 모듈](04_핵심_모듈.md) — 엔드포인트 내부 동작
- 🎓 [Phase 1: 가이드 규칙 추출](12_Phase1_가이드_규칙추출.md)
- 🤖 [Phase 2: Q&A 자동 생성](13_Phase2_QA_생성.md)
