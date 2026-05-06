# 6. Continue.dev 연결 설정

← [← README로 돌아가기](../README.md)

---

## 흐름

```
[VSCode + Continue]
       ↓ POST /v1/chat/completions (OpenAI 호환)
[RAG 서버 :8000]
       ↓ 검색 + 프롬프트 조립
[Ollama :11434]
       ↓ 추론
응답 → Continue 채팅창
```

---

## 전제

1. **RAG 서버 실행** (포트 8000)
   ```
   D:\RAGPlatform\start.bat  (배포본)
   또는
   D:\튜닝\RAGPlatform_Setup\dev_run.ps1  (개발본)
   ```
2. **Ollama 실행** + 모델 pull
   ```
   ollama serve
   ollama pull gemma3:1b
   ```
3. **VSCode + Continue 확장 설치** (마켓플레이스에서 "Continue")

---

## 방법 A — 워크스페이스 병합 (권장 시작점)

저장소 루트(`D:\튜닝`)를 VSCode로 열면 `.continuerc.json`이 인식되어 기존 Continue 설정에 **병합**됩니다.

채팅 모델 목록에서 **「RAG Platform (Ollama via RAG)」** 선택.

---

## 방법 B — 사용자 `config.yaml` 직접 추가 (최신 Continue)

`%USERPROFILE%\.continue\config.yaml`의 `models:` 아래에 추가:

```yaml
  - name: RAG + Ollama (localhost)
    provider: openai
    model: rag-local
    apiBase: http://127.0.0.1:8000/v1
    apiKey: local
    useResponsesApi: false
```

또는 `RAGPlatform_Setup\.continue\configs\rag_platform.yaml` 프로필을 Continue에서 불러오기.

### 설정 항목 설명

| 항목 | 값 | 비고 |
|---|---|---|
| `provider` | `openai` | OpenAI 호환 API라서 |
| `model` | `rag-local` | 서버에 등록된 가짜 모델 ID |
| `apiBase` | `http://127.0.0.1:8000/v1` | **반드시 `/v1` 까지** 포함 |
| `apiKey` | `local` 또는 임의 문자열 | 서버에서 검증 안 함 |
| `useResponsesApi` | `false` | OpenAI 전용 `/responses` 경로 회피 |

---

## 검증

1. Continue 채팅창에 모델 선택: **RAG + Ollama (localhost)**
2. "안녕" 질문 → 답변 도착 확인
3. RAG 서버 콘솔 로그 확인:
   ```
   POST /v1/chat/completions → 200
   ```
4. 응답 후 자동으로 인터랙션 DB에 저장됨 (웹 UI [Continue.dev 대화 내역] 탭에서 확인)

---

## 네임스페이스 관련

기본 네임스페이스는 `default`. Continue 기본 요청만으로는 본문에 `namespace`를 넣기 어려우니, 프로젝트별 RAG를 쓰려면:

- API 클라이언트(curl, Postman 등) 직접 사용
- 커스텀 Continue 확장
- 서버 측 기본값 변경 (`rag/server/routes/chat.py` 의 `ChatRequest.namespace` 기본값)

---

## 자주 발생하는 문제

| 증상 | 원인 | 해결 |
|---|---|---|
| Continue가 "Connection refused" | RAG 서버 미실행 | `start.bat` 실행 |
| "404 Not Found" | apiBase에 `/v1` 빠짐 | `http://127.0.0.1:8000/v1` 로 수정 |
| "Internal server error" | Ollama 미실행 | `ollama serve` |
| 답변 이상하게 길거나 잘림 | max_tokens 기본값 | 채팅 요청 시 `max_tokens` 조정 |
| 한글 답변에 한자 섞임 | Qwen 모델의 알려진 문제 | gemma 계열로 모델 변경 |

---

## 다음 읽을 문서

- 🚀 [실행 방법](07_실행_방법.md) — 서버 띄우기
- 🌐 [API 엔드포인트](03_API_엔드포인트.md) — `/v1/chat/completions` 상세 스펙
