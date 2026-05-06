# BrewAgent — Java 개발 특화 AI 에이전트

> **로컬 환경에서 동작하는 Java 개발 보조 + 파인튜닝 데이터 수집 플랫폼**

![Version](https://img.shields.io/badge/version-0.2-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![License](https://img.shields.io/badge/license-MIT-orange)

VSCode + Continue.dev 와 연동되는 로컬 RAG 서버이며, 회사 보안/품질 가이드를
학습 데이터로 자동 변환하여 **나만의 Java 특화 AI 모델**을 파인튜닝할 수 있는
통합 플랫폼입니다.

모든 처리가 로컬에서 실행되어 외부 API 호출이 없으며, Ollama 기반 로컬 LLM과
FAISS 벡터 검색을 결합하여 동작합니다.

---

## 📚 목차

### 🎯 시작하기
- 📖 [1. 프로젝트 개요](docs/01_프로젝트_개요.md) — 목적·핵심 기능·아키텍처
- 🚀 [7. 실행 방법](docs/07_실행_방법.md) — 설치·실행·진단·종료
- 🔌 [6. Continue.dev 연결 설정](docs/06_Continue_연동.md) — VSCode 연동

### 🏗️ 코드 구조
- 📁 [2. 디렉터리 구조](docs/02_디렉터리_구조.md) — 전체 파일 트리
- 🔧 [4. 핵심 모듈 상세](docs/04_핵심_모듈.md) — 컴포넌트별 동작 원리
- 💾 [5. DB 스키마](docs/05_DB_스키마.md) — 8개 SQLite 테이블

### 🌐 API/통합
- 📡 [3. API 엔드포인트](docs/03_API_엔드포인트.md) — REST API 레퍼런스
- 📦 [8. 의존성 목록](docs/08_의존성.md) — 라이브러리/외부 도구

### 🛠️ 개발/운영
- 🔌 [10. 확장 개발 가이드](docs/10_확장_가이드.md) — 새 파서/Scorer/백엔드 추가
- ⚠️ [9. 알려진 이슈](docs/09_이슈_및_미완성.md) — 트러블슈팅 + Phase 3 후보
- 📋 [11. 변경 이력](docs/11_변경_이력.md) — Phase 0~2 일자별

### 🎓 가이드 → 훈련 데이터
- 📑 [12. Phase 1 — 가이드 규칙 추출](docs/12_Phase1_가이드_규칙추출.md)
- 🤖 [13. Phase 2 — Q&A 자동 생성](docs/13_Phase2_QA_생성.md)

---

## 📜 라이선스

MIT License — 자세한 내용은 [LICENSE](LICENSE) 참고.

저장소: https://github.com/taejin-kim5952/BrewAgent
