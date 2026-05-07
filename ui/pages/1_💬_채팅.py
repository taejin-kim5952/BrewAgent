"""Continue.dev 대화 내역 + 평점 + 내보내기."""
import sys
from pathlib import Path
from datetime import datetime

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import get, patch, post, get_bytes, APIError, API_BASE  # noqa: E402

st.set_page_config(page_title="채팅 내역 · BrewAgent", page_icon="💬", layout="wide")
st.title("💬 Continue.dev 대화 내역")
st.caption("VSCode Continue.dev 로 한 질문이 모두 여기에 기록됩니다. 평점을 매기고 좋은 답변을 내보내세요.")


# ─── 필터 영역 ─────────────────────────────────────
with st.container(border=True):
    cols = st.columns([2, 1, 1, 1, 1])
    with cols[0]:
        ns = st.text_input("네임스페이스", value="", placeholder="전체")
    with cols[1]:
        min_rating = st.selectbox("최소 평점", [None, 1, 2, 3, 4, 5],
                                   format_func=lambda x: "전체" if x is None else f"{x}+")
    with cols[2]:
        min_score = st.selectbox("최소 AI 점수",
                                  [None, 0.5, 0.6, 0.7, 0.8, 0.9],
                                  format_func=lambda x: "전체" if x is None else f"{x}+")
    with cols[3]:
        limit = st.selectbox("표시 개수", [20, 50, 100, 200], index=1)
    with cols[4]:
        st.write("")  # 정렬용
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()

# ─── 인터랙션 목록 ────────────────────────────────
params = {"limit": limit}
if ns.strip():
    params["namespace"] = ns.strip()
if min_rating is not None:
    params["min_rating"] = min_rating
if min_score is not None:
    params["min_eval_score"] = min_score

try:
    data = get("/v1/dataset/interactions", params=params)
except APIError as e:
    st.error(f"조회 실패: {e}")
    st.stop()

items = data.get("items", [])

if not items:
    st.info("📭 조건에 맞는 대화 내역이 없습니다. Continue.dev 에서 질문하면 자동으로 기록됩니다.")
    st.stop()

st.markdown(f"**{len(items)}건** 표시")


# ─── 선택용 세션 상태 ──────────────────────────────
if "selected_interactions" not in st.session_state:
    st.session_state.selected_interactions = set()


def toggle_selection(iid: str):
    if iid in st.session_state.selected_interactions:
        st.session_state.selected_interactions.discard(iid)
    else:
        st.session_state.selected_interactions.add(iid)


# 일괄 선택 헤더
sel_count = len(st.session_state.selected_interactions)
hcols = st.columns([1, 4])
with hcols[0]:
    if st.button(f"전체 선택" if sel_count < len(items) else "선택 해제"):
        if sel_count < len(items):
            st.session_state.selected_interactions = {i["interaction_id"] for i in items}
        else:
            st.session_state.selected_interactions.clear()
        st.rerun()
with hcols[1]:
    st.markdown(f"**선택됨: {sel_count} / {len(items)}**")


# ─── 인터랙션 카드 ────────────────────────────────
for item in items:
    iid = item["interaction_id"]
    score = item.get("eval_score")
    rating = item.get("user_rating") or 0

    score_color = "🟢" if score and score >= 0.8 else "🟡" if score and score >= 0.6 else "🔵" if score else "⚪"
    score_text = f"{score:.2f}" if score is not None else "-"

    with st.container(border=True):
        # 헤더 — 체크박스 + 메타
        head = st.columns([0.3, 6, 1, 1])
        with head[0]:
            checked = iid in st.session_state.selected_interactions
            if st.checkbox("", key=f"chk_{iid}", value=checked, label_visibility="collapsed"):
                st.session_state.selected_interactions.add(iid)
            else:
                st.session_state.selected_interactions.discard(iid)
        with head[1]:
            st.markdown(f"**Q:** {item['query'][:200]}{'...' if len(item['query']) > 200 else ''}")
            st.caption(
                f"{score_color} 점수 {score_text} · "
                f"{item.get('routing', '-')} · "
                f"{item.get('created_at', '')[:19].replace('T', ' ')}"
            )
        with head[2]:
            new_rating = st.select_slider(
                "평점", options=[0, 1, 2, 3, 4, 5], value=rating,
                format_func=lambda x: "-" if x == 0 else "★" * x,
                key=f"rate_{iid}", label_visibility="collapsed",
            )
            if new_rating != rating and new_rating > 0:
                try:
                    patch(f"/v1/dataset/interactions/{iid}/rating", json={"rating": new_rating})
                    st.toast(f"평점 {new_rating}★ 저장됨")
                except APIError as e:
                    st.error(f"저장 실패: {e.detail}")
        with head[3]:
            with st.popover("답변", use_container_width=True):
                st.markdown(f"**A:** {item.get('response', '')}")


# ─── 내보내기 영역 ────────────────────────────────
st.divider()
with st.container(border=True):
    st.markdown("### 📥 JSONL 내보내기")
    cols = st.columns([1, 1, 1, 2])
    with cols[0]:
        fmt = st.selectbox("형식", ["alpaca", "openai", "sharegpt"])
    with cols[1]:
        include_manual = st.checkbox("수동 입력 포함", value=True)
    with cols[2]:
        include_guide_qa = st.checkbox("가이드 Q&A 포함", value=True)
    with cols[3]:
        st.write("")
        sel = st.session_state.selected_interactions
        scope_text = f"선택 {len(sel)}건" if sel else "전체 (필터 적용)"
        if st.button(f"📥 {scope_text} 내보내기", type="primary", use_container_width=True):
            try:
                body = {
                    "format": fmt,
                    "include_interactions": True,
                    "include_manual": include_manual,
                    "include_guide_qa": include_guide_qa,
                }
                if sel:
                    body["interaction_ids"] = list(sel)
                else:
                    if ns.strip():
                        body["namespace"] = ns.strip()
                    if min_rating is not None:
                        body["min_rating"] = min_rating
                    if min_score is not None:
                        body["min_eval_score"] = min_score

                result = post("/v1/dataset/export", json=body, timeout=60)
                content = get_bytes(result["download_url"])
                sources = result.get("sources", {})
                st.success(
                    f"✓ {result['record_count']}개 내보냄 "
                    f"(인터랙션 {sources.get('interactions', 0)} + "
                    f"수동 {sources.get('manual', 0)} + "
                    f"가이드 {sources.get('guide_qa', 0)})"
                )
                st.download_button(
                    "💾 파일 다운로드",
                    data=content,
                    file_name=result["filename"],
                    mime="application/x-ndjson",
                )
            except APIError as e:
                st.error(f"내보내기 실패: {e.detail}")
