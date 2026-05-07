"""문서 업로드 → AI 요약 (PDF/Word/PPT/Excel/이미지/코드/ZIP)."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import post, APIError, API_BASE  # noqa: E402
import requests

st.set_page_config(page_title="문서 요약 · BrewAgent", page_icon="📄", layout="wide")
st.title("📄 문서 요약")
st.caption(
    "PDF · Word · PPT · Excel · TXT · 이미지(OCR) · 코드 파일 지원. "
    "**압축 파일(.zip / .tar.gz)** 도 자동 해제 후 통합 요약. "
    "문서는 인덱싱되지 않고 요약만 수행됩니다."
)


# ─── 업로드 + 옵션 ──────────────────────────────────
with st.container(border=True):
    file = st.file_uploader(
        "파일 선택",
        type=["pdf", "docx", "pptx", "xlsx", "xls", "txt", "md", "csv",
              "png", "jpg", "jpeg",
              "java", "sql", "py", "js", "ts", "go",
              "zip", "tar", "gz", "tgz"],
    )

    cols = st.columns(3)
    with cols[0]:
        length = st.selectbox(
            "요약 분량",
            ["short", "medium", "long"],
            index=1,
            format_func=lambda x: {
                "short": "짧게 (3~5줄)",
                "medium": "보통 (10줄)",
                "long": "자세히 (섹션별)",
            }[x],
        )
    with cols[1]:
        language = st.selectbox(
            "언어",
            ["ko", "en"],
            format_func=lambda x: {"ko": "한국어", "en": "English"}[x],
        )
    with cols[2]:
        model_choice = st.selectbox(
            "모델",
            ["fast", "full"],
            format_func=lambda x: {"fast": "fast (빠름)", "full": "full (정확)"}[x],
        )

    run = st.button("🚀 요약 시작", type="primary", use_container_width=True, disabled=file is None)


# ─── 결과 ──────────────────────────────────────────
if run and file is not None:
    progress_msg = st.empty()
    progress_msg.info(
        "⏳ 문서 파싱 + Ollama 요약 진행 중... "
        "(모델/문서 크기에 따라 수십 초 ~ 수 분 소요)"
    )

    with st.spinner("처리 중..."):
        try:
            # multipart/form-data 직접 호출
            r = requests.post(
                API_BASE + "/v1/ingest/summarize",
                files={"file": (file.name, file.getvalue())},
                data={
                    "length": length,
                    "language": language,
                    "model_choice": model_choice,
                },
                timeout=900,
            )
            if not r.ok:
                detail = r.json().get("detail", r.text) if r.content else f"HTTP {r.status_code}"
                progress_msg.empty()
                st.error(f"요약 실패: {detail}")
                st.stop()

            data = r.json()
            progress_msg.empty()
        except requests.Timeout:
            progress_msg.empty()
            st.error("⏱️ 응답 시간 초과. 더 작은 모델로 시도하거나 파일을 분할하세요.")
            st.stop()
        except Exception as e:
            progress_msg.empty()
            st.error(f"오류: {e}")
            st.stop()

    # 메타 정보
    st.success("✓ 요약 완료")
    meta_cols = st.columns(4)
    with meta_cols[0]:
        st.metric("파일", data["filename"])
    with meta_cols[1]:
        st.metric("문서 종류", data["doc_type"])
    with meta_cols[2]:
        st.metric("글자 수", f"{data['char_count']:,}")
    with meta_cols[3]:
        st.metric("청크/모드", f"{data['chunk_count']} / {data['mode']}")

    st.caption(f"🤖 사용 모델: `{data['model_used']}`")

    if data.get("errors"):
        with st.expander(f"⚠️ 경고 {len(data['errors'])}개"):
            for err in data["errors"]:
                st.text(err)

    # 요약 본문
    st.markdown("### 📝 요약 결과")
    st.markdown(data["summary"])

    # 저장 / 복사
    st.divider()
    save_cols = st.columns(2)
    with save_cols[0]:
        st.download_button(
            "💾 텍스트로 다운로드",
            data=data["summary"],
            file_name=f"summary_{file.name}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with save_cols[1]:
        if st.button("📌 수동 데이터로 저장", use_container_width=True):
            try:
                post(
                    "/v1/dataset/manual",
                    json={
                        "instruction": f"다음 문서를 요약해주세요: {data['filename']}",
                        "output": data["summary"],
                    },
                )
                st.success("✓ 수동 데이터셋에 저장됨")
            except APIError as e:
                st.error(f"저장 실패: {e.detail}")
