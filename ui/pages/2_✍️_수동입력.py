"""수동 Q&A 입력 + 목록 + 삭제."""
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import get, post, delete, APIError  # noqa: E402

st.set_page_config(page_title="수동 입력 · BrewAgent", page_icon="✍️", layout="wide")
st.title("✍️ 수동 데이터 입력")
st.caption("훈련 데이터에 직접 Q&A 쌍을 추가합니다. 회사 가이드에 없는 도메인 지식 보강에 유용합니다.")


# ─── 입력 폼 ───────────────────────────────────────
with st.container(border=True):
    st.markdown("### ➕ 새 Q&A 추가")
    with st.form("manual_form", clear_on_submit=True):
        instruction = st.text_area(
            "질문 (instruction)", height=100,
            placeholder="AI가 학습할 질문 또는 지시사항을 입력하세요\n예: Spring Boot에서 트랜잭션 어떻게 거나요?",
        )
        output = st.text_area(
            "답변 (output)", height=200,
            placeholder="이상적인 답변을 입력하세요 (코드 포함 가능)",
        )
        submit = st.form_submit_button("💾 저장", type="primary", use_container_width=True)

        if submit:
            if not instruction.strip() or not output.strip():
                st.warning("질문과 답변을 모두 입력해주세요.")
            else:
                try:
                    res = post(
                        "/v1/dataset/manual",
                        json={"instruction": instruction.strip(), "output": output.strip()},
                    )
                    st.success(f"✓ 저장됨 (ID: {res.get('entry_id', '?')[:8]}...)")
                    st.rerun()
                except APIError as e:
                    st.error(f"저장 실패: {e.detail}")


# ─── 목록 ─────────────────────────────────────────
st.divider()
try:
    data = get("/v1/dataset/manual", params={"limit": 200})
except APIError as e:
    st.error(f"목록 조회 실패: {e}")
    st.stop()

items = data.get("items", [])
st.markdown(f"### 📋 저장된 Q&A ({len(items)}개)")

if not items:
    st.info("📭 아직 저장된 데이터가 없습니다. 위 폼에서 첫 Q&A를 추가하세요.")
    st.stop()

for entry in items:
    eid = entry["entry_id"]
    created = entry.get("created_at", "")[:19].replace("T", " ")
    with st.container(border=True):
        cols = st.columns([6, 1])
        with cols[0]:
            st.markdown(f"**Q:** {entry['instruction']}")
            with st.expander("답변 보기"):
                st.markdown(entry["output"])
            st.caption(f"📅 {created} · ID: `{eid[:8]}...`")
        with cols[1]:
            if st.button("🗑️ 삭제", key=f"del_{eid}", use_container_width=True):
                try:
                    delete(f"/v1/dataset/manual/{eid}")
                    st.toast("삭제됨")
                    st.rerun()
                except APIError as e:
                    st.error(f"삭제 실패: {e.detail}")
