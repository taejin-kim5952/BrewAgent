"""BrewAgent 홈 화면.

실행:
    streamlit run ui/home.py
"""
import streamlit as st

# 페이지 설정 (멀티페이지 앱의 기본 페이지)
st.set_page_config(
    page_title="BrewAgent",
    page_icon="🐍",
    layout="wide",
    initial_sidebar_state="expanded",
)

# api_client 는 같은 폴더에서 import
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from api_client import is_backend_alive, API_BASE  # noqa: E402


# ─── 헤더 ─────────────────────────────────────────────
st.title("🐍 BrewAgent")
st.caption("Java 개발 특화 AI 에이전트 + 파인튜닝 데이터 수집 플랫폼  ·  Ver 0.2")

# ─── 사이드바: 백엔드 상태 ─────────────────────────────
with st.sidebar:
    st.markdown("### 🔌 백엔드 상태")
    alive, msg = is_backend_alive()
    if alive:
        st.success(msg)
    else:
        st.error(msg)
        st.caption(f"API: `{API_BASE}`")
        st.markdown("백엔드를 먼저 실행해주세요:")
        st.code("dev_run.ps1\n# 또는\nstart.bat", language="bash")
    st.divider()
    st.markdown("👈 **메뉴**에서 기능을 선택하세요")

# 백엔드 미실행 시 진행 차단
if not alive:
    st.warning("백엔드 서버가 실행되지 않아 기능을 사용할 수 없습니다.")
    st.stop()

# ─── 메인 콘텐츠 ─────────────────────────────────────
st.markdown("""
## 🎯 무엇을 할 수 있나요

### 🗨️ Continue.dev 대화 내역
VSCode Continue.dev 로 한 모든 질문/답변이 자동 기록됩니다.
평점을 남기고, 좋은 답변만 골라 파인튜닝 데이터로 내보낼 수 있습니다.

### ✍️ 수동 데이터 입력
직접 Q&A 쌍을 작성해서 훈련 데이터에 추가합니다.

### 📄 문서 요약
PDF/Word/Excel/이미지 등을 업로드하면 Ollama 로컬 모델이 자동 요약합니다.
**ZIP/TAR 압축 파일도 지원** — 보안 문서 처리에 유용.

### 🎓 가이드 → 훈련 데이터 ⭐
회사 보안/품질/네이밍 가이드 PDF를 업로드하면:
1. **Phase 1**: AI가 규칙 단위로 자동 추출
2. **Phase 2**: 각 규칙에서 Q&A 5종 (코드 리뷰/생성/개념/거절) 자동 생성
3. 검수 후 → JSONL 내보내기 → Colab에서 파인튜닝

이 데이터로 **회사 가이드를 따르는 나만의 Java AI** 를 만들 수 있습니다.

---

### 📌 빠른 링크
""")

col1, col2, col3 = st.columns(3)
with col1:
    st.markdown(f"📡 [API 문서 (Swagger)]({API_BASE}/docs)")
with col2:
    st.markdown(f"💚 [백엔드 헬스]({API_BASE}/health)")
with col3:
    st.markdown("🐙 [GitHub](https://github.com/taejin-kim5952/BrewAgent)")

st.divider()
st.caption("👈 왼쪽 사이드바의 페이지 메뉴에서 원하는 기능을 선택하세요.")
