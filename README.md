# BrewAgent — Java 개발 특화 AI 에이전트

> **로컬 환경에서 동작하는 Java 개발 보조 + 파인튜닝 데이터 수집 플랫폼**

VSCode + Continue.dev 와 연동되어 Java 코드 작성/리팩토링/디버깅을 도우면서,
회사 보안/품질 가이드를 학습 데이터로 자동 변환하여 **나만의 Java 특화 AI 모델**을
파인튜닝할 수 있는 통합 플랫폼입니다.

![Version](https://img.shields.io/badge/version-0.2-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

---

## 📌 핵심 기능

| 기능 | 설명 |
|---|---|
| **RAG 채팅** | 업로드 문서를 참고해 Ollama 로컬 모델로 답변 (Continue.dev 연동) |
| **멀티모달 인제스트** | PDF·Word·PPT·Excel·이미지(OCR)·코드·텍스트 인덱싱 |
| **압축 파일 지원** | ZIP/TAR 업로드 시 내부 모든 파일 자동 추출·인덱싱 |
| **하이브리드 검색** | FAISS 벡터 + SQLite FTS5 BM25 결합 |
| **LLM 자동 라우팅** | 질문 복잡도에 따라 빠른/정확한 모델 자동 선택 |
| **문서 요약** | 업로드 문서를 Ollama로 자동 요약 (긴 문서는 map-reduce) |
| **🆕 가이드 → 규칙 추출** | 회사 가이드 PDF → AI가 규칙 단위로 자동 분할 |
| **🆕 Q&A 자동 생성** | 규칙 → 코드 리뷰/생성/개념/거절 4종 학습 데이터 합성 |
| **훈련 데이터 수집** | 모든 Q&A 자동 기록 + JSONL 내보내기 (Alpaca/OpenAI/ShareGPT) |
| **웹 UI** | 4개 탭으로 모든 기능 제공 |

---

## 🚀 빠른 시작

### 1. 사전 설치
| 항목 | 다운로드 |
|---|---|
| Python 3.10+ | https://www.python.org/downloads/ (PATH 추가 체크) |
| Ollama | https://ollama.com/download |

### 2. 설치 (Windows)
```bash
# 이 저장소 다운로드 후 setup.bat 더블클릭
setup.bat

# Ollama 모델 받기 (테스트용 가벼운 모델)
ollama pull gemma3:1b
```

### 3. 실행
```bash
# 설치 폴더의 start.bat 더블클릭 (기본: C:\RAGPlatform\start.bat)
# 또는 바탕화면 'RAG Platform.bat'
```

브라우저 접속:
- **웹 UI**: http://localhost:8000/
- **API 문서**: http://localhost:8000/docs
- **상태 확인**: http://localhost:8000/health

---

## 📚 상세 문서 (클릭해서 보세요)

> 본 README는 개요만 다룹니다. 상세 정보는 아래 챕터로 분리되어 있습니다.

### 🎯 시작하기
- 📖 **[1. 프로젝트 개요](docs/01_프로젝트_개요.md)** — 목적·핵심 기능·아키텍처 다이어그램
- 🚀 **[7. 실행 방법](docs/07_실행_방법.md)** — 설치/실행/진단/종료 가이드
- 🔌 **[6. Continue.dev 연결 설정](docs/06_Continue_연동.md)** — VSCode 연동

### 🏗️ 코드 구조
- 📁 **[2. 디렉터리 구조](docs/02_디렉터리_구조.md)** — 전체 파일 트리와 모듈 역할
- 🔧 **[4. 핵심 모듈 상세](docs/04_핵심_모듈.md)** — AppContainer·채팅·인제스트·평가·라우팅·설정
- 💾 **[5. DB 스키마](docs/05_DB_스키마.md)** — 8개 SQLite 테이블 정의

### 🌐 API/통합
- 📡 **[3. API 엔드포인트](docs/03_API_엔드포인트.md)** — REST API 전체 레퍼런스 + 예시
- 📦 **[8. 의존성 목록](docs/08_의존성.md)** — requirements.txt 라이브러리 설명

### 🛠️ 개발/운영
- 🔌 **[10. 확장 개발 가이드](docs/10_확장_가이드.md)** — 새 파서/Scorer/LLM 백엔드 추가 방법
- ⚠️ **[9. 알려진 이슈](docs/09_이슈_및_미완성.md)** — 해결된 버그·Phase 3 후보·트러블슈팅
- 📋 **[11. 변경 이력](docs/11_변경_이력.md)** — Phase 0~2 일자별 작업 기록

### 🎓 가이드 → 훈련 데이터 (신규)
- 📑 **[12. Phase 1 — 가이드 규칙 추출](docs/12_Phase1_가이드_규칙추출.md)** — PDF/Word → AI 규칙 자동 분할
- 🤖 **[13. Phase 2 — Q&A 자동 생성](docs/13_Phase2_QA_생성.md)** — 규칙 → 파인튜닝용 학습 데이터

---

## 🏗️ 아키텍처 한눈에

```
[VSCode + Continue.dev]
        │  POST /v1/chat/completions
        ▼
[BrewAgent Server :8000]
   ├─ QueryIntelligence   (의도 분석 + 쿼리 재작성)
   ├─ HybridRetriever     (FAISS + FTS5)
   ├─ ContextOptimizer    (중복 제거 + 토큰 예산)
   ├─ PromptBuilder       (의도별 시스템 프롬프트)
   ├─ LLMRouter ──→ OllamaBackend (gemma 등)
   └─ EvaluationEngine + InteractionLogger (백그라운드)
        │
        ▼
[Ollama :11434]  ←── 로컬 LLM
```

자세한 흐름은 [4. 핵심 모듈 상세](docs/04_핵심_모듈.md) 참고.

---

## 🎯 PC 사양별 추천 모델

| GPU/RAM | 추천 | 비고 |
|---|---|---|
| RTX 3050+ (4GB VRAM) | `gemma3:1b` (테스트) / `gemma4:e4b` (운영) | 한국어 균형 |
| RTX 3060+ (8GB VRAM) | `qwen2.5-coder:7b` | 코드 작업 최강 |
| GPU 없음 (RAM 16GB) | `gemma3:1b` 또는 `qwen2.5-coder:3b` | CPU 추론 |

`rag/configs/local.yaml` 에서 변경:
```yaml
ollama:
  model_fast: "gemma3:1b"
  model_full: "gemma4:e4b"
```

---

## 🧠 파인튜닝 워크플로우

```
1. 가이드 PDF/Word 업로드 → AI가 규칙 추출
2. 사용자 검수/편집 → 구조 확정
3. Q&A 자동 생성 (규칙당 5개, 4종 변형)
4. 사용자 승인 → 승인된 Q&A만 데이터셋에 포함
5. JSONL 내보내기 (Alpaca 등) → Colab에서 LoRA 파인튜닝
6. GGUF 변환 → Ollama 등록 → 나만의 Java 에이전트 완성
```

자세한 단계는 [Phase 2 문서](docs/13_Phase2_QA_생성.md) 참고.

---

## 🔒 보안 / 프라이버시

- **모든 처리 로컬 실행** (LLM 추론 + 임베딩 + DB)
- 외부 API 호출 없음 (`force_local: true` 기본값)
- 압축 파일 처리 시 Zip-slip 방어 + 1GB / 1000파일 가드
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
