# BrewAgent — Java 개발 특화 AI 에이전트

> **로컬 환경에서 동작하는 Java 개발 보조 + 파인튜닝 데이터 수집 플랫폼**

VSCode + Continue.dev 와 연동되어 Java 코드 작성/리팩토링/디버깅을 도우면서,
대화 내역을 자동으로 수집해 **나만의 Java 특화 모델**을 파인튜닝할 수 있는 데이터셋을 만듭니다.

![Version](https://img.shields.io/badge/version-0.1-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📌 핵심 기능

| 기능 | 설명 |
|---|---|
| **RAG 채팅** | 업로드된 문서(PDF/Word/Excel/PPT/이미지/코드)를 참고해 Ollama 로컬 모델로 답변 |
| **멀티모달 인제스트** | PDF·Word·PPT·Excel·이미지(OCR)·코드(Java/SQL/Python 등)·텍스트 인덱싱 |
| **압축 파일 지원** | ZIP/TAR 업로드 시 내부 모든 파일을 자동 추출·인덱싱 (보안 문서 보호용) |
| **하이브리드 검색** | FAISS 벡터 검색 + SQLite FTS5 BM25를 RRF로 결합 |
| **LLM 자동 라우팅** | 질문 복잡도에 따라 빠른 모델 ↔ 정확한 모델 자동 선택 |
| **훈련 데이터 수집** | 모든 Q&A 자동 기록 → 품질 평가 → JSONL 내보내기 (OpenAI/Alpaca/ShareGPT) |
| **문서 요약** | 업로드된 문서를 Ollama 모델로 자동 요약 (긴 문서는 map-reduce) |
| **웹 UI** | 대화 내역 조회·평점·내보내기 + 수동 Q&A 입력 + 문서 요약 |
| **Continue.dev 연동** | OpenAI 호환 API로 VSCode Continue.dev와 바로 연결 |

---

## 🏗️ 아키텍처

```
[VSCode + Continue.dev]
        │  POST /v1/chat/completions
        ▼
[BrewAgent Server :8000]
   ├─ QueryIntelligence   (의도 분석 + 쿼리 재작성)
   ├─ HybridRetriever     (FAISS + FTS5)
   ├─ ContextOptimizer    (중복 제거 + 토큰 예산)
   ├─ PromptBuilder       (의도별 시스템 프롬프트)
   ├─ LLMRouter ──→ OllamaBackend (gemma4 / qwen2.5-coder 등)
   └─ EvaluationEngine + InteractionLogger (백그라운드)
        │
        ▼
[Ollama :11434]  ←── 로컬 LLM 서빙
```

---

## 🚀 빠른 시작

### 1. 사전 설치

| 항목 | 다운로드 |
|---|---|
| Python 3.10+ | https://www.python.org/downloads/ (PATH 추가 체크) |
| Ollama | https://ollama.com/download |

### 2. 설치 (Windows)

```bash
# 1) 이 저장소 다운로드 후 setup.bat 더블클릭
setup.bat

# 2) Ollama 모델 받기 (예시)
ollama pull gemma4:e4b
ollama pull gemma4:e2b
```

### 3. 실행

```bash
# 설치 폴더의 start.bat 더블클릭 (기본: C:\RAGPlatform\start.bat)
# 또는 바탕화면의 'RAG Platform.bat' 실행
```

브라우저에서 접속:
- **웹 UI**: http://localhost:8000/
- **API 문서**: http://localhost:8000/docs
- **상태 확인**: http://localhost:8000/health

### 4. Continue.dev 연결

`~/.continue/config.json` 에 추가:

```json
{
  "models": [
    {
      "title": "BrewAgent",
      "provider": "openai",
      "model": "rag-local",
      "apiBase": "http://localhost:8000",
      "apiKey": "local"
    }
  ]
}
```

---

## 📂 프로젝트 구조

```
RAGPlatform_Setup/
├── setup.bat                ← 원클릭 인스톨러 (Windows)
├── install.py
├── requirements.txt
├── rag/                     ← 메인 패키지
│   ├── configs/             ← 설정 (default.yaml, settings.py)
│   ├── server/              ← FastAPI 서버 + 웹 UI
│   │   ├── main.py
│   │   ├── dependencies.py
│   │   ├── static/index.html
│   │   └── routes/          ← chat, ingest, collections, dataset, eval
│   ├── ingest/              ← 파일 파싱 + 청킹 + 임베딩
│   │   └── parsers/         ← pdf, docx, pptx, excel, image, code, text
│   ├── vector_db/           ← FAISS + SQLite FTS5
│   ├── query/               ← 의도 분석 + 하이브리드 검색
│   ├── llm_router/          ← 복잡도 기반 모델 라우팅
│   ├── evaluation/          ← 답변 품질 평가
│   ├── memory/              ← 캐시 + 지식 저장소
│   ├── dataset/             ← 인터랙션 로깅 + JSONL 내보내기
│   └── tools/               ← 도구 호출 (DB 쿼리, 코드 실행)
└── assets/                  ← 아이콘 등
```

---

## 🎯 권장 모델 (PC 사양별)

| GPU/RAM | 추천 모델 | 비고 |
|---|---|---|
| RTX 3050+ (4GB VRAM) | `gemma4:e4b` (메인) + `gemma4:e2b` (보조) | 한국어 품질 우수 |
| RTX 3060+ (8GB VRAM) | `qwen2.5-coder:7b` | 코드 작업 최강, 한자 혼용 주의 |
| GPU 없음 (RAM 16GB) | `gemma4:e2b` 또는 `qwen2.5-coder:3b` | CPU 추론 |

`rag/configs/default.yaml` 에서 모델 변경:

```yaml
ollama:
  model_fast: "gemma4:e2b"
  model_full: "gemma4:e4b"
```

---

## 📊 API 엔드포인트

| 메서드 | 경로 | 설명 |
|---|---|---|
| POST | `/v1/chat/completions` | OpenAI 호환 RAG 채팅 (스트리밍 지원) |
| POST | `/v1/ingest/file` | 파일 업로드 + 인덱싱 (압축 자동 처리) |
| POST | `/v1/ingest/summarize` | 문서 자동 요약 (Ollama) |
| POST | `/v1/ingest/batch` | 서버 디렉토리 일괄 인덱싱 |
| GET | `/v1/collections` | 네임스페이스 목록 |
| GET | `/v1/dataset/interactions` | Q&A 기록 조회 |
| PATCH | `/v1/dataset/interactions/{id}/rating` | 평점 저장 (1~5) |
| POST | `/v1/dataset/export` | 파인튜닝 JSONL 내보내기 |
| POST | `/v1/dataset/manual` | 수동 Q&A 추가 |

전체 목록: http://localhost:8000/docs (Swagger UI)

---

## 🧠 파인튜닝 워크플로우

```
1. RAG Platform 설치 + Continue.dev 연결
   ↓
2. 일주일 동안 Java 작업하며 질문/답변 자연 누적
   ↓
3. 웹 UI에서 좋은 답변에 별점 4~5점 부여
   ↓
4. 좋은 답변만 필터링해 Alpaca JSONL 내보내기
   ↓
5. Google Colab (무료 T4 GPU) + Unsloth로 LoRA 파인튜닝
   - 베이스: google/gemma-4-4b 또는 qwen2.5-coder
   ↓
6. GGUF Q4_K_M로 변환 후 로컬 다운로드
   ↓
7. ollama create my-java-agent -f Modelfile
   ↓
8. default.yaml 모델 변경 → 나만의 Java 특화 에이전트 완성
```

---

## 🔒 보안 / 프라이버시

- **모든 처리는 로컬에서 실행** (LLM 추론, 임베딩, DB 모두 로컬)
- 외부 API 호출 없음 (`force_local: true` 기본값)
- 압축 파일 처리 시 Zip-slip 방어 + 1GB / 1000파일 가드 적용
- 임시 추출 파일은 처리 후 즉시 삭제

---

## 🛠️ 기술 스택

- **웹 프레임워크**: FastAPI + Uvicorn
- **임베딩**: sentence-transformers (all-MiniLM-L6-v2, 384차원)
- **벡터 DB**: FAISS (CPU)
- **메타데이터 DB**: SQLite + FTS5
- **LLM 백엔드**: Ollama (로컬), OpenAI 호환 폴백
- **문서 파싱**: PyMuPDF, python-docx, python-pptx, openpyxl, pytesseract
- **설정**: Pydantic v2 + YAML
- **로깅**: loguru

---

## 📜 라이선스

MIT License

---

## 🤝 기여

이슈 및 PR 환영합니다.

저장소: https://github.com/taejin-kim5952/BrewAgent
