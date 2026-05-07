"""가이드 → 훈련 데이터 변환 (Phase 1 + 2)."""
import sys
import time
from pathlib import Path

import streamlit as st
import requests

sys.path.insert(0, str(Path(__file__).parent.parent))
from api_client import get, post, patch, delete, APIError, API_BASE  # noqa: E402

st.set_page_config(page_title="가이드 → 훈련 데이터 · BrewAgent", page_icon="🎓", layout="wide")
st.title("🎓 가이드 → 훈련 데이터")
st.caption(
    "회사 보안/품질/네이밍 가이드 PDF/Word 를 업로드하면 AI가 규칙 단위로 자동 분할하고, "
    "각 규칙에서 Q&A 학습 데이터를 자동 생성합니다."
)


# ─── 세션 상태 ───────────────────────────────────
if "selected_guide_id" not in st.session_state:
    st.session_state.selected_guide_id = None


# ─── 영역 1: 가이드 업로드 ────────────────────────
with st.container(border=True):
    st.markdown("### 📤 가이드 업로드")
    cols = st.columns([2, 1, 1])
    with cols[0]:
        upload_file = st.file_uploader(
            "PDF/Word 가이드", type=["pdf", "docx", "doc"],
            key="guide_uploader",
        )
    with cols[1]:
        guide_name = st.text_input("별칭", placeholder="예: 보안 가이드 v3")
    with cols[2]:
        st.write("")
        if st.button(
            "📤 업로드 시작", type="primary", use_container_width=True,
            disabled=upload_file is None or not guide_name.strip(),
        ):
            try:
                r = requests.post(
                    API_BASE + "/v1/guide/upload",
                    files={"file": (upload_file.name, upload_file.getvalue())},
                    data={"name": guide_name.strip()},
                    timeout=60,
                )
                if r.ok:
                    st.success(f"✓ 업로드됨. AI가 백그라운드에서 규칙을 추출 중입니다.")
                    st.rerun()
                else:
                    st.error(f"업로드 실패: {r.text[:200]}")
            except Exception as e:
                st.error(f"오류: {e}")


# ─── 영역 2: 가이드 목록 ──────────────────────────
with st.container(border=True):
    head = st.columns([4, 1])
    with head[0]:
        try:
            guides_data = get("/v1/guide/list")
            guides = guides_data.get("items", [])
        except APIError as e:
            st.error(f"가이드 목록 조회 실패: {e}")
            guides = []
        st.markdown(f"### 📚 업로드된 가이드 ({len(guides)}개)")
    with head[1]:
        if st.button("🔄 새로고침", use_container_width=True):
            st.rerun()

    if not guides:
        st.info("업로드된 가이드가 없습니다.")
    else:
        # 진행 중인 가이드가 있으면 자동 갱신 안내
        active = [g for g in guides if g["status"] in ("parsing", "extracting")]
        if active:
            st.caption(f"⏳ {len(active)}개 가이드가 백그라운드 처리 중. 새로고침으로 진행률 확인.")

        for g in guides:
            with st.container(border=True):
                cols = st.columns([3, 1, 1, 0.5, 0.5])
                with cols[0]:
                    is_selected = st.session_state.selected_guide_id == g["guide_id"]
                    label = ("✅ " if is_selected else "") + g["name"]
                    st.markdown(f"**{label}**")
                    st.caption(
                        f"{g['source_file']} · {g['page_count']}p · 규칙 {g['rule_count']}개 · "
                        f"`{g['guide_id'][:8]}...`"
                    )
                    if g.get("error_msg"):
                        st.error(f"⚠ {g['error_msg'][:200]}")
                with cols[1]:
                    status = g["status"]
                    if status == "done":
                        st.success("완료")
                    elif status == "failed":
                        st.error("실패")
                    elif status in ("parsing", "extracting"):
                        st.info(f"{status} {g['progress']}%")
                    else:
                        st.text(status)
                with cols[2]:
                    if status == "done":
                        st.progress(1.0, text="100%")
                    elif status in ("parsing", "extracting"):
                        st.progress(g["progress"] / 100, text=f"{g['progress']}%")
                with cols[3]:
                    open_disabled = g["rule_count"] == 0
                    if st.button("열기", key=f"open_{g['guide_id']}",
                                 use_container_width=True, disabled=open_disabled):
                        st.session_state.selected_guide_id = g["guide_id"]
                        st.rerun()
                with cols[4]:
                    if st.button("🗑", key=f"del_{g['guide_id']}", use_container_width=True):
                        if st.session_state.get(f"confirm_del_{g['guide_id']}"):
                            try:
                                delete(f"/v1/guide/{g['guide_id']}")
                                if st.session_state.selected_guide_id == g["guide_id"]:
                                    st.session_state.selected_guide_id = None
                                st.session_state.pop(f"confirm_del_{g['guide_id']}", None)
                                st.toast("삭제됨")
                                st.rerun()
                            except APIError as e:
                                st.error(e.detail)
                        else:
                            st.session_state[f"confirm_del_{g['guide_id']}"] = True
                            st.warning("한번 더 클릭하면 삭제")


# ─── 영역 3: 선택된 가이드 — 규칙 검수 + Q&A 생성/검수 ────
guide_id = st.session_state.selected_guide_id
if not guide_id:
    st.divider()
    st.info("👆 위 목록에서 가이드를 [열기] 하면 규칙 검수 + Q&A 생성 영역이 표시됩니다.")
    st.stop()

# 선택된 가이드 정보
sel_guide = next((g for g in guides if g["guide_id"] == guide_id), None)
if not sel_guide:
    st.session_state.selected_guide_id = None
    st.rerun()

st.divider()
st.header(f"📑 {sel_guide['name']}")

tab1, tab2 = st.tabs(["📜 규칙 검수 (Phase 1)", "🤖 Q&A 검수 (Phase 2)"])


# ─── Tab 1: 규칙 검수 ────────────────────────────
with tab1:
    # 필터
    fcols = st.columns(4)
    with fcols[0]:
        f_cat = st.selectbox(
            "카테고리",
            ["", "보안", "품질", "네이밍", "테스트", "로깅", "트랜잭션", "API", "성능", "예외처리", "기타"],
            format_func=lambda x: "전체" if x == "" else x,
        )
    with fcols[1]:
        f_sev = st.selectbox(
            "심각도",
            ["", "must", "should", "may", "unknown"],
            format_func=lambda x: "전체" if x == "" else x,
        )

    params = {}
    if f_cat:
        params["category"] = f_cat
    if f_sev:
        params["severity"] = f_sev
    try:
        rules_data = get(f"/v1/guide/{guide_id}/rules", params=params)
        rules = rules_data.get("items", [])
    except APIError as e:
        st.error(f"규칙 조회 실패: {e}")
        st.stop()

    st.markdown(f"**총 {rules_data.get('total', 0)}개 규칙**")

    # Q&A 생성 트리거 버튼
    gcols = st.columns([3, 1, 1])
    with gcols[1]:
        gen_count = st.selectbox("규칙당 Q&A", [3, 5, 8, 10], index=1)
    with gcols[2]:
        only_reviewed = st.checkbox("검수된 규칙만", value=False)
        if st.button("🤖 Q&A 생성 시작", type="primary", use_container_width=True,
                      disabled=len(rules) == 0):
            try:
                res = post(
                    f"/v1/guide/{guide_id}/generate_qa",
                    json={
                        "count_per_rule": gen_count,
                        "only_reviewed": only_reviewed,
                        "overwrite": False,
                    },
                )
                st.success(
                    f"✓ Q&A 생성 시작: {res['rule_count']} 규칙 × {res['count_per_rule']} = "
                    f"~{res['estimated_total']}개. [Q&A 검수] 탭에서 진행 확인."
                )
                time.sleep(1)
            except APIError as e:
                st.error(f"생성 시작 실패: {e.detail}")

    if not rules:
        st.info("조건에 맞는 규칙이 없습니다.")
    else:
        for r in rules:
            with st.container(border=True):
                head_cols = st.columns([5, 1, 1, 1])
                with head_cols[0]:
                    sev_emoji = {"must": "🔴", "should": "🟡", "may": "🔵"}.get(r["severity"], "⚪")
                    rev = "✅" if r["reviewed"] else ""
                    edited = "✏️" if r["user_edited"] else ""
                    st.markdown(
                        f"**{sev_emoji} {r['section_label']} {r['title']}** {rev}{edited}"
                    )
                    st.caption(f"카테고리: {r['category']} · 심각도: {r['severity']} · "
                              f"페이지: {r['source_pages'] or '-'}")
                    st.markdown(r["body"])
                    if r["code_bad"] or r["code_good"]:
                        with st.expander("코드 예시"):
                            if r["code_bad"]:
                                st.markdown("**❌ 잘못된 예**")
                                st.code(r["code_bad"], language="java")
                            if r["code_good"]:
                                st.markdown("**✅ 모범 예**")
                                st.code(r["code_good"], language="java")
                with head_cols[1]:
                    new_rev = 0 if r["reviewed"] else 1
                    if st.button(
                        "✓ 검수해제" if r["reviewed"] else "✓ 검수완료",
                        key=f"rev_{r['rule_id']}", use_container_width=True,
                    ):
                        try:
                            patch(f"/v1/guide/rules/{r['rule_id']}", json={"reviewed": new_rev})
                            st.rerun()
                        except APIError as e:
                            st.error(e.detail)
                with head_cols[2]:
                    if st.button("🤖 재생성", key=f"regen_{r['rule_id']}",
                                 use_container_width=True,
                                 help="이 규칙의 Q&A만 다시 생성"):
                        try:
                            post(f"/v1/guide/rules/{r['rule_id']}/regenerate_qa",
                                 params={"count": 5})
                            st.toast("재생성 시작")
                        except APIError as e:
                            st.error(e.detail)
                with head_cols[3]:
                    if st.button("🗑", key=f"delr_{r['rule_id']}", use_container_width=True):
                        try:
                            delete(f"/v1/guide/rules/{r['rule_id']}")
                            st.toast("삭제됨")
                            st.rerun()
                        except APIError as e:
                            st.error(e.detail)


# ─── Tab 2: Q&A 검수 ────────────────────────────
with tab2:
    # 필터
    qcols = st.columns(4)
    with qcols[0]:
        f_status = st.selectbox(
            "상태",
            ["pending", "approved", "rejected", ""],
            format_func=lambda x: "전체" if x == "" else {
                "pending": "검수 대기", "approved": "승인", "rejected": "거절"
            }.get(x, x),
        )
    with qcols[1]:
        f_qa_type = st.selectbox(
            "유형",
            ["", "code_review", "code_gen", "concept", "refusal"],
            format_func=lambda x: "전체" if x == "" else {
                "code_review": "🔍 코드 리뷰",
                "code_gen": "✍️ 코드 생성",
                "concept": "💡 개념",
                "refusal": "🛑 거절",
            }.get(x, x),
        )
    with qcols[3]:
        st.write("")
        if st.button("🔄 새로고침", key="refresh_qa", use_container_width=True):
            st.rerun()

    qparams = {}
    if f_status:
        qparams["status"] = f_status
    if f_qa_type:
        qparams["qa_type"] = f_qa_type

    try:
        qa_data = get(f"/v1/guide/{guide_id}/qa", params=qparams)
        qa_items = qa_data.get("items", [])
    except APIError as e:
        st.error(f"Q&A 조회 실패: {e}")
        st.stop()

    # 상태별 카운트
    stat_cols = st.columns(4)
    with stat_cols[0]:
        st.metric("전체", qa_data.get("total", 0))
    with stat_cols[1]:
        st.metric("⏳ 대기", qa_data.get("pending", 0))
    with stat_cols[2]:
        st.metric("✅ 승인", qa_data.get("approved", 0))
    with stat_cols[3]:
        st.metric("❌ 거절", qa_data.get("rejected", 0))

    if not qa_items:
        st.info("📭 조건에 맞는 Q&A가 없습니다. 위에서 [Q&A 생성 시작] 버튼을 눌러주세요.")
        st.stop()

    # 일괄 작업
    if "selected_qa" not in st.session_state:
        st.session_state.selected_qa = set()

    bulk_cols = st.columns([2, 1, 1, 1])
    sel_count = len(st.session_state.selected_qa & {q["qa_id"] for q in qa_items})
    with bulk_cols[0]:
        st.caption(f"선택됨: {sel_count}개")
    with bulk_cols[1]:
        if st.button("✅ 선택 승인", disabled=sel_count == 0, use_container_width=True):
            try:
                post("/v1/guide/qa/bulk", json={
                    "qa_ids": list(st.session_state.selected_qa),
                    "action": "approve",
                })
                st.session_state.selected_qa.clear()
                st.rerun()
            except APIError as e:
                st.error(e.detail)
    with bulk_cols[2]:
        if st.button("❌ 선택 거절", disabled=sel_count == 0, use_container_width=True):
            try:
                post("/v1/guide/qa/bulk", json={
                    "qa_ids": list(st.session_state.selected_qa),
                    "action": "reject",
                })
                st.session_state.selected_qa.clear()
                st.rerun()
            except APIError as e:
                st.error(e.detail)
    with bulk_cols[3]:
        if st.button("🗑️ 선택 삭제", disabled=sel_count == 0, use_container_width=True):
            try:
                post("/v1/guide/qa/bulk", json={
                    "qa_ids": list(st.session_state.selected_qa),
                    "action": "delete",
                })
                st.session_state.selected_qa.clear()
                st.rerun()
            except APIError as e:
                st.error(e.detail)

    # Q&A 카드
    type_emoji = {
        "code_review": "🔍 코드 리뷰",
        "code_gen": "✍️ 코드 생성",
        "concept": "💡 개념",
        "refusal": "🛑 거절",
    }
    status_color = {
        "pending": "🟡 대기",
        "approved": "🟢 승인",
        "rejected": "🔴 거절",
    }

    for q in qa_items:
        qid = q["qa_id"]
        with st.container(border=True):
            cols = st.columns([0.3, 6, 1])
            with cols[0]:
                checked = qid in st.session_state.selected_qa
                if st.checkbox("", key=f"qa_chk_{qid}", value=checked, label_visibility="collapsed"):
                    st.session_state.selected_qa.add(qid)
                else:
                    st.session_state.selected_qa.discard(qid)
            with cols[1]:
                st.markdown(
                    f"{type_emoji.get(q['qa_type'], q['qa_type'])} · "
                    f"{status_color.get(q['status'], q['status'])} · "
                    f"규칙 `{q.get('rule_section_label', '?')}`"
                )
                st.markdown(f"**Q:** {q['instruction']}")
                with st.expander(f"답변 보기 ({len(q['output'])}자)"):
                    st.markdown(q["output"])
            with cols[2]:
                if q["status"] != "approved":
                    if st.button("✓ 승인", key=f"app_{qid}", use_container_width=True):
                        try:
                            patch(f"/v1/guide/qa/{qid}", json={"status": "approved"})
                            st.rerun()
                        except APIError as e:
                            st.error(e.detail)
                if q["status"] != "rejected":
                    if st.button("✗ 거절", key=f"rej_{qid}", use_container_width=True):
                        try:
                            patch(f"/v1/guide/qa/{qid}", json={"status": "rejected"})
                            st.rerun()
                        except APIError as e:
                            st.error(e.detail)
                if st.button("🗑", key=f"qa_del_{qid}", use_container_width=True):
                    try:
                        delete(f"/v1/guide/qa/{qid}")
                        st.toast("삭제됨")
                        st.rerun()
                    except APIError as e:
                        st.error(e.detail)
